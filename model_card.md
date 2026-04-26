# PawPal++ Model Card

## Reflection

### AI is a tool

The biggest lesson from this project is that AI works best when you treat it like a powerful assistant. The advisor doesn't replace the owner's judgment, it only offers a starting point grounded in evidence. Every suggestion goes through a schema gate, shows its citations, and waits for human approval. The system is designed around the assumption that the AI will sometimes be wrong, and that's okay as long as the user can see why it made a choice and easily override it.

### Reliability is the hard part

Getting Claude to return a useful suggestion was the easy part. The harder work was everything around it, validating the output schema, catching API failures gracefully, verifying citations aren't fabricated, and building an eval pipeline that accounts for LLM non-determinism. The four guardrail layers took more code than the advisor itself. In production AI systems, the reliability is just as important as the product.

### RAG forces you to think about knowledge curation

Building the 17-doc knowledge base was surprisingly hard. Each document needed accurate content, proper species/topic metadata for filtered retrieval, and enough detail for the chunker to produce useful 800-char segments. Bad corpus documents can lead to bad suggestions regardless of how good the LLM is. I learned that in RAG systems, data quality matters more than model quality.

---

## Design Decisions and Trade-offs

### 1. AI lives upstream — the deterministic core is untouched

The AI advisor only **pre-fills form fields**; it never writes directly to `Task`, `Schedule`, or any downstream logic. This was deliberate: the original 28-test scheduling/conflict/recurrence engine in [pawpal_system.py](pawpal_system.py) is proven and stable. By keeping the AI extension upstream of `Task.__init__`, every original test still passes without modification, and an offline app (no API key) remains fully functional.

**Trade-off:** The AI can't do anything "smart" at scheduling time (e.g., auto-resolve conflicts or reorder tasks). It only influences *what values* the user starts with. I accepted this because it preserves the existing reliability guarantees and keeps the AI's blast radius small.

### 2. RAG over fine-tuning

I chose Retrieval-Augmented Generation over fine-tuning because:
- The knowledge base is small and domain-specific — RAG handles this well
- Citations are traceable back to specific corpus chunks, which is important for trust
- Updating guidance means editing a markdown file, not retraining a model

**Trade-off:** The advisor can only reference what's in the corpus. If a user enters a task that the docs don't cover, the system returns reasonable defaults but notes the limitation in its rationale. Fine-tuning could generalize better, but at the cost of maintainability.

### 3. Haiku 4.5 for production, Sonnet 4.6 for eval only

The advisor uses `claude-haiku-4-5` because suggestions run on every button click. The LLM-as-judge eval uses `claude-sonnet-4-6` because it only runs in the test suite, not at runtime.

**Trade-off:** Haiku occasionally produces slightly less nuanced rationales than Sonnet would, but the quality is sufficient for structured tool-use (duration/priority/frequency). The golden-dataset eval with Sonnet as judge ([test_rag_quality.py](tests/test_rag_quality.py)) verifies that Haiku's suggestions consistently score ≥3/5.

### 4. Local embeddings + cloud LLM

Embeddings use `sentence-transformers/all-MiniLM-L6-v2` running locally. Only the generation step requires an API call.

**Trade-off:** MiniLM is a smaller model than cloud embedding APIs, so retrieval quality is slightly lower. But for a 17-doc corpus, the simpler model is more than adequate, and it eliminates an external dependency.

### 5. Strict tool-use schema instead of free-form text

The advisor is forced to call the `suggest_defaults` tool via `tool_choice={"type": "tool", "name": "suggest_defaults"}` ([advisor.py line 121](pawpal_rag/advisor.py)). This guarantees structured JSON output rather than free-form text that would need parsing.

**Trade-off:** The LLM can't explain nuances outside the schema fields. But the structured output means `_validate()` can enforce exact constraints, and the UI can directly bind fields to widgets without parsing.

### 6. Human-in-the-loop — AI suggests, never auto-saves

The AI pre-fills form fields, but the user must click "Add task" to commit. The rationale and citations are shown in an expander so the user can evaluate the recommendation before accepting it.

**Trade-off:** Requires one extra click vs. auto-applying suggestions. But this ensures no bad AI output silently enters the schedule, which matters in a pet health context where incorrect medication frequencies could be harmful.

### 7. Graceful degradation — return None, never crash

