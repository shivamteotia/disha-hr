"""Policy knowledge base: markdown in data/policies -> OpenAI embeddings -> Qdrant Cloud.

Ingest (from backend/):  python -m app.knowledge          (add --wipe to recreate the collection)
Search is used by the agent's retriever node.
"""
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
EMBED_DIM = 1536  # text-embedding-3-small; 3-large is 3072
MAX_CHARS = 1500  # chunk size, paragraph aware


def chunk(md: str) -> list[str]:
    """Split on blank lines, then pack paragraphs up to MAX_CHARS, keeping the nearest heading for context."""
    chunks, current, heading = [], "", ""
    for para in re.split(r"\n\s*\n", md):
        para = para.strip()
        if not para:
            continue
        if para.startswith("#"):
            heading = para.lstrip("# ").strip()
        if len(current) + len(para) > MAX_CHARS and current:
            chunks.append(current.strip())
            current = f"[{heading}]\n" if heading else ""
        current += para + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _clients():
    from openai import OpenAI
    from qdrant_client import QdrantClient
    url, key = os.environ.get("QDRANT_CLUSTER_ENDPOINT"), os.environ.get("QDRANT_API_KEY")
    if not url or not key:
        raise RuntimeError("Set QDRANT_CLUSTER_ENDPOINT and QDRANT_API_KEY in backend/.env")
    return OpenAI(), QdrantClient(url=url, api_key=key, timeout=30)


def embed(texts: list[str]) -> list[list[float]]:
    openai_client, _ = _clients()
    out = []
    for i in range(0, len(texts), 64):
        batch = openai_client.embeddings.create(model=EMBED_MODEL, input=texts[i:i + 64])
        out.extend(d.embedding for d in batch.data)
    return out


def search(query: str, limit: int = 5) -> list[dict]:
    """Return [{text, source, score}] for the closest policy chunks; [] if Qdrant isn't configured."""
    try:
        openai_client, qdrant = _clients()
        vector = openai_client.embeddings.create(model=EMBED_MODEL, input=query).data[0].embedding
        hits = qdrant.query_points(collection_name=COLLECTION, query=vector, limit=limit, with_payload=True).points
        return [{"text": h.payload.get("text", ""), "source": h.payload.get("source", "policy"), "score": round(h.score, 3)}
                for h in hits]
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
        for i, part in enumerate(chunk(f.read_text(encoding="utf-8"))):
            texts.append(part)
            payloads.append({"text": part, "source": f.stem.replace("-", " "), "chunk": i})
    vectors = embed(texts)
    qdrant.upsert(COLLECTION, points=[models.PointStruct(id=i, vector=v, payload=p)
                                      for i, (v, p) in enumerate(zip(vectors, payloads))])
    print(f"Indexed {len(texts)} chunks from {len(files)} policy files into '{COLLECTION}'.")
    return len(texts)


if __name__ == "__main__":
    ingest(wipe="--wipe" in sys.argv)
