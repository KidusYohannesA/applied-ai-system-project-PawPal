"""End-to-end demo of the PawPal++ RAG-augmented AI advisor.

Runs 3 diverse pet/task combinations through the full pipeline
(retrieval → Claude Haiku 4.5 → schema validation) and prints
human-readable results. No Streamlit required — just run:

    python scripts/demo.py

Requires ANTHROPIC_API_KEY in .env (see README for setup).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pawpal_rag import suggest_task_defaults

# ── Demo cases ──────────────────────────────────────────────────────
# Each case mirrors a realistic user interaction in the Streamlit app.

DEMO_CASES = [
    {
        "description": "Adult Shiba Inu — daily morning walk",
        "pet": SimpleNamespace(name="Mochi", species="dog", breed="Shiba Inu", age=3),
        "task_title": "Morning walk",
    },
    {
        "description": "Senior Siamese cat — brushing / grooming",
        "pet": SimpleNamespace(name="Luna", species="cat", breed="Siamese", age=12),
        "task_title": "Brushing",
    },
    {
        "description": "Young Beagle — monthly heartworm prevention",
        "pet": SimpleNamespace(name="Charlie", species="dog", breed="Beagle", age=2),
        "task_title": "Heartworm prevention",
    },
]

SEPARATOR = "─" * 60


def run_demo():
    print()
    print("🐾 PawPal++ AI Advisor — End-to-End Demo")
    print("=" * 60)
    print()

    results = []

    for i, case in enumerate(DEMO_CASES, 1):
        pet = case["pet"]
        title = case["task_title"]

        print(f"  Case {i}: {case['description']}")
        print(f"  Pet:    {pet.name} ({pet.species}, {pet.breed}, {pet.age}yr)")
        print(f"  Task:   {title!r}")
        print()

        suggestion = suggest_task_defaults(pet, title)

        if suggestion is None:
            print("  ⚠  AI suggestion unavailable.")
            print("     Check that ANTHROPIC_API_KEY is set in .env")
            print()
            print(SEPARATOR)
            print()
            results.append(None)
            continue

        print(f"  ✅ AI Suggestion:")
        print(f"     Duration:  {suggestion.duration_minutes} minutes")
        print(f"     Priority:  {suggestion.priority}")
        print(f"     Frequency: {suggestion.frequency}")
        print(f"     Rationale: {suggestion.rationale}")
        print()

        if suggestion.citations:
            print(f"  📄 Citations ({len(suggestion.citations)}):")
            for c in suggestion.citations:
                src = c.get("source_name", "unknown")
                snippet = c.get("snippet", "")
                print(f"     • {src}: \"{snippet}\"")
        print()
        print(SEPARATOR)
        print()

        results.append(suggestion)

    # ── Summary table ───────────────────────────────────────────────
    successes = [r for r in results if r is not None]
    print(f"  Summary: {len(successes)}/{len(DEMO_CASES)} cases returned AI suggestions")
    print()

    if successes:
        print(f"  {'Case':<35} {'Duration':>8}  {'Priority':<8}  {'Frequency':<9}")
        print(f"  {'─'*35} {'─'*8}  {'─'*8}  {'─'*9}")
        for case, result in zip(DEMO_CASES, results):
            if result is None:
                continue
            label = case["description"][:35]
            print(
                f"  {label:<35} {result.duration_minutes:>5} min"
                f"  {result.priority:<8}  {result.frequency:<9}"
            )
        print()

    print("Done. These are the same suggestions a user sees when clicking")
    print("✨ AI suggest defaults in the Streamlit app.")
    print()


if __name__ == "__main__":
    run_demo()
