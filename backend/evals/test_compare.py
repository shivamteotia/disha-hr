"""Checks the regression verdict logic, no API or judge needed:  cd backend && python -m evals.test_compare"""
from evals.compare import compare


def snap(**metrics):
    return {"metrics": {k.replace("__", "."): v for k, v in metrics.items()}}


base = snap(safety__pii_leakage__avg_score=0.95, quality__faithfulness__avg_score=0.90,
            ops__latency__p95_ms=4000, safety__toxicity__avg_score=1.0, quality__faithfulness__n=8)
assert compare(base, base)[0] == "PASS"
assert compare(base, {**base, "metrics": {**base["metrics"], "quality.faithfulness.avg_score": 0.87}})[0] == "PASS"  # noise
assert compare(base, {**base, "metrics": {**base["metrics"], "quality.faithfulness.avg_score": 0.80}})[0] == "REVIEW"
assert compare(base, {**base, "metrics": {**base["metrics"], "ops.latency.p95_ms": 5100}})[0] == "REVIEW"
assert compare(base, {**base, "metrics": {**base["metrics"], "ops.latency.p95_ms": 2000}})[0] == "PASS"  # faster
assert compare(base, {**base, "metrics": {**base["metrics"], "safety.pii_leakage.avg_score": 0.90}})[0] == "FAIL"
assert compare(base, {**base, "metrics": {**base["metrics"], "safety.toxicity.avg_score": 0.90}})[0] == "FAIL"
assert compare(base, {**base, "metrics": {**base["metrics"], "quality.faithfulness.n": 3}})[0] == "PASS"  # info
edge = snap(safety__x__avg_score=0.92)
assert compare(edge, snap(safety__x__avg_score=0.90))[0] == "PASS", "a drop of exactly the tolerance is flat"
print("compare: ok")
