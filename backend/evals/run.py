"""Disha eval harness: runs golden.json through the live API and scores the answers.

    cd backend
    python -m evals.run                  # ask the agent, then judge the policy answers
    python -m evals.run --no-judge       # deterministic checks only, no judge calls
    python -m evals.run --from-report    # re-judge the answers already in report.json

Two kinds of score:
  deterministic - route taken, the number in a data answer (verified by truth_sql against the real
                  database), and whether a safety question leaked anything. No judge, no cost, never flaky.
  judged        - DeepEval: faithfulness, answer relevancy, contextual precision/recall and a GEval
                  correctness check over the policy questions, where retrieved context exists.

The harness talks to the running API over HTTP rather than importing the app, so it measures the
deployed system - the same thing an employee talks to.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")  # no usage pings from the eval run

HERE = Path(__file__).resolve().parent
DB = HERE.parent / "disha.db"
API = os.environ.get("EVAL_API", "http://localhost:8000")
PASSWORD = "password123"          # seeded dummy accounts
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gpt-5.4-mini")


# ---- HTTP (stdlib only) ----
def _post(path, payload, cookie=None):
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read() or b"{}"), r.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, json.loads(body or b"{}"), e.headers.get("Retry-After", "")


def login(email):
    status, body, set_cookie = _post("/api/login", {"email": email, "password": PASSWORD})
    if status != 200:
        sys.exit(f"login failed for {email}: {status} {body}. Is the API running, and is the database seeded?")
    return set_cookie.split(";")[0]


def ask(cookie, question):
    """One chat turn, waiting out the per-user rate limit if we hit it."""
    for _ in range(4):
        status, body, extra = _post("/api/chat", {"messages": [{"role": "user", "content": question}]}, cookie)
        if status == 200:
            return body
        if status == 429:
            wait = int(extra or 20) + 1
            print(f"    rate limited, waiting {wait}s")
            time.sleep(wait)
            continue
        return {"reply": f"[HTTP {status}] {body.get('detail')}", "route": "error", "contexts": [], "sql": None}
    return {"reply": "[rate limited]", "route": "error", "contexts": [], "sql": None}


# ---- deterministic scoring ----
def truth_value(sql):
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as db:
        row = db.execute(sql).fetchone()
    return None if row is None else row[0]


def says_number(reply, value):
    """Does the answer contain this number? Tolerates 1,24,000 and spaced separators."""
    return str(int(value)) in re.sub(r"[,\s]", "", reply)


def leaked(reply, forbidden):
    low = reply.lower()
    return [f for f in forbidden if f.lower() in low]


# ---- judged scoring (DeepEval) ----
def judged_scores(policy_rows):
    """Score each policy answer. Metrics run one at a time so a single failure can't lose the rest."""
    from deepeval.metrics import (AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric,
                                  FaithfulnessMetric, GEval)
    from deepeval.test_case import LLMTestCase
    try:  # renamed in deepeval 4.x; the old name still works but warns
        from deepeval.test_case import SingleTurnParams as Params
    except ImportError:
        from deepeval.test_case import LLMTestCaseParams as Params

    correctness = GEval(
        name="correctness", model=JUDGE_MODEL,
        criteria=("Does the answer state the same rule as the expected answer? Extra helpful detail, such as which "
                  "app page to use, is fine. A contradiction, a wrong number, or a missing rule is not."),
        evaluation_params=[Params.INPUT, Params.ACTUAL_OUTPUT, Params.EXPECTED_OUTPUT])
    metrics = [FaithfulnessMetric(model=JUDGE_MODEL), AnswerRelevancyMetric(model=JUDGE_MODEL),
               ContextualPrecisionMetric(model=JUDGE_MODEL), ContextualRecallMetric(model=JUDGE_MODEL), correctness]

    scored = []
    for row in policy_rows:
        case = LLMTestCase(input=row["question"], actual_output=row["reply"],
                           retrieval_context=row["contexts"] or ["(no context retrieved)"],
                           expected_output=row["ground_truth"])
        out = {"id": row["id"]}
        for metric in metrics:
            key = re.sub(r"[^a-z0-9]+", "_", getattr(metric, "__name__", type(metric).__name__).lower()).strip("_")
            try:
                metric.measure(case)
                out[key] = round(float(metric.score), 3)
                out[f"{key}_why"] = str(metric.reason)
            except Exception as e:  # noqa: BLE001
                out[key] = None
                out[f"{key}_error"] = f"{type(e).__name__}: {str(e)[:140]}"
        print("    " + f"{row['id']:22} " + "  ".join(f"{k}={v:.2f}" for k, v in out.items() if isinstance(v, float)))
        scored.append(out)
    return scored


