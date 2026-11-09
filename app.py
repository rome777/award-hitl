"""송년회 시상 승인 데모 (Streamlit).

탭: 추천하기(참석자 누구나) / 담당자 대기함(송년회 담당자, 첫 화면) / 시상식(당일 큰 화면) / 처리 기록
"""
import html
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

if "--example" in sys.argv:  # streamlit run app.py -- --example : 가상 이름 예시 모드
    os.environ["AWARD_EXAMPLE"] = "1"

import graph  # noqa: E402  (store 가 위 환경변수를 읽고 경로를 정한다)
import store  # noqa: E402
from criteria import DEFAULT  # noqa: E402
from judge import make_judge  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_PER_PERSON = 2
# 공개 배포(Streamlit Cloud Secrets 에 PUBLIC_DEMO = "1")에서는 IP당 AI 호출을 제한하고, 지우기·예시 넣기를 끈다
PUBLIC = os.getenv("PUBLIC_DEMO") == "1"
AI_LIMIT = int(os.getenv("AI_LIMIT_PER_IP", "5"))

st.set_page_config(page_title="송년회 시상 승인", layout="wide")
st.markdown("""
<style>
.award-card {border:1px solid #d6c08a; border-radius:14px; padding:22px 26px; margin-bottom:16px;
  background:linear-gradient(135deg,#fffaf0,#fdf1d6); color:#3b2a10;}
.award-card .to {font-size:0.95rem; color:#8a6d2f; margin-bottom:4px;}
.award-card .title {font-size:1.7rem; font-weight:800; margin-bottom:8px;}
.award-card .cit {font-size:1.1rem; line-height:1.6;}
.award-card .via {font-size:0.8rem; color:#a08850; margin-top:10px;}
.preview {border-left:5px solid #c9a24b; padding:10px 16px; background:rgba(201,162,75,0.08); border-radius:6px;}
.preview .title {font-size:1.3rem; font-weight:700;}
</style>
""", unsafe_allow_html=True)


def load_json(name):
    real = os.path.join(ROOT, "data", f"{name}.json")
    path = real if os.path.exists(real) and not store.EXAMPLE else os.path.join(ROOT, "data", f"{name}.example.json")
    return json.load(open(path, encoding="utf-8"))


@st.cache_resource
def resources():
    con = store.connect()
    saver = graph.open_checkpointer()
    judge = make_judge()
    return con, saver, judge, graph.build_app(con, judge, saver)


con, saver, judge, app = resources()
attendees = load_json("attendees")
people = attendees["people"]
role_of = {p["name"]: p["role"] for p in people}
REASONS = json.load(open(os.path.join(ROOT, "data", "reasons.json"), encoding="utf-8"))


def run_submission(frm, to, reason):
    sid = store.add_submission(con, frm, to, role_of[to], reason)
    rec = {"id": sid, "from": frm, "to": to, "to_role": role_of[to], "reason": reason}
    graph.submit(app, rec)
    return sid


def insert_samples(progress=None):
    samples = load_json("samples")
    done = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(run_submission, x["from"], x["to"], x["reason"]) for x in samples]
        for f in futures:
            f.result()
            done += 1
            if progress:
                progress(done, len(samples))


@st.cache_resource(show_spinner="처음 실행이라 예시 추천 30건을 넣는 중입니다 (1분쯤 걸려요)")
def seed_once():
    """처음 실행할 때 한 번만 예시를 넣는다. 이미 기록이 있으면 넣지 않고 표시만 남긴다."""
    if store.get_meta(con, "seeded"):
        return
    if not store.submissions(con):
        insert_samples()
    store.set_meta(con, "seeded", 1)


seed_once()


def all_rows():
    rows = []
    for s in store.submissions(con):
        snap = app.get_state(graph.config(s["id"]))
        rows.append({**s, "state": snap.values, "status": graph.status_of(app, s["id"])})
    return rows


def esc(x):
    return html.escape(str(x))


def client_ip():
    """프록시 뒤에서는 X-Forwarded-For 의 첫 주소가 사용자 IP다. 헤더는 꾸밀 수 있어 완벽한 제한은 아니다."""
    try:
        xff = st.context.headers.get("X-Forwarded-For", "")
        ip = xff.split(",")[0].strip() if isinstance(xff, str) and xff else st.context.ip_address
    except Exception:  # 테스트 환경 등 요청 정보가 없을 때
        ip = None
    return ip if isinstance(ip, str) and ip else "local"


