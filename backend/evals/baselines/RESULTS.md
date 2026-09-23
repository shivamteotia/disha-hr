# Eval baseline — 2026-09-23

`baseline.json` = mean of 5 full runs of `python -m evals.run` (20 golden cases each) against the live API.
Per-run snapshots, reports and logs: `runs/`. Per-metric spread: `runs/spread.json`.

| Setting | Value |
|---|---|
| Code | `981c7bb` + uncommitted: FlashRank reranker (default), rerank keeps only useful passages, data-route sandbox fix |
| Reranker | `RERANKER=flashrank`, `ms-marco-MiniLM-L-12-v2`, relative cutoff (≥ half the top score), ≤ 4 chunks |
| Judge | `gpt-5.4-mini` (DeepEval) |
| Agent | OpenAI via the app's own settings |

## Results (mean of 5, with per-run values)

| Metric | Kind | Mean | Runs | Spread | compare.py tol |
|---|---|---|---|---|---|
| route correct % | guardrail | 98.0 | 100, 95, 95, 100, 100 | 5.0 | 0 |
| data answers correct % | guardrail | 100 | all 100 | 0 | 0 |
| safety refusals (forbidden text) % | gate | 100 | all 100 | 0 | 0 |
| reliability (non-error) % | guardrail | 100 | all 100 | 0 | 0 |
| latency p50 ms | info | ~7,900 | 7716 – 8084 | — | — |
| latency p95 ms | guardrail | 10,105 | 9693, 9413, 9762, 10723, 10936 | 1,523 | 25 % |
| faithfulness | guardrail | 0.994 | 1, 1, 1, 1, .969 | .031 | .05 |
| answer relevancy | guardrail | 0.851 | .896, .927, .715, .844, .875 | .213 | .05 |
| contextual relevancy | guardrail | 0.427 | .495, .457, .276, .386, .522 | .247 | .05 |
| contextual precision | guardrail | 0.838 | .938, .75, .75, .875, .875 | .188 | .05 |
| contextual recall | guardrail | **0.800** | 1, .75, .75, .75, .75 | .25 | .05 |
| correctness (GEval) | guardrail | **0.725** | .812, .7, .675, .713, .725 | .137 | .05 |
| completeness (GEval) | guardrail | 0.698 | .812, .625, .662, .7, .688 | .188 | .05 |
| PII leakage | gate | 1.000 | all 1 | 0 | .02 |
| protected-info leakage | gate | 0.920 | .933, .9, .867, .967, .933 | .10 | .02 |
| scope adherence | gate | 0.780 | .8, .833, .8, .733, .733 | .10 | .02 |
| toxicity (1 = clean) | gate | 1.000 | all 1 | 0 | .02 |

## Findings

1. **FlashRank drops the right chunk in the real pipeline.** Recall/correctness failures are two questions:
   - `pol-office-days` — answer needs *Remote Work › Hybrid working* (3 office days). FlashRank kept only
     attendance chunks in 4/5 runs, so Disha answered "five days, Mon–Fri".
   - `pol-gift-limit` — FlashRank kept *Expense › What cannot be claimed* instead of *Code of Conduct › Gifts*
     in 2/5 runs.
   The planner rewrites the question before search; the ms-marco cross-encoder is sensitive to that phrasing
   (e.g. appending "policy" flips gift-limit to the expense chunk), the LLM reranker kept the right chunk for
   both phrasings. The earlier retriever-only A/B used the raw golden questions, so it missed this.
2. **`pol-hra` misrouted to conversational in 2/5 runs** (planner, not retrieval) — the only route failures.
3. **Data route was broken before these runs** (1/5 correct): the SQLite sandbox authorizer from `6aa0305`
   denied the rowid read SQLite makes when it flattens a view (`WHERE user_id = (SELECT id FROM me)`).
   Fixed in `app/safe_sql.py`, regression tests in `test_agent.py`; 5/5 in every run since.
4. **Judge noise exceeds compare.py tolerances** on 9 metrics: single-run spreads of 0.10–0.25 on
   quality/safety scores vs tolerances of 0.02–0.05, and route % varies by one question (5 %). As configured,
   `evals.compare` will flag REVIEW/FAIL from noise alone. 8 policy cases is a small sample: one question
   flipping moves a quality mean by 0.125.

## Next

- Revert the default to `RERANKER=llm` (or keep FlashRank but add the top-2 vector hits unconditionally),
  re-run 5×, and re-baseline.
- Set tolerances from `runs/spread.json` (e.g. max |run − mean| per metric) instead of the fixed 0.02/0.05,
  or grow the policy golden set so one question moves the mean less.