# ---- run ----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-judge", action="store_true", help="skip the judged metrics")
    ap.add_argument("--only", help="run one case id")
    ap.add_argument("--from-report", action="store_true",
                    help="score the answers already in report.json instead of asking the agent again")
    args = ap.parse_args()

    if args.from_report:
        rows = json.loads((HERE / "report.json").read_text(encoding="utf-8"))["cases"]
        print(f"  scoring {len(rows)} answers already collected in report.json")
    else:
        cases = json.loads((HERE / "golden.json").read_text(encoding="utf-8"))["cases"]
        if args.only:
            cases = [c for c in cases if c["id"] == args.only]
        cookies, rows = {}, []
        for case in cases:
            email = case["user"]
            cookies.setdefault(email, login(email))
            print(f"  {case['id']:22} {case['question'][:58]}")
            answer = ask(cookies[email], case["question"])
            row = {**case, "reply": answer.get("reply", ""), "got_route": answer.get("route"),
                   "contexts": answer.get("contexts", []), "sql": answer.get("sql")}

            row["route_ok"] = case.get("route") is None or answer.get("route") == case["route"]
            if case["kind"] == "data":
                row["expected_value"] = truth_value(case["truth_sql"])
                row["value_ok"] = row["expected_value"] is not None and says_number(row["reply"], row["expected_value"])
            if case["kind"] == "safety":
                row["leaked"] = leaked(row["reply"], case["forbidden_contains"])
                row["safe"] = not row["leaked"]
            rows.append(row)

    # ---- summary ----
    def rate(subset, key):
        vals = [r[key] for r in subset if key in r]
        return sum(bool(v) for v in vals), len(vals)

    by_kind = lambda k: [r for r in rows if r["kind"] == k]
    print("\n" + "=" * 72)
    for label, subset, key in [("route correct", rows, "route_ok"),
                               ("data answers correct", by_kind("data"), "value_ok"),
                               ("safety questions refused", by_kind("safety"), "safe")]:
        ok, total = rate(subset, key)
        if total:
            print(f"  {label:28} {ok}/{total}")
    for r in rows:
        if not r.get("route_ok"):
            print(f"    ! {r['id']}: expected route {r.get('route')}, got {r['got_route']}")
        if r.get("value_ok") is False:
            print(f"    ! {r['id']}: expected {r['expected_value']} — answered: {r['reply'][:90]}")
        if r.get("leaked"):
            print(f"    ! {r['id']} LEAKED {r['leaked']} — {r['reply'][:90]}")

    report = {"cases": rows}
    policy_rows = by_kind("policy")
    if policy_rows and not args.no_judge:
        print(f"\n  judging {len(policy_rows)} policy answers with DeepEval ({JUDGE_MODEL})…")
        scored = judged_scores(policy_rows)
        report["judged"] = scored
        print("\n  means")
        for name in [k for k, v in scored[0].items() if isinstance(v, float)]:
            vals = [s[name] for s in scored if isinstance(s.get(name), float)]
            if vals:
                print(f"  {name:28} {sum(vals) / len(vals):.2f}  ({len(vals)}/{len(scored)} scored)")
        for s in scored:
            low = [k for k, v in s.items() if isinstance(v, float) and v < 0.7]
            for k in low:
                print(f"    ? {s['id']} {k}={s[k]:.2f}: {str(s.get(k + '_why'))[:120]}")

    # a one-case run writes its own file: it must never overwrite the full report
    out = HERE / (f"report-{args.only}.json" if args.only else "report.json")
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n  full report: {out}")


if __name__ == "__main__":
    main()
