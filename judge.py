"""시상 문구 판정기. Jev가 기본이고, 키가 없거나 실패하면 대체 판정으로 넘어간다.

모두 같은 dict를 돌려준다.
{awkward, private, tone, tone_conf, tone_probs, engine, latency[, fallback_reason]}
"""
import os
import time

from pydantic import BaseModel, Field

# "민망하다"는 칭찬받을 때의 쑥스러움까지 포함해서 칭찬 문구도 높게 나왔다. 창피·불쾌로 좁힌다.
AWKWARD = "받는 사람이 동료들 앞에서 이 문구를 들으면 창피를 당하거나 기분이 상한다 (칭찬을 듣고 쑥스러운 것은 해당하지 않는다)"
AWKWARD_CRITERIA = {
    "true": "졸다가 걸린 일, 발표 실수, 지각 핑계처럼 본인이 숨기고 싶은 실수나 창피한 순간을 공개한다",
    "false": "노력, 도움, 성실함을 칭찬하거나, 누구나 웃어넘길 버릇을 애정 있게 말한다",
}
PRIVATE = "연애, 건강, 가족, 돈, 외모처럼 받는 사람이 공개하고 싶지 않을 사생활이 드러난다"
PRIVATE_CRITERIA = {
    "true": "연애 상대, 소개팅, 다이어트, 투자 손실, 가족 사정처럼 수업과 상관없는 개인 생활을 공개한다",
    "false": "수업, 과제, 실습, 발표, 팀 활동 안에서 있었던 일만 말한다",
}
TONE = "이 시상 문구의 성격"
TONE_CRITERIA = {
    "칭찬": "받는 사람의 노력이나 장점, 고마운 점을 높인다",
    "농담": "웃긴 버릇이나 개성을 애정 있게 말하고, 받는 사람을 깎아내리지 않는다",
    "조롱": "받는 사람의 실수나 창피한 순간을 드러내 웃음거리로 만든다",
}
TONES = list(TONE_CRITERIA)


def _text(award, rec):
    # 송년회 청중은 추천 사연을 이미 아는 동료들이다. 문구가 사연을 돌려 말해도 청중은 알아듣기 때문에
    # 사연(추천 이유)까지 함께 보여 주고, 공개되는 것은 상 이름과 문구라고 밝힌다.
    return (f"송년회에서 동료들 앞에서 아래 상 이름과 시상 문구를 읽는다. 동료들은 추천 사연을 알고 있다.\n"
            f"받는 사람: {rec['to']}\n추천 사연: {rec['reason']}\n"
            f"상 이름: {award['title']}\n시상 문구: {award['citation']}")


def _result(awkward, private, tone_probs, engine, started):
    tone = max(tone_probs, key=tone_probs.get)
    return {
        "awkward": round(float(awkward), 4),
        "private": round(float(private), 4),
        "tone": tone,
        "tone_conf": round(float(tone_probs[tone]), 4),
        "tone_probs": {k: round(float(v), 4) for k, v in tone_probs.items()},
        "engine": engine,
        "latency": round(time.perf_counter() - started, 2),
    }


class JevJudge:
    name = "jev"

    def __init__(self):
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        self.client = TypeSafeClient(retry=RetryPolicy(max_retries=2), timeout=30)

    def judge(self, award, rec):
        from typesafe_sdk import Choice, Noul

        started = time.perf_counter()
        res = self.client.system_one(
            state=_text(award, rec),
            questions={
                "awkward": Noul(instructions=AWKWARD, criteria=AWKWARD_CRITERIA),
                "private": Noul(instructions=PRIVATE, criteria=PRIVATE_CRITERIA),
                "tone": Choice(instructions=TONE, criteria=TONE_CRITERIA),
            },
            model="jev-latest",
        ).answers
        return _result(res["awkward"].noul, res["private"].noul, dict(res["tone"].probabilities), "jev", started)


class GPTDecision(BaseModel):
    awkward: float = Field(ge=0, le=1, description=AWKWARD + " 확률")
    private: float = Field(ge=0, le=1, description=PRIVATE + " 확률")
    tone: str = Field(description="칭찬 | 농담 | 조롱")
    tone_conf: float = Field(ge=0, le=1, description="tone 판정이 맞을 확률")


class GPTJudge:
    """Jev 키가 없을 때. 확률은 모델이 스스로 적어 내는 값이라 Jev보다 거칠다."""

    name = "gpt-5-nano"

    def __init__(self):
        from langchain_openai import ChatOpenAI

        self.llm = ChatOpenAI(model="gpt-5-nano", reasoning_effort="minimal", timeout=60, max_retries=2).with_structured_output(GPTDecision)

    def judge(self, award, rec):
        started = time.perf_counter()
        guide = "\n".join(f"- {k}: {v}" for k, v in TONE_CRITERIA.items())
        d = self.llm.invoke([("system", f"송년회 시상 문구를 검사한다. 각 항목의 확률을 0~1로 매긴다.\n성격 기준\n{guide}"),
                             ("human", _text(award, rec))])
        tone = d.tone.strip() if d.tone.strip() in TONES else "농담"
        rest = (1 - d.tone_conf) / (len(TONES) - 1)
        probs = {t: (d.tone_conf if t == tone else rest) for t in TONES}
        return _result(d.awkward, d.private, probs, self.name, started)


class KeywordJudge:
    """키가 하나도 없을 때 데모가 멈추지 않게 하는 마지막 대체 판정."""

    name = "keyword"
    MOCK = ["졸", "지각", "실수", "흑역사", "망", "침", "코골", "놀림", "결석", "버그"]
    PRIV = ["연애", "여자친구", "남자친구", "소개팅", "다이어트", "병원", "월급", "코인", "대출", "가족", "이별"]

    def judge(self, award, rec):
        started = time.perf_counter()
        text = award["title"] + award["citation"]
        mock = sum(k in text for k in self.MOCK)
        priv = sum(k in text for k in self.PRIV)
        probs = {"칭찬": 0.6, "농담": 0.3, "조롱": 0.1} if not mock else {"칭찬": 0.1, "농담": 0.4, "조롱": 0.5}
        return _result(min(1, 0.15 + 0.35 * mock), min(1, 0.05 + 0.5 * priv), probs, self.name, started)


class FallbackJudge:
    """앞에서부터 차례로 시도하고, 실패하면 다음 판정기로 넘긴다."""

    def __init__(self, judges):
        self.judges = judges
        self.name = judges[0].name

    def judge(self, award, rec):
        reasons = []
        for j in self.judges:
            try:
                result = j.judge(award, rec)
                if reasons:
                    result["fallback_reason"] = "; ".join(reasons)
                return result
            except Exception as e:  # 판정기 장애는 다음 판정기로 넘긴다
                reasons.append(f"{j.name}: {type(e).__name__}: {str(e)[:100]}")
        raise RuntimeError("모든 판정기가 실패했습니다: " + "; ".join(reasons))


def make_judge():
    judges = []
    if os.getenv("TYPESAFE_API_KEY"):
        judges.append(JevJudge())
    if os.getenv("OPENAI_API_KEY"):
        judges.append(GPTJudge())
    judges.append(KeywordJudge())
    return FallbackJudge(judges)
