"""Checks for policy chunking and reranking: python test_knowledge.py (from backend/)

No network: chunk() is pure, and rerank() takes the judge function as an argument.
"""
import os

for key in ("OPENAI_API_KEY", "QDRANT_API_KEY", "QDRANT_CLUSTER_ENDPOINT", "LOGFIRE_TOKEN", "LANGSMITH_API_KEY"):
    os.environ[key] = ""  # empty, not absent: backend/.env must not pull real keys into this check

from app import knowledge  # noqa: E402

POLICY = """# Leave Policy

*Sample policy written for the DISHA HR demo. Replace with your company's approved policy before real use.*
Owner: HR · Version 1.0 · Effective 1 January 2026

## 1. Leave types and yearly entitlement

Every confirmed employee receives 12 days of casual leave (CL) each calendar year.

Sick leave (SL) is also 12 days, and earned leave (EL) is 15 days.

## 4. Notice expected

Earned Leave (EL) needs at least 7 calendar days of notice before the first day.

Sick leave of three or more consecutive days requires a medical certificate.
"""

chunks = knowledge.chunk(POLICY, title="Leave Policy")

# The boilerplate header currently wins rank 1 for every policy question: it is generic HR-flavoured
# text that matches anything and answers nothing. It must not reach the index at all.
joined = " ".join(chunks)
assert "Sample policy written" not in joined, "disclaimer must be stripped at ingest"
assert "Owner: HR" not in joined, "owner/version line must be stripped at ingest"
assert "Version 1.0" not in joined

# Every chunk must carry its document identity, so a chunk retrieved on its own is still attributable.
for c in chunks:
    assert c.startswith("Leave Policy"), f"chunk lost its document title: {c[:60]!r}"
assert any("Notice expected" in c for c in chunks), "section headings must survive"

# Smaller chunks: one rule per chunk rather than a whole section, so embeddings aren't diluted.
assert knowledge.MAX_CHARS <= 800, "chunks should be ~700 chars, not 1500"
for c in chunks:
    assert len(c) <= knowledge.MAX_CHARS + 200, f"chunk too long: {len(c)}"
assert len(chunks) >= 2, "this policy should split into several chunks"

# The real content survives.
assert any("12 days of casual leave" in c for c in chunks)
assert any("7 calendar days" in c for c in chunks)

# --- rerank ---
HITS = [{"text": "Holidays do not consume leave balance.", "source": "leave policy", "score": 0.7},
        {"text": "EL needs 7 calendar days of notice.", "source": "leave policy", "score": 0.6},
        {"text": "Late arrival after 10:15 is a late mark.", "source": "attendance policy", "score": 0.5}]

# The judge puts the genuinely relevant passage first; rerank must honour that order.
ordered = knowledge.rerank("how much notice for earned leave?", HITS, keep=2, ask=lambda _: '{"order": [1, 0, 2]}')
assert [h["text"] for h in ordered] == [HITS[1]["text"], HITS[0]["text"]], ordered
assert len(ordered) == 2, "keep must cap the result"

# Passages the judge leaves out are dropped, not padded back in: off-topic context dilutes the answer.
only = knowledge.rerank("how much notice for earned leave?", HITS, keep=4, ask=lambda _: '{"order": [1, 1]}')
assert [h["text"] for h in only] == [HITS[1]["text"]], only

# Fail-open: retrieval must never take the assistant down, so any judge failure keeps vector order.
def boom(_):
    raise RuntimeError("judge unavailable")

assert knowledge.rerank("q", HITS, keep=2, ask=boom) == HITS[:2], "must fall back to vector order"
assert knowledge.rerank("q", HITS, keep=2, ask=lambda _: "not json") == HITS[:2], "bad JSON falls back"
assert knowledge.rerank("q", HITS, keep=2, ask=lambda _: '{"order": [9, 9]}') == HITS[:2], "bad indexes fall back"
assert knowledge.rerank("q", [], keep=2, ask=boom) == [], "no candidates is not an error"

# --- flash_rerank (fake ranker: same shape as flashrank's rerank() output, sorted best first) ---
class FakeRanker:
    def __init__(self, scores):
        self.scores = scores

    def rerank(self, request):
        return sorted(({"id": i, "score": s} for i, s in enumerate(self.scores)), key=lambda r: -r["score"])


# Relative cutoff: tiny absolute scores still keep the best passage; anything under half the top is dropped.
assert knowledge.flash_rerank("q", HITS, keep=4, ranker=FakeRanker([0.001, 0.006, 0.004])) == [HITS[1], HITS[2]]
assert knowledge.flash_rerank("q", HITS, keep=1, ranker=FakeRanker([0.9, 0.95, 0.9])) == [HITS[1]], "keep caps"


class BrokenRanker:
    def rerank(self, request):
        raise RuntimeError("model missing")


assert knowledge.flash_rerank("q", HITS, keep=2, ranker=BrokenRanker()) == HITS[:2], "must fall back to vector order"
assert knowledge.flash_rerank("q", [], keep=2, ranker=BrokenRanker()) == []

# search() caching: a repeat question skips embedding, Qdrant and rerank; a rerank failure is not cached
from types import SimpleNamespace as NS  # noqa: E402

calls = {"embed": 0, "qdrant": 0, "rank": 0}


class FakeEmbeddings:
    def create(self, model, input):
        calls["embed"] += 1
        return NS(data=[NS(embedding=[0.1, 0.2])])


class FakeQdrant:
    def query_points(self, **kw):
        calls["qdrant"] += 1
        return NS(points=[NS(payload={"text": h["text"], "source": h["source"]}, score=0.5) for h in HITS])


rank_ok = [False]


def fake_rank(query, hits, keep=4, ask=None):
    calls["rank"] += 1
    if not rank_ok[0]:
        raise RuntimeError("rerank down")
    return hits[1:2]


knowledge._clients = lambda: (NS(embeddings=FakeEmbeddings()), FakeQdrant())
knowledge._rerank_strict = fake_rank
knowledge.RERANKER = "llm"

first = knowledge.search("hra?", limit=2)
assert [h["text"] for h in first] == [HITS[0]["text"], HITS[1]["text"]], "rerank failure falls back to vector order"
rank_ok[0] = True
second = knowledge.search("hra?", limit=2)
assert [h["text"] for h in second] == [HITS[1]["text"]], "the fallback must not have been cached"
second[0]["text"] = "edited by a caller"
third = knowledge.search("  hra?  ", limit=2)
assert [h["text"] for h in third] == [HITS[1]["text"]], "callers get copies, and whitespace doesn't miss the cache"
assert calls == {"embed": 1, "qdrant": 1, "rank": 2}, calls

print("knowledge checks passed")
