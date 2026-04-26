SYSTEM_PROMPT = """You are PawPal+'s pet-care advisor. Given a pet (species, breed, age) and a
user-entered task title, suggest evidence-based defaults for duration_minutes, priority,
and frequency, grounded in the retrieved care guidance.

Hard rules:
- duration_minutes: integer between 1 and 240
- priority: one of "low", "medium", "high"
- frequency: one of "once", "daily", "weekly", "monthly"
- citations: at least one source from the retrieved chunks; quote a short snippet
- rationale: 1-2 sentences explaining your choice in plain language

If the retrieved chunks do not cover the task, return reasonable defaults but say so
in the rationale and use a single citation noting the limitation. Never invent sources
or numbers that do not appear in the retrieved chunks."""


SUGGEST_TOOL = {
    "name": "suggest_defaults",
    "description": "Return evidence-based default values for a PawPal+ task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "duration_minutes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 240,
                "description": "Recommended task duration in minutes.",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Recommended priority.",
            },
            "frequency": {
                "type": "string",
                "enum": ["once", "daily", "weekly", "monthly"],
                "description": "Recommended frequency.",
            },
            "rationale": {
                "type": "string",
                "description": "1-2 sentence explanation of the recommendation.",
            },
            "citations": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "source_name": {"type": "string"},
                        "source_url": {"type": "string"},
                        "snippet": {"type": "string"},
                    },
                    "required": ["source_name", "snippet"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "duration_minutes",
            "priority",
            "frequency",
            "rationale",
            "citations",
        ],
        "additionalProperties": False,
    },
}


def format_chunks_for_prompt(chunks) -> str:
    """Render retrieved chunks as a labeled block for the user message."""
    lines = []
    for i, c in enumerate(chunks, 1):
        meta = c.metadata or {}
        label = (
            f"[{i}] {meta.get('source_name', meta.get('source_file', 'unknown'))}"
            f" | topic={meta.get('topic', '?')} | species={meta.get('species', '?')}"
        )
        lines.append(label)
        lines.append(c.text.strip())
        lines.append("")
    return "\n".join(lines).strip() or "(no chunks retrieved)"


def build_user_message(pet, task_title: str, chunks) -> str:
    species = getattr(pet, "species", "?")
    breed = getattr(pet, "breed", "") or "(unknown breed)"
    age = getattr(pet, "age", 0)
    return (
        f"Pet: species={species}, breed={breed}, age={age} years\n"
        f"Task title: {task_title!r}\n\n"
        f"Retrieved care guidance (use citations from these only):\n"
        f"{format_chunks_for_prompt(chunks)}\n\n"
        f"Call the suggest_defaults tool with your recommendation."
    )
