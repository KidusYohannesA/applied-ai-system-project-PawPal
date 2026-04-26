# PawPal++

[![Tests](https://github.com/KidusYohannesA/applied-ai-system-project-PawPal/actions/workflows/test.yml/badge.svg)](https://github.com/KidusYohannesA/applied-ai-system-project-PawPal/actions/workflows/test.yml)

**PawPal++**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Base Project vs. My Additions

This repository started from the **PawPal+ Module 2 starter** — a Streamlit pet-care planner with a deterministic priority/duration scheduler, conflict detection, recurring-task generation, and 28 unit tests. The original scope is everything described in its original repository: a fully working but **fully manual** scheduling app where the owner types in every duration, priority, and frequency themselves.

I extended it with a **RAG-augmented AI advisor** that meaningfully changes how task entry works.

| Layer | What was already there (base project) | What I added |
|---|---|---|
| **Data model** | `Owner`, `Pet`, `Task`, `Schedule` in [pawpal_system.py](pawpal_system.py) | Untouched — AI extension lives upstream |
| **Scheduling logic** | Priority + duration sort, conflict detection, recurrence, daily view | Untouched — all 28 original tests still pass |
| **Streamlit UI** | Add Pet / Add Task / Generate Schedule sections | Added breed + age inputs, **✨ AI suggest defaults** button, citations expander |
| **Knowledge base** | (none) | 17 curated markdown docs in [data/knowledge/](data/knowledge/) covering dogs, cats, age stages, medications, vet visits |
| **Retrieval** | (none) | ChromaDB persistent store (82 chunks) with `sentence-transformers/all-MiniLM-L6-v2` local embeddings, species-filtered top-k retrieval — see [pawpal_rag/](pawpal_rag/) |
| **LLM integration** | (none) | Anthropic `claude-haiku-4-5` advisor with strict tool-use schema, prompt caching on the system prompt, structured logging, graceful fallback when API key is missing |
| **Reliability / eval** | (none) | LLM-as-judge using `claude-sonnet-4-6` (see [pawpal_rag/judge.py](pawpal_rag/judge.py)), programmatic citation-grounding check, 8-case golden dataset in [tests/test_rag_quality.py](tests/test_rag_quality.py) |
| **Tests** | 28 deterministic unit tests | +11 RAG tests (mocked + 1 integration smoke) +9 LLM-as-judge eval cases = **48 total** |
| **CI** | (none) | GitHub Actions on Python 3.12 with pip caching — see [.github/workflows/test.yml](.github/workflows/test.yml) |

### Project layout

```
data/knowledge/           
data/chroma/              
pawpal_rag/
├── corpus.py            
├── store.py            
├── retriever.py         
├── prompts.py            
└── advisor.py           
scripts/build_index.py    # one-shot indexer
tests/test_rag.py        
```

### Where the AI is integrated

The AI advisor is wired directly into the **Add Task** flow ([app.py](app.py)) — when the owner clicks the suggest button, retrieved corpus chunks are sent to Claude, the validated suggestion **pre-fills the duration / priority / frequency widgets**, and the citations + rationale render in an expander. The owner can still edit and save. The deterministic `Schedule.schedule_tasks()` then operates on the AI-influenced `Task` objects exactly as it did before — no parallel "AI track" or print-the-data-alongside-a-standard-answer split.

See [assets/system-architecture.md](assets/system-architecture.md) for the full data-flow diagram and the four AI-output checkpoints (schema gate, programmatic grounding, LLM-as-judge, human review).

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. After pip install -r requirements.txt, create a .env file with your
#    Anthropic API key (.env is gitignored — never commit it).
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
# Then edit .env and replace sk-ant-... with your real key from
# console.anthropic.com

python scripts/build_index.py
```

### Run the app

```bash
streamlit run app.py
```



## AI Extension — RAG-Augmented Task Suggestions

PawPal+ ships with an AI advisor that suggests evidence-based defaults (duration, priority, frequency) when you add a new task. The advisor uses **Retrieval-Augmented Generation (RAG)** over a curated corpus of pet-care guidance and calls the Anthropic API (`claude-haiku-4-5`) with strict tool-use JSON schemas.

### System diagram

See [assets/system-architecture.md](assets/system-architecture.md) for the full Mermaid data-flow diagram, component legend, and the four checkpoints (schema gate · logging · human review · test suite) that verify AI output before it reaches the schedule.

### What it does

When you click **✨ AI suggest defaults** in the Add Task section, the system:

1. Retrieves the top 5 most relevant chunks from `data/knowledge/` (filtered by species)
2. Sends them to Claude along with the pet's species/breed/age and the task title
3. Receives a typed suggestion with `duration_minutes`, `priority`, `frequency`, a rationale, and source citations
4. Pre-fills the form fields — you can still edit before saving

### Reliability and error handling

The advisor degrades gracefully — it never crashes the app. If anything fails (missing API key, network error, malformed response), `suggest_task_defaults()` returns `None` and the UI shows a warning while the form stays usable.

All failure paths are logged to the `pawpal_rag.advisor` logger. To see what went wrong:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

Logged events include:
- Retrieval results (chunk count, query)
- Anthropic API errors (full traceback via `logger.exception`)
- Schema validation failures (which field, what value)
- Token usage per call (input, output, cache reads/writes)

### Testing the AI extension

```bash
# Unit + mocked tests (no API key needed)
python -m pytest tests/test_rag.py -v

# Real-API smoke test (requires ANTHROPIC_API_KEY)
python -m pytest tests/test_rag.py -v -m integration

# Full suite — verifies the original 28 tests still pass
python -m pytest tests/ -v
```

### Sample Interactions

The following examples are real outputs from `python scripts/demo.py`, which runs the full RAG pipeline (retrieval → Claude Haiku 4.5 → schema validation) end-to-end. No manual editing — these are exactly what the advisor returns.

#### Example 1: Adult Shiba Inu — Morning walk

```
Pet:    Mochi (dog, Shiba Inu, 3yr)
Task:   "Morning walk"

✅ AI Suggestion:
   Duration:  30 minutes
   Priority:  high
   Frequency: daily
   Rationale: Shiba Inus are medium-energy active breeds that require
              45-60 minutes of daily exercise, typically split into
              two sessions. A 30-minute morning walk is an appropriate
              half of the daily exercise regimen.

📄 Citations:
   • ASPCA & AKC general exercise guidance: "Active medium-energy breeds
     (Labrador Retriever, Golden Retriever, Shiba Inu, Beagle, Boxer)
     need 45-60 minutes of daily exercise."
```

#### Example 2: Senior Siamese cat — Brushing

```
Pet:    Luna (cat, Siamese, 12yr)
Task:   "Brushing"

✅ AI Suggestion:
   Duration:  10 minutes
   Priority:  low
   Frequency: weekly
   Rationale: Siamese cats have short coats and benefit from brushing
              1–2 times per week. At 12 years old, regular grooming
              helps maintain coat health and catch skin issues early.

📄 Citations:
   • AAFP grooming guidance: "Short-haired cats benefit from brushing
     1-2 times per week. Each session takes 5-10 minutes."
   • TICA / CFA breed reference: "Siamese: Short coat, weekly brushing."
```

#### Example 3: Young Beagle — Heartworm prevention

```
Pet:    Charlie (dog, Beagle, 2yr)
Task:   "Heartworm prevention"

✅ AI Suggestion:
   Duration:  2 minutes
   Priority:  high
   Frequency: monthly
   Rationale: Heartworm prevention must be given on the same day every
              month year-round. Missing a dose by more than ~2 weeks
              can break protection. Administration takes 1-2 minutes.

📄 Citations:
   • AVMA preventive medication guidance: "Heartworm prevention is given
     on the same day every month, year-round. Administration takes
     1-2 minutes. Recommended frequency=monthly, priority=high."
```

To reproduce these results yourself:

```bash
python scripts/demo.py                # AI advisor end-to-end (requires API key)
python scripts/demo_guardrails.py     # Guardrail demos (no API key needed)
```

## Design Decisions, Testing Results, and Reflection

See [model_card.md](model_card.md) for the full write-up covering:
- 8 design decisions with trade-off analysis
- Testing summary (48 tests, what worked, what didn't, lessons learned)
- Reflection on AI as a tool, reliability engineering, and knowledge curation
- Ethics: limitations, biases, and AI collaboration during development

---

# Demo Image: 
![Demo Image](assets/DemoImage.png)

# WalkThrough Video: 
![WalkThrough Video](assets/LoomWalkThrough.mp4)

