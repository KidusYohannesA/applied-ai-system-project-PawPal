# PawPal+ (Module 2 Project)

[![Tests](https://github.com/KidusYohannesA/applied-ai-system-project-PawPal/actions/workflows/test.yml/badge.svg)](https://github.com/KidusYohannesA/applied-ai-system-project-PawPal/actions/workflows/test.yml)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## Features

- **Priority-based scheduling** — Tasks are sorted by priority (high > medium > low), with shorter tasks scheduled first at the same level, then assigned back-to-back starting at a configurable hour
- **Chronological sorting** — `get_tasks_by_time()` sorts tasks by start time using `datetime.max` as a sentinel so unscheduled tasks always appear last
- **Conflict detection** — `detect_conflicts()` runs a sweep-line pass over sorted tasks, flagging any pair where the next task starts before the current one ends
- **Recurring task generation** — `mark_complete()` uses a frequency-to-timedelta lookup (`daily` = 1 day, `weekly` = 7 days, `monthly` = 30 days) to auto-create the next occurrence on the same pet
- **Daily view filtering** — `get_daily_view()` filters all tasks down to a single date, comparing the date component of each task's `datetime` start time
- **Computed end times** — End times are calculated on the fly via `get_end_time()` (`start_time + duration`), avoiding stored state that can drift out of sync
- **Cross-pet task aggregation** — Schedule dynamically collects tasks from all pets through `_all_tasks()`, so adding or removing a pet's task is immediately reflected everywhere
- **Schedule explanation** — `get_explanation()` produces a numbered, human-readable summary of each task with pet name, time window, priority, and frequency

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Smarter Scheduling

The scheduler has been enhanced with several algorithmic improvements:

- **Priority + duration sorting** — Tasks are scheduled by priority (high first), with shorter tasks before longer ones at the same level. Quick critical tasks like medication won't get stuck behind a long walk.
- **Completed task filtering** — Finished tasks are automatically excluded from scheduling so they don't waste time slots.
- **Datetime-based time handling** — Times are stored as `datetime` objects internally instead of strings, eliminating repeated parsing and enabling safe date comparisons.
- **Chronological ordering** — `get_tasks_by_time()` returns tasks sorted by start time for display, with unscheduled tasks placed at the end.
- **Recurring task auto-creation** — When a daily, weekly, or monthly task is marked complete, a new pending task is automatically created with its start time advanced to the next occurrence.
- **Conflict detection** — `detect_conflicts()` uses a sweep-line algorithm to find overlapping task windows across all pets and returns warning messages for each conflict.

## Testing PawPal+

```bash
python -m pytest tests/test_pawpal.py -v
```

The test suite (28 tests) covers the following areas:

- **Sorting correctness** — tasks are returned in chronological order by start time, and `schedule_tasks()` sorts by priority then duration
- **Recurrence logic** — completing a daily, weekly, or monthly task creates a new pending task advanced to the next occurrence, including chained completions
- **Conflict detection** — overlapping time windows are flagged across different pets and on the same pet, with boundary precision (off-by-one minute)
- **Edge cases** — zero-duration tasks, recurring tasks with no start time or no pet, midnight boundaries in daily view, duplicate pet names in the registry, and silent no-ops for orphan tasks

**Confidence Level: 4/5 stars**
The core scheduling, recurrence, and conflict logic is well-covered. One star is withheld because input validation (malformed time strings, invalid priority values) is not enforced by the system and therefore not tested defensively.

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run the app

```bash
streamlit run app.py
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

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

### Setup (one extra step beyond the base app)

```bash
# 1. After pip install -r requirements.txt, create a .env file with your
#    Anthropic API key (.env is gitignored — never commit it).
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
# Then edit .env and replace sk-ant-... with your real key from
# console.anthropic.com

# 2. (Optional) Build the vector store explicitly. If skipped, it builds
#    automatically on first AI suggestion.
python scripts/build_index.py
```

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

### Project layout (AI extension)

```
data/knowledge/           # 17 curated markdown docs (dogs, cats, general)
data/chroma/              # vector store (auto-built; gitignored)
pawpal_rag/
├── corpus.py             # markdown loader + heading-aware chunker
├── store.py              # ChromaDB persistent store (lazy chromadb import)
├── retriever.py          # retrieve(query, k, where)
├── prompts.py            # system prompt + suggest_defaults tool schema
└── advisor.py            # suggest_task_defaults() — Anthropic call + validation
scripts/build_index.py    # one-shot indexer
tests/test_rag.py         # 11 tests (chunker, mocked advisor, integration smoke)
```

### Testing the AI extension

```bash
# Unit + mocked tests (no API key needed)
python -m pytest tests/test_rag.py -v

# Real-API smoke test (requires ANTHROPIC_API_KEY)
python -m pytest tests/test_rag.py -v -m integration

# Full suite — verifies the original 28 tests still pass
python -m pytest tests/ -v
```

## 📸 Demo
Screenshot of App:

![PawPal+ Demo](../streamlitdemo.png)

