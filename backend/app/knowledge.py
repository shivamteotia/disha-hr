"""Policy knowledge base: markdown in data/policies -> OpenAI embeddings -> Qdrant Cloud.

Ingest (from backend/):  python -m app.knowledge          (add --wipe to recreate the collection)
Search is used by the agent's retriever node.
"""
import functools
import json
import os
import re
import sys
from pathlib import Path

try:  # this module also runs as a CLI, so load backend/.env here too
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

POLICY_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"
COLLECTION = os.environ.get("QDRANT_COLLECTION", "disha_policies")
EMBED_MODEL = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")
# gpt-4.1-mini: full recall on the planner's rewritten queries and ~0.25s faster than gpt-5.4-mini (non-reasoning)
RERANK_MODEL = os.environ.get("OPENAI_RERANK_MODEL", "gpt-4.1-mini")
# llm = rerank() via RERANK_MODEL (default); flashrank = local cross-encoder - ~0.3s faster but dropped the
# answering chunk on rewritten queries (pol-office-days, pol-gift-limit in evals/baselines/RESULTS.md)
RERANKER = os.environ.get("RERANKER", "llm")
FLASHRANK_MODEL = os.environ.get("FLASHRANK_MODEL", "ms-marco-MiniLM-L-12-v2")
EMBED_DIM = 1536      # text-embedding-3-small; 3-large is 3072
MAX_CHARS = 700       # one rule per chunk: bigger chunks dilute the embedding
CANDIDATES = 12       # fetched from Qdrant, then reranked down to the caller's limit

# Every policy opens with the same disclaimer and an Owner/Version line. That text is generic
# HR-flavoured boilerplate: it matches almost any question and answers none, so it used to win
# rank 1 for every query. Drop it before indexing.
BOILERPLATE = re.compile(r"^\s*(\*Sample policy.*?\*|Owner:.*|Version\s.*|_.*demo.*_)\s*$", re.I | re.M)


def chunk(md: str, title: str) -> list[str]:
    """Split a policy into ~MAX_CHARS pieces, each labelled 'Title › Section' so it stands alone."""
    md = BOILERPLATE.sub("", md)
    chunks, current, heading = [], "", ""

    def label():
        return f"{title} › {heading}\n" if heading else f"{title}\n"

    for para in re.split(r"\n\s*\n", md):
        para = para.strip()
        if not para:
            continue
        if para.startswith("#"):
            new_heading = para.lstrip("# ").strip()
            if new_heading == title:      # the document's own H1, already in every label
                continue
            if current.strip():
                chunks.append(current.strip())
                current = ""
            heading = new_heading
            continue
        if len(current) + len(para) > MAX_CHARS and current.strip():
            chunks.append(current.strip())
            current = ""
        current = (current or label()) + para + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def rerank(query: str, hits: list[dict], keep: int = 4, ask=None) -> list[dict]:
    """Keep only the candidates that help answer the question, most useful first, at most `keep`.

    Dropping the off-topic passages (rather than always padding to `keep`) is what keeps the answer
    model's context on-topic - measured as contextual relevancy in evals/.
    Fails open: any error, bad JSON or no usable index falls back to vector order, because a
    ranking problem must never stop the assistant answering.
    """
    if not hits:
        return []
    ask = ask or _ask_model
    listing = "\n".join(f"[{i}] {h['text'][:400]}" for i, h in enumerate(hits))
    prompt = (f"Question: {query}\n\nPassages:\n{listing}\n\n"
              f"List the numbers of the passages needed to answer the question, most useful first. "
              f"Leave out passages that are only about the same topic but don't help answer it. "
              f'Reply as JSON: {{"order": [numbers]}}')
    try:
        order = json.loads(ask(prompt))["order"]
        ranked = list({i: hits[i] for i in order if isinstance(i, int) and 0 <= i < len(hits)}.values())
        return ranked[:keep] or hits[:keep]
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("rerank unavailable, using vector order: %s", e)
        return hits[:keep]


