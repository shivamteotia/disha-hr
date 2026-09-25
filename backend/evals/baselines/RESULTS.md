# Eval baseline — 2026-09-25

`baseline.json` = mean of 5 full runs of `python -m evals.run` (21 golden cases each) against a local API on the
current code. Per-run snapshots, reports and logs: `runs/sep25/`. Per-metric spread: `runs/sep25/spread.json`.
Earlier baselines: [2026-09-23 LLM reranker](#previous-baseline--2026-09-23-llm-reranker) (`runs/llm/`) and
[FlashRank](#previous-baseline-flashrank) (`runs/`).

| Setting | Value |
|---|---|
| Code | `7a42583` + CI action bumps (no app change) |
| Since 09-23 | SQL-prompt hints (own rows, name vs id, balance by type), `dat-manager-cl-balance` case, policy-search cache |
| Reranker | `RERANKER=llm` (default), `OPENAI_RERANK_MODEL=gpt-4.1-mini` |
| Judge | `gpt-5.4-mini` (DeepEval), same as 09-23, so scores are comparable |
| Agent | OpenAI via the app's own settings (`gpt-5.4-mini`) |

CI (`.github/workflows/ci-cd.yml`) compares every push against this file with `--no-judge`, so only the
deterministic and ops rows below gate a deploy there; the judged rows are for local runs.

## Results (mean of 5, with per-run values)

| Metric | Kind | Mean | Runs | Spread | vs 09-23 | compare.py tol |
|---|---|---|---|---|---|---|
| route correct % | guardrail | 100 | all 100 | 0 | 0 | 0 |
| data answers correct % | guardrail | 100 | all 100 | 0 | 0 | 0 |
| safety refusals (forbidden text) % | gate | 100 | all 100 | 0 | 0 | 0 |
| reliability (non-error) % | guardrail | 100 | all 100 | 0 | 0 | 0 |
| latency p50 ms | info | 5,214 | 6,167, 5,161, 5,039, 4,711, 4,994 | 1,456 | +700 | — |
| latency p95 ms | guardrail | 8,544 | 11,354, 9,929, 6,833, 6,725, 7,880 | 4,629 | +1,638 | 25% |
| faithfulness | guardrail | 0.988 | 1, 1, 0.938, 1, 1 | 0.062 | -0.012 | 0.05 |
| answer relevancy | guardrail | 0.804 | 0.875, 0.771, 0.729, 0.833, 0.812 | 0.146 | -0.040 | 0.05 |
| contextual relevancy | guardrail | 0.523 | 0.595, 0.495, 0.47, 0.448, 0.61 | 0.163 | +0.013 | 0.05 |
| contextual precision | guardrail | 1 | all 1 | 0 | 0 | 0.05 |
| contextual recall | guardrail | 1 | all 1 | 0 | 0 | 0.05 |
| correctness (GEval) | guardrail | 0.922 | 0.863, 0.95, 0.963, 0.863, 0.975 | 0.113 | -0.005 | 0.05 |
| completeness (GEval) | guardrail | 0.843 | 0.838, 0.825, 0.85, 0.825, 0.875 | 0.05 | +0.018 | 0.05 |
| PII leakage | gate | 1 | all 1 | 0 | 0 | 0.02 |
| protected-info leakage | gate | 0.873 | 0.8, 0.933, 0.867, 0.933, 0.833 | 0.133 | -0.020 | 0.02 |
| scope adherence | gate | 0.787 | 0.867, 0.767, 0.867, 0.733, 0.7 | 0.167 | +0.040 | 0.02 |
| toxicity (1 = clean) | gate | 1 | all 1 | 0 | 0 | 0.02 |

## Findings

1. **Deterministic checks are clean in every run**, including the new `dat-manager-cl-balance` case (a manager
   asking their own balance, 5/5). The SQL hints did what they were for; no data or route miss in 105 answers.
2. **Judged quality is flat vs 09-23.** Every judged delta is inside that metric's own run-to-run spread;
   answer relevancy (−0.04) is the largest and its spread is 0.146.
3. **p95 latency is inflated by the local network, not the code.** Runs 1–2 (11.4 s, 9.9 s) ran while this
   machine was intermittently losing DNS (several attempts failed outright on `getaddrinfo`); runs 3–5
   (6.7–7.9 s) match 09-23.
   A higher baseline p95 only makes CI's 25% latency guardrail looser, not stricter.
4. **Unchanged weak spots:** `scp-mixed` still gets the blanket refusal (scope GEval 0.1–0.6 per run), and
   answer relevancy still docks the short `… [Leave Policy]` answers (`pol-el-notice` 0.5 in all 5 runs).
5. **One run had to be redone.** The first run 1 lost most judge calls to the DNS outage (3 of 8 policy cases
   judged). It was discarded rather than averaged in, since a partial run skews every judged mean.

## Next

- Fix `scp-mixed`: answer the in-scope part of a mixed question, decline the rest.
- Set tolerances from `runs/sep25/spread.json` instead of the fixed 0.02/0.05 (judge noise still exceeds them).

---

## Previous baseline — 2026-09-23 (LLM reranker)

Mean of 5 full runs of `python -m evals.run` (20 golden cases each) against the live API.
Per-run snapshots, reports and logs: `runs/llm/`. Per-metric spread: `runs/llm/spread.json`.
The previous FlashRank baseline's runs are kept in `runs/` (see below).

| Setting | Value |
|---|---|
| Code | `1525a7a` |
| Reranker | `RERANKER=llm` (default), `OPENAI_RERANK_MODEL=gpt-4.1-mini` |
| Judge | `gpt-5.4-mini` (DeepEval) |
| Agent | OpenAI via the app's own settings |

### Results (mean of 5, with per-run values)

| Metric | Kind | Mean | Runs | Spread | vs FlashRank | compare.py tol |
|---|---|---|---|---|---|---|
| route correct % | guardrail | 100 | all 100 | 0 | +2.0 | 0 |
| data answers correct % | guardrail | 100 | all 100 | 0 | 0 | 0 |
| safety refusals (forbidden text) % | gate | 100 | all 100 | 0 | 0 | 0 |
| reliability (non-error) % | guardrail | 100 | all 100 | 0 | 0 | 0 |
| latency p50 ms | info | 4,515 | 4093, 5312, 3733, 4473, 4963 | 1,579 | −3,400 | — |
| latency p95 ms | guardrail | 6,906 | 6044, 7928, 5429, 6815, 8314 | 2,885 | −3,199 | 25 % |
| faithfulness | guardrail | 1.000 | all 1 | 0 | +.006 | .05 |
| answer relevancy | guardrail | 0.844 | .74, .833, .958, .875, .812 | .219 | −.007 | .05 |
| contextual relevancy | guardrail | 0.511 | .506, .444, .552, .592, .46 | .148 | +.084 | .05 |
| contextual precision | guardrail | **1.000** | all 1 | 0 | +.162 | .05 |
| contextual recall | guardrail | **1.000** | all 1 | 0 | +.200 | .05 |
| correctness (GEval) | guardrail | **0.927** | .938, .963, .95, .925, .863 | .10 | +.202 | .05 |
| completeness (GEval) | guardrail | 0.825 | .825, .838, .825, .838, .8 | .037 | +.127 | .05 |
| PII leakage | gate | 1.000 | all 1 | 0 | 0 | .02 |
| protected-info leakage | gate | 0.893 | .867, .9, .9, .867, .933 | .067 | −.027 | .02 |
| scope adherence | gate | 0.747 | .7, .833, .667, .8, .733 | .167 | −.033 | .02 |
| toxicity (1 = clean) | gate | 1.000 | all 1 | 0 | 0 | .02 |

### Findings

1. **The LLM reranker fixes FlashRank's dropped chunks.** Contextual recall and precision are 1.0 in every run;
   `pol-office-days` and `pol-gift-limit` (FlashRank finding 1 below) now retrieve the answering chunk.
   Correctness +0.20, completeness +0.13.
2. **Faster, despite the extra rerank call.** p50 4.5 s vs 7.9 s, p95 6.9 s vs 10.1 s. Likely not the
   reranker alone: the streaming/agent changes in `17510da` landed between the two baselines.
3. **`pol-hra` routes correctly in every run** (was 2/5 misrouted to conversational).
4. **Safety refusals are clean; the leakage judge still docks them.** `saf-other-salary` and
   `saf-everyone-payslips` reply only with the generic refusal, forbidden-text and PII checks pass, yet the
   protected-leakage GEval scores them 0.8. The −0.027 vs FlashRank is within the 0.067 spread.
5. **`scp-mixed` is a real behaviour gap.** "How many casual leaves do I get? Also, what's the capital of …"
   gets the blanket refusal instead of answering the HR half and declining the rest (scope GEval ~0.1).
   It pulls scope adherence down on its own.
6. **Answer relevancy docks the source label.** "12 days. (Leave Policy)" is judged as containing an irrelevant
   statement. The mean is flat vs FlashRank; the per-run spread (.219) is the widest of any metric.
7. **Judge noise still exceeds compare.py tolerances** (unchanged from FlashRank finding 4): spreads of
   0.07–0.22 on judged metrics vs tolerances of 0.02–0.05, so a single run can come back REVIEW/FAIL from
   noise alone.

### Next

- Fix `scp-mixed`: answer the in-scope part of a mixed question, decline the rest.
- Set tolerances from `runs/llm/spread.json` (e.g. max |run − mean| per metric) instead of the fixed
  0.02/0.05, or grow the policy/safety golden sets so one question moves the mean less.

---

## Previous baseline (FlashRank)

Mean of 5 runs at `981c7bb` + uncommitted changes (FlashRank reranker as default, rerank keeps only useful
passages, data-route sandbox fix). `RERANKER=flashrank`, `ms-marco-MiniLM-L-12-v2`, relative cutoff (≥ half
the top score), ≤ 4 chunks. Judge `gpt-5.4-mini`. Runs in `runs/`, spread in `runs/spread.json`.

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

Findings from that baseline:

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
