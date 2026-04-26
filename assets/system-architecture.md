# PawPal+ System Architecture

## Data flow

See [data-flow.md](data-flow.md) for the full Mermaid flowchart diagram.

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
