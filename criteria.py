"""멈춤 기준. graph.py(실제 판단)와 evaluate.py(기준 비교표)가 같은 함수를 쓴다.

기준은 모두 Jev가 시상 문구에 매긴 확률로 계산한다.
"""

DEFAULT = {
    "awkward": 0.4,    # 받는 사람이 창피하거나 기분 상할 확률이 이 값 이상이면 멈춤
    "private": 0.5,    # 사생활이 드러날 확률이 이 값 이상이면 멈춤
    "tone": True,      # 성격이 "조롱"이거나 성격 판정 확신도가 tone_conf 미만이면 멈춤
    "tone_conf": 0.6,
}


def stop_reasons(judge, th=None):
    """판정 결과(judge dict)가 걸린 기준을 사람이 읽을 문장으로 돌려준다. 빈 목록이면 자동 공개."""
    th = {**DEFAULT, **(th or {})}
    reasons = []
    if judge["awkward"] >= th["awkward"]:
        reasons.append(f"창피·불쾌 확률 {judge['awkward']:.2f} (기준 {th['awkward']} 이상)")
    if judge["private"] >= th["private"]:
        reasons.append(f"사생활 노출 확률 {judge['private']:.2f} (기준 {th['private']} 이상)")
    if th["tone"]:
        if judge["tone"] == "조롱":
            reasons.append(f"성격 판정 '조롱' (확신도 {judge['tone_conf']:.2f})")
        elif judge["tone_conf"] < th["tone_conf"]:
            reasons.append(f"성격 판정 확신도 {judge['tone_conf']:.2f} (기준 {th['tone_conf']} 미만)")
    return reasons
