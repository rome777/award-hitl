"""추천 한 건으로 상 이름과 시상 문구를 하나 쓴다 (gpt-5-nano).

OpenAI 키가 없으면 추천 이유를 문구로 그대로 쓴다.
"""
import os

from pydantic import BaseModel, Field

MODEL = "gpt-5-nano"  # 2026-11-09 OpenAI 가격표 기준 가장 싼 텍스트 모델

SYSTEM = """너는 송년회 시상식 문구를 쓰는 사람이다. 동료가 보낸 추천 한 건을 읽고 상 하나를 만든다.

규칙
- title: "○○상" 꼴의 상 이름 하나. 10자 이내. 추천 내용이 바로 떠오르게 짓는다.
- citation: 시상식에서 사회자가 읽을 문구. 두 문장, 40~90자. 첫 문장은 추천에 적힌 구체적인 일을 그대로 담고, 둘째 문장은 "○○님께 이 상을 드립니다"로 끝낸다.
- 추천에 적힌 사실과 분위기를 그대로 살린다. 추천에 없는 사실을 지어내지 않는다.
- 추천이 놀리는 내용이어도 순화하거나 빼거나 칭찬으로 바꾸지 않는다. 내보내도 되는지는 다음 단계에서 따로 검사한다.
- 담당자 지시가 있으면 그 지시를 가장 먼저 따른다.

예시
추천 이유: 회의 때마다 노트북 배터리가 꺼져서 매번 충전기를 빌림
title: 충전기 대여상
citation: 회의 때마다 배터리가 꺼져 충전기를 빌리러 다니셨습니다. 홍길동님께 이 상을 드립니다.

추천 이유: 팀원이 막힐 때마다 밤늦게까지 같이 디버깅해 줌
title: 야간 디버깅상
citation: 팀원이 막힐 때마다 밤늦게까지 함께 디버깅해 주셨습니다. 홍길동님께 이 상을 드립니다."""

MIN_BODY = 15  # "~님께 이 상을 드립니다"를 뺀 본문이 이보다 짧으면 추천 내용이 빠진 것으로 본다


class Award(BaseModel):
    title: str = Field(description="상 이름")
    citation: str = Field(description="시상 문구")


_llm = None


def _model():
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI

        # 추론 토큰도 출력 단가로 과금되므로 추론을 최소로 둔다
        _llm = ChatOpenAI(model=MODEL, reasoning_effort="minimal", timeout=60, max_retries=2).with_structured_output(Award)
    return _llm


def write_award(rec, instruction=None, previous=None):
    """rec: {"from", "to", "to_role", "reason"} → {"title", "citation", "engine"}"""
    if not os.getenv("OPENAI_API_KEY"):
        return {"title": "올해의 동료상", "citation": f"{rec['to']}님, {rec['reason']}", "engine": "없음(추천 원문)"}
    # 추천한 사람 이름은 넣지 않는다. 넣었더니 "추천한 사람님께 이 상을 드립니다"로 이름을 바꿔 쓰는 일이 있었다
    lines = [
        f"받는 사람: {rec['to']} ({rec.get('to_role', '수강생')})",
        f"추천 이유: {rec['reason']}",
    ]
    if previous:
        lines.append(f"이전에 쓴 문구: {previous['title']} / {previous['citation']}")
    if instruction:
        lines.append(f"담당자 지시: {instruction}")
    messages = [("system", SYSTEM), ("human", "\n".join(lines))]
    award = _model().invoke(messages)
    # 싼 모델의 실수를 코드로 검사하고 한 번 더 시킨다
    problem = _check(award, rec)
    if problem:
        messages += [("ai", f"title: {award.title}\ncitation: {award.citation}"), ("human", problem + " 고쳐서 다시 써라.")]
        award = _model().invoke(messages)
    return {"title": award.title.strip(), "citation": award.citation.strip(), "engine": MODEL}


def _check(award, rec):
    if rec["to"] not in award.citation:
        return f"citation 에 받는 사람 이름 '{rec['to']}'이 없다."
    if _body_len(award.citation, rec["to"]) < MIN_BODY:
        return "citation 첫 문장에 추천 이유에 적힌 구체적인 일이 빠졌다."
    return ""


def _body_len(citation, name):
    body = citation.replace(name, "")
    for tail in ("님께 이 상을 드립니다", "수강생님께 이 상을 드립니다", "퍼실님께 이 상을 드립니다", "님", "."):
        body = body.replace(tail, "")
    return len(body.strip())