IP = client_ip()


def ai_left():
    return AI_LIMIT - store.usage(con, IP) if PUBLIC else None


rows = all_rows()
pending = [r for r in rows if r["status"] == "대기"]

# ── 사이드바 ──────────────────────────────────────────
with st.sidebar:
    st.header("송년회 시상 승인")
    engine = judge.name
    st.caption(f"생성: gpt-5-nano{' (키 없음: 추천 원문 사용)' if not os.getenv('OPENAI_API_KEY') else ''}")
    st.caption(f"판정: {'Jev' if engine == 'jev' else engine + ' (대체 판정)'}")
    st.caption(f"승인: {graph.APPROVER} (데모를 쓰는 아무나)")
    st.caption(f"승인 대기: {len(pending)}건")
    if PUBLIC:
        st.caption(f"AI 사용 가능: {max(ai_left(), 0)}/{AI_LIMIT}회 (추천 보내기, 다시 쓰기. 공개 데모라 IP당 제한)")
    st.caption(f"멈춤 기준: 창피·불쾌 ≥ {DEFAULT['awkward']} · 사생활 ≥ {DEFAULT['private']} · "
               f"성격 '조롱' 또는 확신도 < {DEFAULT['tone_conf']}")
    st.divider()
    samples_in = store.has_samples(con, load_json("samples"))
    empty = not store.submissions(con)
    if st.button("예시 추천 30건 넣기", width="stretch", disabled=samples_in or PUBLIC,
                 help="공개 데모에서는 꺼 둡니다" if PUBLIC else ("이미 들어가 있습니다" if samples_in else None)):
        bar = st.progress(0.0, text="추천 처리 중")
        insert_samples(lambda d, n: bar.progress(d / n, text=f"추천 처리 중 {d}/{n}"))
        st.rerun()
    if st.button("기록 모두 지우기", width="stretch", disabled=empty or PUBLIC,
                 help="공개 데모에서는 꺼 둡니다" if PUBLIC else ("지울 기록이 없습니다" if empty else None)):
        for s in store.submissions(con):
            saver.delete_thread(s["id"])
        store.reset(con)
        st.rerun()

# 탭 이름에 건수를 넣으면 건수가 바뀔 때 탭이 새로 그려져 첫 탭으로 돌아간다. 이름은 고정하고 key 로 선택을 기억한다
tab_rec, tab_queue, tab_show, tab_log = st.tabs(["추천하기", "담당자 대기함", "시상식", "처리 기록"],
                                                default="담당자 대기함", key="tab")

# ── 추천하기 ──────────────────────────────────────────
names = [p["name"] for p in people]


def reroll():
    """추천하는 사람, 받는 사람, 추천 이유를 무작위로 채운다. 추천 한도가 남은 사람 중에서 고른다."""
    left = [n for n in names if store.count_from(con, n) < MAX_PER_PERSON] or names
    frm = random.choice(left)
    st.session_state["frm"] = frm
    st.session_state["to"] = random.choice([n for n in names if n != frm])
    st.session_state["reason"] = random.choice(REASONS)


if "frm" not in st.session_state:
    reroll()

with tab_rec:
    st.subheader("동료를 상에 추천해 주세요")
    st.caption(f"모두가 추천할 수 있고 모두가 상을 받을 수 있습니다. 한 사람당 {MAX_PER_PERSON}명까지. "
               "상 이름과 시상 문구는 AI가 써 드립니다.")
    st.button("다른 추천으로 바꾸기", on_click=reroll)
    c1, c2 = st.columns(2)
    frm = c1.selectbox("추천하는 사람", names, key="frm")
    to_options = [n for n in names if n != frm]
    if st.session_state.get("to") not in to_options:
        st.session_state["to"] = to_options[0]
    to = c2.selectbox("받는 사람", to_options, key="to")
    reason = st.text_area("추천 이유", key="reason")
    used = store.count_from(con, frm)
    st.caption(f"{frm}님 추천 {used}/{MAX_PER_PERSON}")
    no_ai = PUBLIC and ai_left() <= 0
    if no_ai:
        st.caption(f"이 IP의 AI 사용 횟수({AI_LIMIT}회)를 다 썼습니다.")
    if st.button("추천 보내기", type="primary", disabled=used >= MAX_PER_PERSON or not reason.strip() or no_ai):
        if PUBLIC:
            store.add_usage(con, IP)
        with st.spinner("상 이름과 문구를 쓰고 검사하는 중"):
            sid = run_submission(frm, to, reason.strip())
        award = app.get_state(graph.config(sid)).values["award"]
        if graph.status_of(app, sid) == "공개":
            st.session_state["flash"] = ("success", f"'{award['title']}'이 시상식 화면에 바로 올라갔습니다.")
        else:
            st.session_state["flash"] = ("info", f"'{award['title']}'은 담당자 확인 후 공개됩니다.")
        st.rerun()
    if "flash" in st.session_state:
        kind, msg = st.session_state.pop("flash")
        getattr(st, kind)(msg)

