# 실행과 배포

[README로 돌아가기](README.md)

## 실행

Python 3.10 이상.

```bash
python -m venv .venv
```

```bash
.venv/Scripts/pip install -r requirements.txt
```

macOS·Linux는 `.venv/bin/pip`을 씁니다. `.env.example`을 `.env`로 복사하고 키를 넣습니다. 키는 둘 다 선택입니다.

| 키 | 없으면 |
|---|---|
| `OPENAI_API_KEY` | 상 이름은 "올해의 동료상", 문구는 추천 이유를 그대로 씁니다 |
| `TYPESAFE_API_KEY` | Jev 대신 gpt-5-nano가 확률을 적어 내는 대체 판정을 씁니다. 둘 다 없으면 키워드 대체 판정 |

```bash
.venv/Scripts/streamlit run app.py
```

처음 실행하면 예시 추천 30건이 자동으로 들어갑니다 (1분쯤). 첫 화면은 담당자 대기함입니다.

- **추천하기**: 추천하는 사람, 받는 사람, 추천 이유가 무작위로 채워져 있습니다. 그대로 보내거나 고쳐서 보냅니다. "다른 추천으로 바꾸기"로 새로 뽑습니다. 한 사람당 2명까지.
- **담당자 대기함**: 기준에 걸린 상만 옵니다. 추천 원문, AI가 쓴 상, Jev 점수, 멈춘 이유, 승인하면 일어나는 일을 보고 답합니다.
- **시상식**: 공개된 상 카드. 송년회 당일 큰 화면용.
- **처리 기록**: 모든 추천의 처리 방식(자동 공개, 승인, 빼기 등)과 Jev 점수, 담당자 결정.
- 사이드바 **기록 모두 지우기**: 기록이 없으면 비활성. 지워도 예시를 다시 자동으로 채우지는 않습니다.
- 사이드바 **예시 추천 30건 넣기**: 예시가 이미 들어가 있으면 비활성. 지운 뒤에 다시 넣을 때 씁니다.

참석자 명단은 `data/attendees.json`(가상 이름 21명)을 씁니다. 다른 이름 세트 `data/*.example.json`으로 돌리려면 `streamlit run app.py -- --example`.

명령줄에서 흐름만 확인할 수도 있습니다 (칭찬형 1건 자동 공개, 놀림형 1건 멈춤 후 승인).

```bash
.venv/Scripts/python graph.py
```

## 공개 배포 (Streamlit Community Cloud)

저장소를 연결하고 Main file을 `app.py`로 둡니다. 앱 설정의 Secrets에 아래를 넣습니다.

```toml
OPENAI_API_KEY = "..."
TYPESAFE_API_KEY = "..."
PUBLIC_DEMO = "1"
AI_LIMIT_PER_IP = "5"
```

`PUBLIC_DEMO = "1"`이면 공개 데모 모드가 됩니다.

- AI를 부르는 동작(추천 보내기, 다시 쓰기)은 IP당 `AI_LIMIT_PER_IP`회까지. 승인, 수정, 빼기는 제한 없음
- 아무나 기록을 지우거나 AI를 30번 부르지 못하게 "기록 모두 지우기"와 "예시 추천 30건 넣기"를 끔
- IP는 `X-Forwarded-For` 헤더로 봅니다. 헤더는 꾸밀 수 있어서 비용을 줄이는 장치이지 완벽한 차단은 아닙니다
- Community Cloud의 파일은 앱이 다시 시작되면 지워집니다. 그때는 예시 30건으로 다시 시작합니다

## 기준 검증

```bash
.venv/Scripts/python evaluate.py
```

예시 30건을 한 번 생성·판정해 `results/judged.json`에 저장하고, 기준값 조합마다 개입률·놓침·헛멈춤을 세어
`results/criteria.md`에 표로 남깁니다. 기준값을 바꿔도 Jev를 다시 부르지 않습니다. `--refresh`로 다시 생성·판정합니다.

## 파일

| 파일 | 하는 일 |
|---|---|
| `graph.py` | LangGraph 파이프라인 (write → judge → review(interrupt) → publish / drop) |
| `writer.py` | gpt-5-nano로 상 이름·시상 문구 생성. 받는 사람 이름 누락, 내용 누락을 코드로 검사해 한 번 더 시킴 |
| `judge.py` | Jev 판정과 대체 판정 (gpt-5-nano, 키워드) |
| `criteria.py` | 멈춤 기준값과 `stop_reasons()`. 그래프와 평가가 같은 함수를 씀 |
| `store.py` | 추천, 공개된 상, 담당자 결정 기록 (SQLite) |
| `app.py` | Streamlit 데모 |
| `evaluate.py` | 기준 비교표 |
| `data/attendees.json` · `data/samples.json` | 참석자 21명(가상 이름), 예시 추천 30건 |
| `data/*.example.json` | 같은 구조의 다른 이름 세트 (보고서 캡처용) |
| `data/reasons.json` | 추천하기 화면의 무작위 추천 이유 40개 |
