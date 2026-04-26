# PawPal+ System Architecture

## Data flow

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

## Component legend

| Color | Layer | Components |
|---|---|---|
| 🔵 **Blue** | Human input + UI | Owner, Streamlit `app.py` |
| 🟣 **Pink** | AI / generation | Advisor, Anthropic API, returned suggestion |
| 🟢 **Green** | Deterministic core | `Task` / `Pet` / `Schedule` (untouched by AI extension) |
| 🟪 **Indigo** | Knowledge / retrieval | Markdown corpus, ChromaDB store, retriever |
| 🔴 **Red** | Quality gate | Schema validator (rejects malformed AI output) |
| 🟡 **Amber** | Observability + eval | Logger, unit/integration test suite, LLM-as-judge eval harness |

## Where humans + automated checks verify AI output

The system has **five checkpoints** between an AI response and a saved task:

1. **Schema gate** (`_validate` in [advisor.py](../pawpal_rag/advisor.py)) — rejects responses with out-of-range `duration_minutes`, invalid `priority`/`frequency` enums, or zero citations. Returns `None` → UI falls back to safe defaults.
2. **Logger** (`pawpal_rag.advisor`) — every retrieval, API call, validation failure, and token-usage event is logged. Failures aren't silent.
3. **Human review** — the AI only **pre-fills** the form. The owner sees the suggestion, the rationale, and citations, and can edit any field before clicking *Add task*. AI never writes to the schedule directly.
4. **Test suite** ([tests/test_rag.py](../tests/test_rag.py)) — 4 chunker tests verify corpus splitting and metadata extraction; 7 advisor tests (mocked Anthropic SDK) assert that bad schemas (invalid priority, out-of-range duration, missing citations, API errors) all return `None` without crashing; 1 real-API integration test verifies sensible suggestions for a known pet/task pair. 11 unit + 1 integration = 12 total.
5. **LLM-as-judge eval** ([tests/test_rag_quality.py](../tests/test_rag_quality.py)) — 8 golden-dataset cases each run through: (a) the real advisor (Haiku 4.5 + retrieval), (b) range/enum assertions, (c) programmatic citation-grounding via `check_citation_grounding()` in [judge.py](../pawpal_rag/judge.py), and (d) a Sonnet 4.6 judge that scores the suggestion 1–5 on five dimensions. Plus 1 model-identity check = 9 eval tests total.

## Step-by-step trace (numbered arrows above)

| # | Where | What happens |
|---|---|---|
| 1 | Owner → UI | Owner enters pet (species, breed, age) and types a task title |
| 2 | UI → Advisor | Click on **✨ AI suggest defaults** triggers `suggest_task_defaults(pet, title)` |
| 3 | Advisor → Retriever | Build query `"<species> <breed> <title>"` with species filter |
| 4 | Retriever → Advisor | ChromaDB returns top-5 most similar chunks with metadata |
| 5 | Advisor → API | Send cached system prompt + retrieved chunks + strict `suggest_defaults` tool schema |
| 6 | API → Validate | Tool-use response (typed JSON) flows into the schema gate |
| 7 | Suggestion → UI | Validated `SuggestedDefaults` pre-fills duration/priority/frequency widgets; rationale + citations shown in expander |
| 8 | UI → Owner | **Human-in-the-loop review** — owner can accept, edit, or ignore |
| 9 | Owner → Task | Click *Add task* creates a `Task` via the deterministic core (unchanged from v1) |

## Why the deterministic core is untouched

The original 28-test scheduling/conflict/recurrence logic in [pawpal_system.py](../pawpal_system.py) was deliberately **not** modified. The AI extension lives upstream of `Task.__init__` — it only changes what values the form is *initialized* with, not how the schedule is computed. This means:

- All 28 original tests still pass without modification.
- An offline app (no API key) is fully functional; the AI button just shows a warning.
- Every AI output is converted to standard `Task` fields, so downstream code doesn't need to know AI was involved.
