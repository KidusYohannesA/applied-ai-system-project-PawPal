"""Build (or rebuild) the PawPal+ RAG vector store from data/knowledge/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pawpal_rag.store import build_index


def main():
    n = build_index(reset=True)
    print(f"Indexed {n} chunks.")


if __name__ == "__main__":
    main()