# ── 담당자 대기함 ─────────────────────────────────────
with tab_queue:
    st.subheader(f"승인 대기 {len(pending)}건")
    st.caption("기준에 걸린 상만 여기로 옵니다. 나머지는 자동으로 공개됩니다. 승인은 송년회 담당자 누구나 할 수 있습니다.")
    if not pending:
        st.write("기다리는 건이 없습니다.")
    else:
        left, right = st.columns([1, 2.2])
        labels = {r["id"]: f"{r['to_name']} · {r['state']['award']['title']}" for r in pending}
        sid = left.radio("대기 목록", list(labels), format_func=labels.get, label_visibility="collapsed")
        r = next(x for x in pending if x["id"] == sid)
        s = r["state"]
        rec, award, j = s["rec"], s["award"], s["judge"]
        left_rewrites = graph.MAX_REWRITES - s.get("rewrites", 0)
        with right:
            st.markdown("**추천 원문**")
            st.write(f"{rec['from']} → {rec['to']} ({rec['to_role']}): {rec['reason']}")
            st.markdown("**AI가 쓴 상**")
            st.markdown(f"<div class='preview'><div class='title'>{esc(award['title'])}</div>"
                        f"<div>{esc(award['citation'])}</div></div>", unsafe_allow_html=True)
            st.markdown("**판정 (Jev)**" if j["engine"] == "jev" else f"**판정 ({j['engine']}, 대체 판정)**")
            m1, m2, m3 = st.columns(3)
            m1.metric("창피·불쾌", f"{j['awkward']:.2f}")
            m1.caption(f"{DEFAULT['awkward']} 이상이면 멈춤")
            m2.metric("사생활 노출", f"{j['private']:.2f}")
            m2.caption(f"{DEFAULT['private']} 이상이면 멈춤")
            m3.metric("성격", j["tone"])
            m3.caption(f"확신도 {j['tone_conf']:.2f} · 조롱이거나 확신도 {DEFAULT['tone_conf']} 미만이면 멈춤")
            st.caption("성격 확률: " + " · ".join(f"{k} {v:.2f}" for k, v in j["tone_probs"].items()))
            st.warning("멈춘 이유: " + " / ".join(s["stop_reasons"] or ["다시 쓴 문구 확인"]))
            st.info(f"승인하면: 시상식 화면에 '{award['title']}'이 {rec['to']}님 이름으로 공개됩니다. 공개된 뒤에는 되돌릴 수 없습니다.")

            b1, b2 = st.columns(2)
            if b1.button("승인", type="primary", width="stretch", key=f"ok_{sid}"):
                graph.answer(app, sid, {"action": "approve"})
                st.rerun()
            with b2.popover("빼기", width="stretch"):
                why = st.text_input("뺀 이유 (필수)", key=f"why_{sid}")
                if st.button("이 상 빼기", disabled=not why.strip(), key=f"drop_{sid}"):
                    graph.answer(app, sid, {"action": "drop", "reason": why.strip()})
                    st.rerun()
            with st.expander("수정 후 승인"):
                new_title = st.text_input("상 이름", award["title"], key=f"t_{sid}")
                new_text = st.text_area("시상 문구", award["citation"], key=f"c_{sid}")
                if st.button("고친 문구로 승인", key=f"edit_{sid}"):
                    graph.answer(app, sid, {"action": "edit", "title": new_title.strip(), "text": new_text.strip()})
                    st.rerun()
            with st.expander(f"다시 쓰기 (남은 횟수 {left_rewrites})"):
                ins = st.text_input("AI에게 줄 지시", placeholder="예: 실수 얘기는 빼고 성실함을 칭찬하는 쪽으로", key=f"i_{sid}")
                no_ai = PUBLIC and ai_left() <= 0
                if no_ai:
                    st.caption(f"이 IP의 AI 사용 횟수({AI_LIMIT}회)를 다 썼습니다.")
                if st.button("이 지시로 다시 쓰기", disabled=left_rewrites <= 0 or not ins.strip() or no_ai, key=f"rw_{sid}"):
                    if PUBLIC:
                        store.add_usage(con, IP)
                    with st.spinner("다시 쓰는 중"):
                        graph.answer(app, sid, {"action": "rewrite", "instruction": ins.strip()})
                    st.rerun()

