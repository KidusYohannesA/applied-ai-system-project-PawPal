import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pawpal_rag.corpus import chunk_markdown, load_corpus


# ── Chunker (no API, no store) ──────────────────────────────────────


def test_chunker_splits_on_h2():
    md = """---
species: dog
topic: exercise
---

## Section A
Content of section A goes here.

## Section B
Content of section B goes here.
"""
    chunks = chunk_markdown(md, source_file="test.md")
    assert len(chunks) == 2
    assert "Section A" in chunks[0].text
    assert "Section B" in chunks[1].text


def test_chunker_preserves_metadata():
    md = """---
species: cat
topic: feeding
source_url: https://example.com/cat-feeding
source_name: Example Cat Source
---

## Adult cat meal frequency
Twice a day is best.
"""
    chunks = chunk_markdown(md, source_file="cats/feeding.md")
    assert len(chunks) == 1
    meta = chunks[0].metadata
    assert meta["species"] == "cat"
    assert meta["topic"] == "feeding"
    assert meta["source_url"] == "https://example.com/cat-feeding"
    assert meta["source_name"] == "Example Cat Source"
    assert meta["source_file"] == "cats/feeding.md"
    assert meta["heading"].startswith("Adult cat meal frequency")


def test_chunker_handles_long_section_with_window():
    big = "x" * 2000
    md = f"""---
species: dog
---

## Long section
{big}
"""
    chunks = chunk_markdown(md, source_file="t.md")
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 850  # _MAX_CHUNK_CHARS=800 plus a small buffer


def test_load_corpus_reads_real_knowledge_dir():
    root = Path(__file__).resolve().parent.parent / "data" / "knowledge"
    chunks = load_corpus(root)
    assert len(chunks) > 10  # we authored 17 docs with multiple sections each
    assert any("exercise" in (c.metadata.get("topic") or "") for c in chunks)
    assert any(c.metadata.get("species") == "dog" for c in chunks)
    assert any(c.metadata.get("species") == "cat" for c in chunks)


# ── Advisor (mocked Anthropic client) ────────────────────────────────


def _fake_pet(species="dog", breed="Shiba Inu", age=3):
    return SimpleNamespace(species=species, breed=breed, age=age, name="Mochi")


def _make_mock_response(input_payload, *, name="suggest_defaults"):
    block = SimpleNamespace(type="tool_use", name=name, input=input_payload)
    return SimpleNamespace(content=[block])


def test_advisor_returns_validated_suggestion_on_good_payload():
    from pawpal_rag import advisor

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_mock_response({
        "duration_minutes": 30,
        "priority": "high",
        "frequency": "daily",
        "rationale": "Shibas need 30+ min walks daily.",
        "citations": [{"source_name": "AKC", "source_url": "https://akc.org", "snippet": "..."}],
    })

    with patch.object(advisor, "_get_client", return_value=fake_client), \
         patch.object(advisor, "retrieve", return_value=[]):
        result = advisor.suggest_task_defaults(_fake_pet(), "Morning walk")

    assert result is not None
    assert result.duration_minutes == 30
    assert result.priority == "high"
    assert result.frequency == "daily"
    assert len(result.citations) == 1


def test_advisor_returns_none_on_invalid_priority():
    from pawpal_rag import advisor

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_mock_response({
        "duration_minutes": 30,
        "priority": "URGENT",  # not in enum
        "frequency": "daily",
        "rationale": "...",
        "citations": [{"source_name": "x", "snippet": "..."}],
    })

    with patch.object(advisor, "_get_client", return_value=fake_client), \
         patch.object(advisor, "retrieve", return_value=[]):
        result = advisor.suggest_task_defaults(_fake_pet(), "Walk")

    assert result is None


def test_advisor_returns_none_on_out_of_range_duration():
    from pawpal_rag import advisor

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_mock_response({
        "duration_minutes": 9999,
        "priority": "high",
        "frequency": "daily",
        "rationale": "...",
        "citations": [{"source_name": "x", "snippet": "..."}],
    })

    with patch.object(advisor, "_get_client", return_value=fake_client), \
         patch.object(advisor, "retrieve", return_value=[]):
        result = advisor.suggest_task_defaults(_fake_pet(), "Walk")

    assert result is None


def test_advisor_returns_none_on_no_citations():
    from pawpal_rag import advisor

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_mock_response({
        "duration_minutes": 30,
        "priority": "high",
        "frequency": "daily",
        "rationale": "...",
        "citations": [],  # at least one required
    })

    with patch.object(advisor, "_get_client", return_value=fake_client), \
         patch.object(advisor, "retrieve", return_value=[]):
        result = advisor.suggest_task_defaults(_fake_pet(), "Walk")

    assert result is None


def test_advisor_returns_none_when_api_call_raises():
    from pawpal_rag import advisor

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("network down")

    with patch.object(advisor, "_get_client", return_value=fake_client), \
         patch.object(advisor, "retrieve", return_value=[]):
        result = advisor.suggest_task_defaults(_fake_pet(), "Walk")

    assert result is None


def test_advisor_returns_none_when_no_api_key():
    from pawpal_rag import advisor

    with patch.object(advisor, "_get_client", return_value=None):
        result = advisor.suggest_task_defaults(_fake_pet(), "Walk")

    assert result is None


def test_advisor_passes_retrieved_chunks_into_user_message():
    from pawpal_rag import advisor
    from pawpal_rag.corpus import Chunk

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_mock_response({
        "duration_minutes": 30,
        "priority": "high",
        "frequency": "daily",
        "rationale": "ok",
        "citations": [{"source_name": "x", "snippet": "y"}],
    })
    fake_chunks = [
        Chunk(
            text="Adult Shibas need 30-60 min walks daily.",
            metadata={"source_name": "AKC test", "topic": "exercise", "species": "dog"},
        )
    ]

    with patch.object(advisor, "_get_client", return_value=fake_client), \
         patch.object(advisor, "retrieve", return_value=fake_chunks):
        advisor.suggest_task_defaults(_fake_pet(), "Walk")

    # Inspect the call payload
    call = fake_client.messages.create.call_args
    user_text = call.kwargs["messages"][0]["content"]
    assert "Adult Shibas" in user_text
    assert "AKC test" in user_text


# ── Real-API integration smoke test (skipped by default) ────────────


@pytest.mark.integration
def test_advisor_real_api_returns_sensible_walk_defaults():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    from pawpal_rag import suggest_task_defaults

    pet = _fake_pet(species="dog", breed="Shiba Inu", age=3)
    result = suggest_task_defaults(pet, "Morning walk")
    assert result is not None
    assert 20 <= result.duration_minutes <= 90
    assert result.frequency == "daily"
    assert result.priority in {"medium", "high"}
    assert len(result.citations) >= 1
