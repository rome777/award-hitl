# 송년회 시상 승인 에이전트

**[데모 앱 바로가기](https://award-hitl.streamlit.app/)** · [설계와 결과 (REPORT.md)](REPORT.md) · [실행과 배포 (GUIDE.md)](GUIDE.md)

송년회 참석자 누구나 동료를 상에 추천하면, AI가 상 이름과 시상 문구를 쓰고 내보내도 되는지 판정합니다.
안전한 상은 바로 시상식 화면에 올라가고, 놀림이나 사생활이 섞인 상만 송년회 담당자에게 확인을 받습니다.

- 생성: OpenAI `gpt-5-nano` (2026-11-09 가격표 기준 가장 싼 텍스트 모델)
- 판정: TypeSafe **Jev** (창피·불쾌 확률, 사생활 노출 확률, 성격 판정)
- 멈추고 이어가기: LangGraph `interrupt` / `Command(resume=...)`, 체크포인터 `SqliteSaver`
- 데모: Streamlit

```mermaid
flowchart LR
    A([추천]) --> B[① gpt-5-nano<br/>문구 작성]
    B --> C{② Jev 판정}
    C -->|기준 통과| D([시상식 화면 공개])
    C -->|기준 걸림| E[담당자 대기함]
    E -->|승인 · 수정 후 승인| D
    E -.->|다시 쓰기| B
    E -->|빼기| F([제외])

    classDef input fill:#e5e7eb,stroke:#6b7280,color:#111827
    classDef ai fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef human fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef out fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    class A input
    class B,C ai
    class E human
    class D ok
    class F out

    linkStyle 0,1 stroke:#2563eb,stroke-width:2px
    linkStyle 2,4 stroke:#16a34a,stroke-width:2px
    linkStyle 3 stroke:#d97706,stroke-width:2px
    linkStyle 5 stroke:#2563eb,stroke-width:2px
    linkStyle 6 stroke:#dc2626,stroke-width:2px
```
