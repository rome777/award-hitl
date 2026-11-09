"""송년회 시상 승인 에이전트 (LangGraph).

추천 1건 = thread_id 1개.
write(gpt-5-nano) → judge(Jev) → 기준에 안 걸리면 publish
                              → 걸리면 review(interrupt)에서 멈추고 담당자 답을 기다린다
review 답: approve → publish / edit → publish(수정본) / drop → drop / rewrite → write (최대 2회)

publish 만 바깥(시상식 화면)으로 결과를 내보낸다. review 안에는 부수 효과를 두지 않는다.
재개하면 review 가 첫 줄부터 다시 실행되기 때문이다.
"""
import sqlite3
import sys
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import store
from criteria import stop_reasons
from writer import write_award

load_dotenv(store.os.path.join(store.os.path.dirname(store.os.path.abspath(__file__)), ".env"))

MAX_REWRITES = 2
APPROVER = "송년회 담당자"  # 승인하는 사람은 특정인이 아니라 데모를 쓰는 임의의 담당자


class State(TypedDict, total=False):
    rec: dict            # {"id", "from", "to", "to_role", "reason"}
    award: dict          # {"title", "citation", "engine"}
    judge: dict          # Jev 판정 결과 (judge.py)
    stop_reasons: list   # 걸린 기준. 비어 있으면 자동 공개
    decision: dict       # 담당자 답 {"action", "text"?, "reason"?, "instruction"?, "approver"}
    rewrites: int        # 다시 쓰기 횟수
    status: str          # published | dropped


def build_app(con, judge, checkpointer):
    def write(state):
        d = state.get("decision") or {}
        if d.get("action") == "rewrite":
            store.log_decision(con, state["rec"]["id"], "rewrite", {"instruction": d.get("instruction", "")}, d.get("approver"))
            award = write_award(state["rec"], instruction=d.get("instruction"), previous=state["award"])
            return {"award": award, "rewrites": state.get("rewrites", 0) + 1, "decision": {}}
        return {"award": write_award(state["rec"]), "rewrites": 0}

    def judge_node(state):
        j = judge.judge(state["award"], state["rec"])
        return {"judge": j, "stop_reasons": stop_reasons(j)}

    def after_judge(state):
        # 담당자가 다시 쓰게 한 건은 기준과 상관없이 담당자에게 돌아간다
        if state["stop_reasons"] or state.get("rewrites", 0) > 0:
            return "review"
        return "publish"

    def review(state):
        rec, award = state["rec"], state["award"]
        answer = interrupt({
            "추천": f"{rec['from']} → {rec['to']}: {rec['reason']}",
            "상": f"{award['title']}: {award['citation']}",
            "판정": state["judge"],
            "멈춘 이유": state["stop_reasons"] or ["다시 쓴 문구 확인"],
            "승인하면": f"시상식 화면에 '{award['title']}'이 {rec['to']}님 이름으로 공개됩니다",
            "남은 다시 쓰기": MAX_REWRITES - state.get("rewrites", 0),
        })
        return {"decision": answer}

    def after_review(state):
        action = state["decision"].get("action")
        if action in ("approve", "edit"):
            return "publish"
        if action == "rewrite" and state.get("rewrites", 0) < MAX_REWRITES:
            return "write"
        return "drop"

    def publish(state):
        rec, award, d = state["rec"], dict(state["award"]), state.get("decision") or {}
        if d.get("action") == "edit":
            award["title"], award["citation"] = d.get("title") or award["title"], d.get("text") or award["citation"]
        via = "자동" if not d else ("수정 후 승인" if d["action"] == "edit" else "승인")
        store.publish(con, rec["id"], rec["to"], award["title"], award["citation"], via)
        if d:
            store.log_decision(con, rec["id"], d["action"], {"title": award["title"], "citation": award["citation"]}, d.get("approver"))
        return {"award": award, "status": "published"}

    def drop(state):
        d = state.get("decision") or {}
        store.log_decision(con, state["rec"]["id"], "drop", {"reason": d.get("reason", "")}, d.get("approver"))
        return {"status": "dropped"}

    g = StateGraph(State)
    g.add_node("write", write)
    g.add_node("judge", judge_node)
    g.add_node("review", review)
    g.add_node("publish", publish)
    g.add_node("drop", drop)
    g.add_edge(START, "write")
    g.add_edge("write", "judge")
    g.add_conditional_edges("judge", after_judge, {"review": "review", "publish": "publish"})
    g.add_conditional_edges("review", after_review, {"publish": "publish", "write": "write", "drop": "drop"})
    g.add_edge("publish", END)
    g.add_edge("drop", END)
    return g.compile(checkpointer=checkpointer)


def open_checkpointer(path=store.CHECKPOINT_PATH):
    store.os.makedirs(store.os.path.dirname(path), exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def config(sid):
    return {"configurable": {"thread_id": sid}}


def submit(app, rec):
    """추천을 넣고 끝까지 돌리거나 review 에서 멈춘다."""
    return app.invoke({"rec": rec}, config(rec["id"]))


def answer(app, sid, decision):
    """멈춘 건에 담당자 답을 넣어 이어간다."""
    return app.invoke(Command(resume={"approver": APPROVER, **decision}), config(sid))


def status_of(app, sid):
    """대기 / 공개 / 제외 / 처리 중"""
    snap = app.get_state(config(sid))
    if snap.next == ("review",):
        return "대기"
    s = snap.values.get("status")
    return {"published": "공개", "dropped": "제외"}.get(s, "처리 중")


if __name__ == "__main__":
    # 흐름 확인용: 칭찬형 1건(자동 공개), 놀림형 1건(멈춤 → 승인)
    import os
    import tempfile

    from judge import make_judge

    tmp = tempfile.mkdtemp()
    con = store.connect(os.path.join(tmp, "app.sqlite"))
    app = build_app(con, make_judge(), open_checkpointer(os.path.join(tmp, "cp.sqlite")))
    cases = [
        ("가은솔", "오태윤", "퍼실", "새벽에 올린 질문에도 아침마다 꼼꼼한 답을 달아 주셨어요"),
        ("바유진", "마시우", "수강생", "실습 시간마다 꾸벅꾸벅 졸다가 퍼실님께 세 번 걸림. 침 자국까지 목격됨"),
    ]
    for frm, to, role, reason in cases:
        sid = store.add_submission(con, frm, to, role, reason)
        rec = {"id": sid, "from": frm, "to": to, "to_role": role, "reason": reason}
        result = submit(app, rec)
        print(f"\n[{sid}] {frm} → {to}")
        print("  상:", result["award"]["title"], "/", result["award"]["citation"])
        j = result["judge"]
        print(f"  판정({j['engine']}, {j['latency']}s): 민망 {j['awkward']} · 사생활 {j['private']} · {j['tone']} {j['tone_conf']}")
        if "__interrupt__" in result:
            print("  ① 멈춤:", result["__interrupt__"][0].value["멈춘 이유"])
            print("  상태:", status_of(app, sid))
            result = answer(app, sid, {"action": "approve"})
            print("  ② 담당자 승인 →", result["status"])
        else:
            print("  자동 공개 →", result["status"])
        print("  상태:", status_of(app, sid))
    print("\n시상식 화면:", [(p["to_name"], p["title"], p["via"]) for p in store.published(con)])
    sys.exit(0)
