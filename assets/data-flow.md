```mermaid
flowchart TB
    User([👤 Owner])
    UI[Streamlit UI<br/>app.py]
    Advisor[pawpal_rag.advisor<br/>suggest_task_defaults]
    Retriever[retriever.py<br/>+ ChromaDB store]
    Corpus[(data/knowledge/<br/>17 markdown docs)]
    API[Anthropic API<br/>claude-haiku-4-5<br/>+ prompt caching]
    Validate{{_validate<br/>schema gate}}
    Suggestion[SuggestedDefaults<br/>duration · priority ·<br/>frequency · citations]
    Task[Task / Pet / Schedule<br/>pawpal_system.py<br/>deterministic, unchanged]
    Plan[Daily plan +<br/>conflict warnings]

    Tests[/tests/test_rag.py<br/>11 unit + 1 integration/]
    Logger((logger:<br/>pawpal_rag.advisor))

    %% EVAL LAYER (dev-time quality bar)
    Judge[pawpal_rag.judge<br/>check_citation_grounding<br/>+ judge_suggestion]
    JudgeAPI[Anthropic API<br/>claude-sonnet-4-6<br/>LLM-as-judge]
    QualityEval[/tests/test_rag_quality.py<br/>8 golden cases/]

    %% INPUT
    User -->|1 . enter pet + task title| UI
    UI -->|2 . click ✨ AI suggest| Advisor

    %% PROCESS
    Corpus -.->|build_index.py<br/>chunk on H2| Retriever
    Advisor -->|3 . species · breed · title| Retriever
    Retriever -->|4 . top-5 chunks| Advisor
    Advisor -->|5 . cached system prompt<br/>+ chunks + tool schema| API
    API -->|6 . tool_use response| Validate

    %% GATES
    Validate -->|✓ valid| Suggestion
    Validate -.->|✗ schema fail<br/>or API error| Fallback[/None → UI keeps<br/>safe defaults/]

    %% OUTPUT
    Suggestion -->|7 . pre-fill form| UI
    UI -->|8 . 👀 human review<br/>+ optional edit| User
    User -->|9 . click Add task| Task
    Task --> Plan
    Plan --> UI

    %% OBSERVABILITY OVERLAYS
    Advisor -.-> Logger
    API -.-> Logger
    Validate -.-> Logger
    Tests -.->|mocks Anthropic SDK<br/>asserts on payload| Advisor
    Tests -.->|@integration → real API| API

    %% EVAL FLOW (dev-time, not runtime)
    Suggestion -.->|advisor output +<br/>retrieved chunks| Judge
    Judge -->|programmatic<br/>grounding check| Judge
    Judge -->|pet + task + suggestion<br/>+ chunks| JudgeAPI
    JudgeAPI -->|judge_verdict<br/>score 1-5| QualityEval
    QualityEval -.->|range + grounding +<br/>judge assertions| Advisor

    classDef human fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#000
    classDef ai fill:#fce7f3,stroke:#be185d,color:#000
    classDef det fill:#dcfce7,stroke:#16a34a,color:#000
    classDef gate fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#000
    classDef obs fill:#fef3c7,stroke:#d97706,color:#000
    classDef store fill:#e0e7ff,stroke:#4338ca,color:#000

    class User,UI human
    class Advisor,API,Suggestion ai
    class Task,Plan det
    class Validate gate
    class Tests,Logger,Judge,JudgeAPI,QualityEval obs
    class Corpus,Retriever store
```