# ── 시상식 ───────────────────────────────────────────
with tab_show:
    pubs = store.published(con)
    st.subheader(f"2026 송년회 시상식 · {len(pubs)}개의 상")
    cols = st.columns(2)
    for i, p in enumerate(pubs):
        cols[i % 2].markdown(
            f"<div class='award-card'><div class='to'>{esc(p['to_name'])} {esc(role_of.get(p['to_name'], ''))}</div>"
            f"<div class='title'>{esc(p['title'])}</div><div class='cit'>{esc(p['citation'])}</div>"
            f"<div class='via'>{esc(p['via'])}</div></div>", unsafe_allow_html=True)

# ── 처리 기록 ─────────────────────────────────────────
with tab_log:
    counts = {k: sum(r["status"] == k for r in rows) for k in ("공개", "대기", "제외")}
    auto = sum(1 for p in store.published(con) if p["via"] == "자동")
    st.subheader("처리 기록")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("전체 추천", len(rows))
    c2.metric("자동 공개", auto)
    c3.metric("사람이 처리", counts["공개"] - auto + counts["제외"])
    c4.metric("대기 중", counts["대기"])
    via = {p["id"]: p["via"] for p in store.published(con)}
    ACTION = {"approve": "승인", "edit": "수정 후 승인", "drop": "빼기", "rewrite": "다시 쓰기"}

    def how(r):
        if r["status"] == "공개":
            return "자동 공개" if via.get(r["id"]) == "자동" else via.get(r["id"], "")
        return {"대기": "담당자 확인 대기", "제외": "담당자가 뺌"}.get(r["status"], r["status"])

    show = st.radio("보기", ["전체", "자동 공개", "기준에 걸린 건"], horizontal=True)
    table = []
    for r in rows:
        s = r["state"]
        j = s.get("judge") or {}
        stopped = bool(s.get("stop_reasons")) or s.get("rewrites", 0) > 0 or r["status"] in ("대기", "제외") \
            or via.get(r["id"], "자동") != "자동"
        if show == "자동 공개" and stopped or show == "기준에 걸린 건" and not stopped:
            continue
        table.append({
            "추천": f"{r['from_name']} → {r['to_name']}", "추천 이유": r["reason"],
            "상": (s.get("award") or {}).get("title", ""), "처리": how(r),
            "창피·불쾌": j.get("awkward"), "사생활": j.get("private"),
            "성격": f"{j.get('tone', '')} {j.get('tone_conf', 0):.2f}" if j else "",
            "멈춘 이유": " / ".join(s.get("stop_reasons") or []),
        })
    st.dataframe(table, width="stretch", hide_index=True,
                 column_config={"창피·불쾌": st.column_config.NumberColumn(format="%.2f"),
                                "사생활": st.column_config.NumberColumn(format="%.2f")})
    st.markdown("**담당자 결정**")
    names_by_id = {r["id"]: f"{r['from_name']} → {r['to_name']}" for r in rows}
    st.dataframe([{"시각": d["at"], "추천": names_by_id.get(d["id"], d["id"]), "결정": ACTION.get(d["action"], d["action"]),
                   "승인자": d["approver"], "내용": " / ".join(f"{k}: {v}" for k, v in d["detail"].items())}
                  for d in store.decisions(con)], width="stretch", hide_index=True)