Every failure path in [advisor.py](pawpal_rag/advisor.py) returns `None` rather than raising an exception. The UI checks for `None` and shows a warning while keeping the form usable with manual defaults. See `python scripts/demo_guardrails.py` for examples.

**Trade-off:** Failures are "silent" from the user's perspective (they just see "AI suggestion unavailable"). This is mitigated by structured logging (`pawpal_rag.advisor` logger) that captures every failure with full context for debugging.

### 8. Species-filtered retrieval

Retrieval queries include a ChromaDB metadata filter: `{"species": {"$in": [pet.species, "any"]}}`, so a dog query only retrieves dog specific + general docs.

**Trade-off:** Reduces recall a cat grooming tip that also applies to dogs won't surface for dog queries. But it significantly improves precision and prevents confusing cross-species citations.

---

## Testing Results

### 48 tests across 3 files

| File | Count | What it covers | API needed? |
|---|---|---|---|
| `test_pawpal.py` | 28 | Scheduling, conflict detection, recurrence, edge cases | No |
| `test_rag.py` | 11 + 1 | Chunker, advisor schema gate (mocked), 1 real-API smoke test | Mocked (1 needs key) |
| `test_rag_quality.py` | 8 + 1 | Golden-dataset eval: range checks → grounding → LLM judge | Yes |

Default run (`pytest tests/ -v`) executes 39 tests in ~0.04s (integration + eval tests are deselected by default via `pytest.ini` markers).

### What worked

- Mocked advisor tests caught real bugs early. `_validate()` rejects invalid priorities, out-of-range durations, and missing citations before they ever reached the UI.
- Golden-dataset eval with expected ranges handles LLM non-determinism well. All 8 cases pass consistently across runs.
- Programmatic citation grounding (`check_citation_grounding()`) catches fabricated snippets without needing an LLM call, fast and free.

### What initially didn't work

- Exact-match assertions on LLM output failed immediately. Claude returns slightly different durations and rationale phrasing on every run. Switching to range-based assertions solved this.
- Testing retrieval quality in CI was slow. ChromaDB, sentence-transformers takes ~30s to load on first run. The chunker tests verify corpus integrity without touching the vector store; retrieval is tested via the integration smoke test only.

### What I learned

- For LLM features, assert on schema compliance and value ranges, not exact strings. The `_validate()` gate is the real safety net.
- Separate fast tests from slow tests, using pytest markers keeps the default suite fast while still allowing deep quality checks on demand.

---

## Ethics and AI Collaboration

### Limitations and biases

The advisor's knowledge is limited to the 17 curated documents covering dogs and cats only. It has no knowledge of anything else, so queries for other species will return generic defaults that may not be appropriate. Additionally, the corpus skews toward common breeds, rare breeds receive less specific advice and the advisor falls back to general species-level guidance.

### Could the AI be misused?

The advisor suggests task *defaults* (duration, frequency, priority) — it does not do anything else. 
The main misuse risk is low given the domain (pet scheduling).

### What surprised me about reliability testing

The biggest surprise was how inconsistent LLM output is across identical calls. Running the same query (same pet, same task) five times returned durations of 30, 45, 30, 60, and 30 minutes, making it impossible to test with exact-match assertions. This forced me to redesign the entire eval approach around range-based assertions and schema compliance rather than expected values.

Another surprise was citation fabrication. Early in development, Claude occasionally returned citation snippets that sounded plausible but weren't in the retrieved chunks. The `check_citation_grounding()` function in `judge.py` was built specifically to catch this, verifying snippets appear verbatim in the context. Once added, it caught fabrications in some of the eval runs.

### AI collaboration during development

I used AI tools throughout this project for architecture planning, code generation, test design, and documentation.

When designing the reliability harness, the AI suggested using a *separate, stronger model* (Sonnet 4.6) as the judge instead of having the same model (Haiku 4.5) evaluate its own output. This multi-model approach avoids the self-evaluation bias where a model rates its own output favorably. I hadn't considered this and it became a core part of the evaluation pipeline.

Early on, the AI suggested embedding the entire knowledge base directly into the system prompt as context (no retrieval step). For 17 small documents this would have technically worked, but it would have blown past the prompt cache window, made the system impossible to scale, and eliminated the species-filtered retrieval that keeps citations relevant. I rejected this in favor of the RAG pipeline, which is more work to build but far more maintainable and precise.