def flash_rerank(query: str, hits: list[dict], keep: int = 4, ranker=None) -> list[dict]:
    """Local cross-encoder (FlashRank, no API call): keep the best passage plus any scoring at least
    half as well, at most `keep`. Relative, not a fixed cutoff: the right passage scores 0.99 for one
    question and 0.006 for another, so only the ratio within a question means anything.
    Fails open to vector order, like rerank()."""
    if not hits:
        return []
    try:
        from flashrank import RerankRequest
        scored = (ranker or _flashranker()).rerank(
            RerankRequest(query=query, passages=[{"id": i, "text": h["text"]} for i, h in enumerate(hits)]))
        top = scored[0]["score"]
        return [hits[s["id"]] for s in scored if s["score"] >= top / 2][:keep]
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("flashrank unavailable, using vector order: %s", e)
        return hits[:keep]


_ranker = None


def _flashranker():
    global _ranker
    if _ranker is None:  # loads the ONNX model once per process (downloaded on first use)
        import tempfile
        from flashrank import Ranker
        _ranker = Ranker(model_name=FLASHRANK_MODEL, cache_dir=str(Path(tempfile.gettempdir()) / "flashrank"))
    return _ranker


def _ask_model(prompt: str) -> str:
    out = _openai().chat.completions.create(
        model=RERANK_MODEL, messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}, max_completion_tokens=500)
    return out.choices[0].message.content or ""


@functools.cache
def _openai():
    from openai import OpenAI
    return OpenAI(timeout=30)


@functools.cache  # one pair per process: rebuilding them cost ~0.9s per search (TLS + Qdrant version check)
def _clients():
    from qdrant_client import QdrantClient
    url = (os.environ.get("QDRANT_CLUSTER_ENDPOINT") or "").strip()
    key = (os.environ.get("QDRANT_API_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Set QDRANT_CLUSTER_ENDPOINT and QDRANT_API_KEY in backend/.env")
    return _openai(), QdrantClient(url=url, api_key=key, timeout=30)


def embed(texts: list[str]) -> list[list[float]]:
    openai_client, _ = _clients()
    out = []
    for i in range(0, len(texts), 64):
        batch = openai_client.embeddings.create(model=EMBED_MODEL, input=texts[i:i + 64])
        out.extend(d.embedding for d in batch.data)
    return out


def search(query: str, limit: int = 4) -> list[dict]:
    """Return [{text, source, score}] for the best policy chunks; [] if Qdrant isn't configured."""
    try:
        openai_client, qdrant = _clients()
        vector = openai_client.embeddings.create(model=EMBED_MODEL, input=query).data[0].embedding
        hits = qdrant.query_points(collection_name=COLLECTION, query=vector, limit=CANDIDATES, with_payload=True).points
        candidates = [{"text": h.payload.get("text", ""), "source": h.payload.get("source", "policy"),
                       "score": round(h.score, 3)} for h in hits]
        return (flash_rerank if RERANKER == "flashrank" else rerank)(query, candidates, keep=limit)
    except Exception as e:  # noqa: BLE001 - the agent answers without policy context rather than failing
        import logging
        logging.getLogger(__name__).warning("policy search unavailable: %s", e)
        return []


def ingest(wipe: bool = False) -> int:
    from qdrant_client.http import models
    _, qdrant = _clients()
    files = sorted(POLICY_DIR.glob("*.md"))
    if not files:
        raise RuntimeError(f"No .md policies found in {POLICY_DIR}")

    if wipe and qdrant.collection_exists(COLLECTION):
        qdrant.delete_collection(COLLECTION)
    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(COLLECTION, vectors_config=models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE))

    texts, payloads = [], []
    for f in files:
        body = f.read_text(encoding="utf-8")
        first = next((line for line in body.splitlines() if line.startswith("# ")), "")
        title = first.lstrip("# ").strip() or f.stem.replace("-", " ").title()
        for i, part in enumerate(chunk(body, title)):
            texts.append(part)
            payloads.append({"text": part, "source": title, "chunk": i})
    vectors = embed(texts)
    qdrant.upsert(COLLECTION, points=[models.PointStruct(id=i, vector=v, payload=p)
                                      for i, (v, p) in enumerate(zip(vectors, payloads))])
    print(f"Indexed {len(texts)} chunks from {len(files)} policy files into '{COLLECTION}'.")
    return len(texts)


if __name__ == "__main__":
    ingest(wipe="--wipe" in sys.argv)
