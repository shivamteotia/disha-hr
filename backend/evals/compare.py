"""Regression gate: diff the candidate snapshot against the blessed baseline and give a verdict.

    cd backend
    python -m evals.run --baseline --label "main"      # once, on the version you trust
    python -m evals.run --label "k=8 retrieval"        # after a change -> baselines/candidate.json
    python -m evals.compare [--all]                    # PASS=0  FAIL=1  REVIEW=2 (exit code, for CI)

Every metric id resolves to a rule (rule_for): which direction is better, and whether it is
  gate      - any drop beyond tolerance BLOCKS (safety),
  guardrail - a drop beyond tolerance is flagged for a human (quality, latency, reliability),
  info      - shown, never affects the verdict (counts, p50).
Tolerances sit above the run-to-run noise of an LLM judge and of latency, so wobble reads as flat.
Judged metrics are compared on their average score, not a pass rate: a pass rate swings wildly when
scores cluster near the threshold.
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

BASELINES = Path(__file__).resolve().parent / "baselines"
EXIT_CODE = {"PASS": 0, "FAIL": 1, "REVIEW": 2}


def rule_for(mid):
    """-> (direction, kind, tolerance as (absolute, relative))"""
    if mid.endswith(".n") or mid == "ops.latency.p50_ms":
        return "higher", "info", (0, 0)
    if mid.startswith("safety."):  # judged leakage/scope/toxicity (deepeval 4.x: 1 = non-toxic), and the refusal check
        return "higher", "gate", (0 if mid.endswith("pass_rate") else 0.02, 0)
    if mid.startswith("quality."):
        return "higher", "guardrail", (0.05, 0)
    if mid.startswith("det."):  # route and data-number checks: deterministic, but the planner is an LLM
        return "higher", "guardrail", (0, 0)
    if mid == "ops.latency.p95_ms":
        return "lower", "guardrail", (0, 0.25)
    if mid == "ops.reliability.success_rate":
        return "higher", "guardrail", (0, 0)
    return "higher", "info", (0, 0)


def classify(mid, base, cand):
    direction, kind, (tol, rel) = rule_for(mid)
    row = {"id": mid, "baseline": base, "candidate": cand, "kind": kind, "delta": None}
    if base is None or cand is None:
        return {**row, "status": "new" if base is None else "dropped"}
    row["delta"] = delta = cand - base
    if kind == "info":
        return {**row, "status": "info"}
    if (delta > 0) == (direction == "higher") and delta != 0:
        return {**row, "status": "improved"}
    if round(abs(delta), 9) <= max(tol, rel * abs(base)):  # round: 0.92 - 0.90 is 0.0200000000000000018
        return {**row, "status": "flat"}
    return {**row, "status": "blocked" if kind == "gate" else "regressed"}


def compare(baseline, candidate):
    b, c = baseline["metrics"], candidate["metrics"]
    rows = [classify(mid, b.get(mid), c.get(mid)) for mid in sorted(set(b) | set(c))]
    statuses = {r["status"] for r in rows}
    return ("FAIL" if "blocked" in statuses else "REVIEW" if "regressed" in statuses else "PASS"), rows


def _fmt(v):
    return "" if v is None else f"{v:.4g}" if isinstance(v, float) and not math.isnan(v) else str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=BASELINES / "baseline.json")
    ap.add_argument("--candidate", default=BASELINES / "candidate.json")
    ap.add_argument("--all", action="store_true", help="also show info metrics")
    args = ap.parse_args()
    baseline, candidate = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (args.baseline, args.candidate))

    for name, snap in (("baseline", baseline), ("candidate", candidate)):
        meta = snap["metadata"]
        print(f"{name:10} {meta.get('label') or '(no label)'}  git {meta['git_sha']}  judge {meta['judge_model']}  "
              f"{meta['created_at']}")
    if baseline["metadata"]["judge_model"] != candidate["metadata"]["judge_model"]:
        print("  ! judge models differ - judged scores are not comparable")

    verdict, rows = compare(baseline, candidate)
    order = ["blocked", "regressed", "dropped", "new", "improved", "flat", "info"]
    print("=" * 92)
    print(f"{'metric':<46} {'baseline':>10} {'candidate':>10} {'delta':>10}  status")
    print("-" * 92)
    for r in sorted(rows, key=lambda r: (order.index(r["status"]), r["id"])):
        if r["kind"] == "info" and not args.all:
            continue
        mark = "  <<<" if r["status"] in ("blocked", "regressed") else ""
        delta = f"{r['delta']:+.4g}" if r["delta"] is not None else ""
        print(f"{r['id']:<46} {_fmt(r['baseline']):>10} {_fmt(r['candidate']):>10} {delta:>10}  {r['status']}{mark}")
    counts = Counter(r["status"] for r in rows)
    print("-" * 92)
    print("  ".join(f"{k}={counts[k]}" for k in order if counts[k]))
    print({"PASS": "VERDICT: PASS   - no gate blocked, no guardrail regressed.",
           "REVIEW": "VERDICT: REVIEW - a guardrail regressed beyond tolerance; a human decides.",
           "FAIL": "VERDICT: FAIL   - a safety gate regressed. Blocked."}[verdict])
    sys.exit(EXIT_CODE[verdict])


if __name__ == "__main__":
    main()
