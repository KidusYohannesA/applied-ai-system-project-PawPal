from __future__ import annotations

from pathlib import Path

from .corpus import Chunk, load_corpus

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PERSIST_DIR = _PROJECT_ROOT / "data" / "chroma"
_DEFAULT_CORPUS_DIR = _PROJECT_ROOT / "data" / "knowledge"
_COLLECTION_NAME = "pawpal_knowledge"
_EMBED_MODEL = "all-MiniLM-L6-v2"


_client_cache = {}


def _get_collection(persist_dir: Path = _DEFAULT_PERSIST_DIR):
    key = str(persist_dir)
    if key in _client_cache:
        return _client_cache[key]
    persist_dir.mkdir(parents=True, exist_ok=True)
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(persist_dir))
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=_EMBED_MODEL
    )
    collection = client.get_or_create_collection(
        name=_COLLECTION_NAME, embedding_function=embed_fn
    )
    _client_cache[key] = collection
    return collection


def build_index(
    corpus_dir: Path = _DEFAULT_CORPUS_DIR,
    persist_dir: Path = _DEFAULT_PERSIST_DIR,
    reset: bool = True,
) -> int:
    """Build (or rebuild) the vector store from the corpus directory.

    Returns the number of chunks indexed.
    """
    chunks = load_corpus(corpus_dir)
    if not chunks:
        raise RuntimeError(f"No markdown files found under {corpus_dir}")

    if reset and persist_dir.exists():
        import chromadb

        client = chromadb.PersistentClient(path=str(persist_dir))
        try:
            client.delete_collection(_COLLECTION_NAME)
        except Exception:
            pass
        _client_cache.pop(str(persist_dir), None)

    collection = _get_collection(persist_dir)
    ids = [f"chunk-{i}" for i in range(len(chunks))]
    documents = [c.text for c in chunks]
    metadatas = [c.metadata for c in chunks]
    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return len(chunks)


def ensure_indexed(
    corpus_dir: Path = _DEFAULT_CORPUS_DIR,
    persist_dir: Path = _DEFAULT_PERSIST_DIR,
) -> None:
    """Build the index lazily on first use if it doesn't exist."""
    collection = _get_collection(persist_dir)
    if collection.count() == 0:
        build_index(corpus_dir=corpus_dir, persist_dir=persist_dir, reset=False)


def query(
    text: str,
    k: int = 5,
    where: dict | None = None,
    persist_dir: Path = _DEFAULT_PERSIST_DIR,
) -> list[Chunk]:
    """Run a similarity query and return Chunks with score (lower distance = better)."""
    ensure_indexed(persist_dir=persist_dir)
    collection = _get_collection(persist_dir)
    res = collection.query(query_texts=[text], n_results=k, where=where or None)
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        out.append(Chunk(text=doc, metadata=meta or {}, score=float(dist)))
    return out
