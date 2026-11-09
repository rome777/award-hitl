"""멈춤 기준 비교표.

1) 예시 추천 30건을 write(gpt-5-nano) + judge(Jev) 로 한 번만 돌려 결과를 캐시한다.
2) 기준값 조합마다 개입률·놓침·헛멈춤을 세어 표로 만든다. 기준값을 바꿔도 Jev 를 다시 부르지 않는다.

  python evaluate.py            # 캐시가 없으면 만들고 표 생성
  python evaluate.py --refresh  # 캐시를 지우고 다시 판정
  python evaluate.py --example  # 실명 파일이 있어도 가상 이름 예시로

실명 파일(data/samples.json)이 있으면 그걸 쓰고 결과는 results/real/ 에 둔다 (git 제외).
"""
import argparse
import itertools
import json
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, ".env"))

from criteria import DEFAULT, stop_reasons  # noqa: E402
from judge import make_judge  # noqa: E402
from writer import write_award  # noqa: E402


def paths(example):
    real = os.path.join(ROOT, "data", "samples.json")
    if os.path.exists(real) and not example:
        return real, os.path.join(ROOT, "results", "real")
    return os.path.join(ROOT, "data", "samples.example.json"), os.path.join(ROOT, "results")


def run_samples(samples, out):
    judge = make_judge()

    def one(s):
        award = write_award(s)
        return {**s, "award": award, "judge": judge.judge(award, s)}

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, samples))
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rows


def measure(rows, th):
    stopped = missed = false_stop = 0
    for r in rows:
        did_stop = bool(stop_reasons(r["judge"], th))
        if did_stop:
            stopped += 1
            false_stop += not r["should_stop"]
        elif r["should_stop"]:
            missed += 1
    return stopped, missed, false_stop


def table(rows):
    n = len(rows)
    lines = ["| 창피·불쾌 기준 | 사생활 기준 | 성격 기준 | 개입률 | 놓침 | 헛멈춤 |", "|---|---|---|---|---|---|"]
    combos = [("기준 없음", {"awkward": 2, "private": 2, "tone": False})]
    combos.append(("전부 멈춤", {"awkward": 0, "private": 0, "tone": False}))
    for a, p, t in itertools.product([0.3, 0.4, 0.5, 0.6], [0.2, 0.3, 0.5, 0.7], [False, True]):
        combos.append((None, {"awkward": a, "private": p, "tone": t}))
    for label, th in combos:
        s, m, f = measure(rows, th)
        if label:
            lines.append(f"| {label} | | | {s}/{n} | {m}건 | {f}건 |")
        else:
            tone = f"조롱 또는 확신도<{DEFAULT['tone_conf']}" if th["tone"] else "끔"
            mark = " **(채택)**" if th == {k: DEFAULT[k] for k in ("awkward", "private", "tone")} else ""
            lines.append(f"| {th['awkward']} | {th['private']} | {tone}{mark} | {s}/{n} | {m}건 | {f}건 |")
    return "\n".join(lines)


def detail(rows):
    lines = ["| id | 유형 | 정답 | 상 | 창피·불쾌 | 사생활 | 성격 | 채택 기준 결과 |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        j = r["judge"]
        reasons = stop_reasons(j)
        got = "멈춤" if reasons else "자동"
        want = "멈춤" if r["should_stop"] else "자동"
        mark = "" if got == want else (" (놓침)" if want == "멈춤" else " (헛멈춤)")
        lines.append(f"| {r['id']} | {r['type']} | {want} | {r['award']['title']} | {j['awkward']:.2f} | {j['private']:.2f} | "
                     f"{j['tone']} {j['tone_conf']:.2f} | {got}{mark} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--example", action="store_true")
    args = ap.parse_args()
    src, out_dir = paths(args.example)
    os.makedirs(out_dir, exist_ok=True)
    cache = os.path.join(out_dir, "judged.json")
    samples = json.load(open(src, encoding="utf-8"))
    if args.refresh or not os.path.exists(cache):
        rows = run_samples(samples, cache)
    else:
        rows = json.load(open(cache, encoding="utf-8"))
    engines = sorted({r["judge"]["engine"] for r in rows})
    md = [f"# 멈춤 기준 비교 ({os.path.basename(src)}, {len(rows)}건, 판정: {', '.join(engines)})", "",
          "놓침 = 사람이 봤어야 하는데 자동으로 공개된 건. 헛멈춤 = 볼 필요 없는데 담당자에게 간 건.", "",
          table(rows), "", "## 건별 판정 (채택 기준)", "", detail(rows), ""]
    open(os.path.join(out_dir, "criteria.md"), "w", encoding="utf-8").write("\n".join(md))
    s, m, f = measure(rows, DEFAULT)
    print(f"채택 기준: 개입 {s}/{len(rows)}, 놓침 {m}, 헛멈춤 {f} → {os.path.join(out_dir, 'criteria.md')}")


if __name__ == "__main__":
    main()
