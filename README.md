# DISHA HR

Mobile-friendly HR app: **Next.js** frontend → **FastAPI** backend → **SQLite now, PostgreSQL later**, with
**Disha**, an AI assistant (LangGraph, OpenAI, Qdrant RAG, guarded text-to-SQL) behind a chat button on every page.

Live at **https://13.201.82.67.sslip.io** (AWS EC2), deployed by GitHub Actions on every push to `main` — see Deploy.

## How it works

The app also serves this as a page at `/how-it-works` (no login needed).

![Disha answering a data question and a policy question, with the path each answer took](frontend/public/disha-chat.png)

**The LangGraph planner** (`backend/app/agent.py`; nodes and edges match `graph.get_graph().draw_mermaid()`). The
answer is written after the graph ends, so it can stream, then the output rail checks it.

```mermaid
graph TD;
  start([question]) --> guard_plan["guard_plan<br/>input rail ∥ planner"];
  guard_plan -.policy.-> retrieve["retrieve<br/>Qdrant RAG + rerank"];
  guard_plan -.data.-> query_data["query_data<br/>text-to-SQL on scoped views"];
  guard_plan -.small talk / refused.-> responder;
  retrieve --> responder["responder (streamed)"];
  query_data --> responder;
  responder --> rail["output rail"] --> done([answer]);
```

**Evals**: 21 golden questions through the live API, mean of 5 runs (full table and findings in
[`backend/evals/baselines/RESULTS.md`](backend/evals/baselines/RESULTS.md)):

| | Current (2026-09-25) | Previous (FlashRank) |
|---|---|---|
| Route / data / safety checks | 100% / 100% / 100% | 98% / 100% / 100% |
| Correctness · completeness | 0.92 · 0.84 | 0.73 · 0.70 |
| Contextual recall · precision | 1.00 · 1.00 | 0.80 · 0.84 |
| Latency p50 / p95 | 5.2s / 8.5s* | 7.9s / 10.1s |

\* two of the five runs hit a flaky local network; the other three had p95 6.7-7.9s.

**A real trace** (LangSmith), *"A client wants to give me a gift. When do I have to declare it?"*:
`guard_plan` 1.40s → `retrieve` 2.73s (2 passages) → `responder` 1.31s, about 5.5s end to end.

## Setup (Windows)
1. `pip install -r backend/requirements.txt`
2. `cd frontend && npm install`

Data lives in `backend/disha.db` (SQLite). To switch to PostgreSQL: install it, `CREATE DATABASE disha`, and set
`DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/disha` — tables are created on first start.
Then run `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/disha_test node test.mjs` once to confirm.

## Run
```
cd backend && uvicorn app.main:app --reload     # API on :8000, docs at http://localhost:8000/docs
cd frontend && npm run dev                      # app on http://localhost:3000 (and http://<PC-IP>:3000 on phones)
cd backend && python -m app.seed                # optional: 20 dummy employees, Jan 2026 → yesterday (password123)
node test.mjs                                   # API contract tests on a throwaway disha_test database
```
First API start prints the admin login (`admin@company.com` / random password; or set `ADMIN_PASSWORD`).
Env: `DATABASE_URL`, `ADMIN_PASSWORD`, `TZ` (attendance uses server time), `HTTPS=1` (Secure cookie behind TLS),
`API_URL` (frontend → API, default `http://127.0.0.1:8000`). Keys live in `backend/.env` (see `.env.example`):
`OPENAI_API_KEY` for chat, `QDRANT_*` for policy answers, `LOGFIRE_TOKEN` and `LANGSMITH_*` for tracing,
`JUDGE_MODEL` for the evals.

## Deploy (AWS)

`.github/workflows/ci-cd.yml` runs on every push to `main`; each stage starts only if the previous one passed.
Pull requests run the first two stages only.

| Stage | What it does |
|---|---|
| **test** | `test_agent.py`, `test_knowledge.py`, `node test.mjs`, frontend build |
| **evaluate** | seeds a throwaway API, runs `evals.run --no-judge`, then `evals.compare` against the baseline: a safety drop **fails**, a quality/latency drop only **warns** |
| **push** | builds the backend and frontend images, pushes them to ECR repo `dishahr` as `backend-<sha>` / `frontend-<sha>` |
| **deploy** | SSH to the EC2 box, writes `backend.env` from secrets, `docker compose up` with `deploy/docker-compose.yml`, health check over HTTPS |

On the server: **Caddy** (HTTPS via Let's Encrypt for `<ip>.sslip.io`; plain HTTP and the bare IP redirect to it)
→ Next.js → FastAPI, with SQLite on a Docker volume (or Postgres if the `DATABASE_URL` secret is set).

GitHub secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `EC2_SSH_KEY` (the `.pem`), `BACKEND_ENV` (the whole
`backend/.env`), `ADMIN_PASSWORD`, optional `DATABASE_URL`. Variable: `EC2_HOST`. The `.pem` and access-key CSV are
gitignored; keep them out of the repo folder.

Run a command on the server (e.g. seed the demo data once):
```
ssh -i dishahr.pem ubuntu@13.201.82.67 "sudo docker compose exec -T backend python -m app.seed"
```
Roll back: re-run an older successful workflow run from the Actions tab (its images are still in ECR).
ECR keeps the 10 newest backend and frontend images (`deploy/ecr-lifecycle.json`, applied with
`aws ecr put-lifecycle-policy --repository-name dishahr --lifecycle-policy-text file://deploy/ecr-lifecycle.json`),
so rollback reaches 10 deploys back.

## Disha assistant (agentic)

```
question -> input rail -> planner -> conversational          -> responder -> output rail -> answer
                                  -> policy  (Qdrant RAG)    -^
                                  -> data    (text-to-SQL)   -^
```

- **Planner** (`app/agent.py`, LangGraph) decides the route, so small talk never touches retrieval.
- **Policy route** searches company policies in Qdrant (`data/policies/*.md`, OpenAI embeddings).
- **Data route** writes SQL — but only against **temp views already scoped to the asking employee**
  (`app/safe_sql.py`): one SELECT, whitelisted view names, forced row limit, own connection that is
  never pooled. Managers also see their team's leaves and expenses; admins see everything.
- **Guardrails** (`app/rails.py`, NeMo) screen the question and the answer; both degrade to open if unavailable.
- **Tracing**: Logfire spans per node (`LOGFIRE_TOKEN`), and LangSmith traces of the same nodes plus every prompt
  and completion (`LANGSMITH_API_KEY` + `LANGSMITH_TRACING=true`; the OpenAI client is wrapped when the key is set).
- **Caching**: a policy question's embedding is cached with no expiry, and its search results (Qdrant + rerank)
  for `SEARCH_CACHE_SECONDS` (default 600), in memory per worker. Data answers and SQL are never cached: they are
  per user and read live data.
- **Rate limit**: 8 questions a minute and 50 an hour per employee; a refusal says how long to wait.
  Held in memory, so the cap is per API process — move it to a table before running several workers.
  Override with `CHAT_LIMIT_PER_MINUTE` / `CHAT_LIMIT_PER_HOUR`.

Setup: copy `backend/.env.example` to `backend/.env` and fill in `OPENAI_API_KEY` (plus Qdrant keys for
policy answers), then index the policies:

```
cd backend && python -m app.knowledge --wipe    # embeds data/policies/*.md into Qdrant
```

Checks without OpenAI or Qdrant calls: `cd backend && python test_agent.py`

### Evals (DeepEval)
`backend/evals/golden.json` holds the golden question set — policy, data, safety and small-talk cases. The harness
asks them through the **running API**, so it measures the deployed system, and scores two ways:

- **deterministic** — was the right route taken; does a data answer contain the number that `truth_sql` returns from
  the live database; did a safety question leak anything. No judge, no cost, never flaky.
- **judged (DeepEval)** — faithfulness, answer relevancy, contextual precision/recall and a GEval correctness check
  over the policy answers, each with a written reason stored in `evals/report.json`.

```
cd backend
pip install -r evals/requirements.txt
python -m evals.run                 # API must be running on :8000
python -m evals.run --no-judge      # deterministic half only, no judge calls
python -m evals.run --from-report   # re-judge saved answers without asking the agent again
python -m evals.traces --hours 2    # recent LangSmith traces for the same runs
python -m evals.compare             # latest run vs baseline -> PASS / REVIEW / FAIL (exit 0 / 2 / 1)
```

Current baseline (2026-09-25, mean of 5 runs, judge `gpt-5.4-mini`): routes 100%, data 100%, safety refusals
100%; contextual precision 1.00, contextual recall 1.00, faithfulness 0.99, correctness 0.92, completeness 0.84,
answer relevancy 0.80; latency p50 5.2s / p95 8.5s (two runs hit a flaky local network; the other three were
6.7-7.9s). Per-run values, spread and findings are in
[`backend/evals/baselines/RESULTS.md`](backend/evals/baselines/RESULTS.md). Answer relevancy is docked for the
trailing source tag (`… (Leave Policy)`) that we deliberately keep for provenance. Judged scores vary 0.07–0.22
between runs, more than `compare`'s tolerances, so treat a single-run REVIEW/FAIL on a judged metric as a prompt to
re-run, not a verdict. For repeated local runs, raise `CHAT_LIMIT_PER_MINUTE` / `CHAT_LIMIT_PER_HOUR` in
`backend/.env` so the chat rate limit doesn't interrupt them. (RAGAS was tried first and dropped — it pins
`openai<2`, needs a pinned old `langchain-community` to import, and sends `max_tokens`, which the gpt-5 models
reject.)

## Layout
| Path | What |
|---|---|
| `backend/app/db.py` | Postgres schema, password hashing, working-day helper |
| `backend/app/main.py` | FastAPI routes + permission rules |
| `backend/app/seed.py` | dummy data |
| `backend/app/agent.py` | Disha agent graph: planner, retriever, text-to-SQL, responder |
| `backend/app/safe_sql.py` | per-employee views + SQL validation for the data route |
| `backend/app/knowledge.py` | policy chunking, embeddings, Qdrant search + `--wipe` ingest |
| `backend/app/rails.py` | NeMo Guardrails input/output checks |
| `backend/test_agent.py` | SQL sandbox + routing checks (no OpenAI calls) |
| `data/policies/*.md` | company policies answered from (sample content, replace for real use) |
| `frontend/app/(app)/*/page.js` | one page per module; `frontend/components/` shared shell + UI |
| `frontend/components/DishaChat.js` | the Disha chat, opened from the floating button in `Shell.js` |
| `test.mjs` | HTTP tests for access control, approvals, leave rules |
| `.github/workflows/ci-cd.yml` | test → evaluate → push → deploy pipeline |
| `deploy/docker-compose.yml` | backend, frontend and Caddy on the EC2 box |

## Modules
| Module | User | Admin |
|---|---|---|
| Employees | directory, edit own phone, change password | add/edit/deactivate, roles, reset password |
| Attendance | check-in / check-out, monthly view | all employees, regularise |
| Leaves | balance (CL 12 / SL 12 / EL 15 / LWP), apply, cancel; managers approve their team | approve / reject any, holiday calendar |
| Expenses | claim with receipt, cancel; managers approve their team | approve / reject any |
| Announcements | read on dashboard | post / delete |
| Payslips | view, print / save PDF | create / update monthly |
| Goals | create, update progress | assign to anyone |
| Documents | upload / download own (≤7 MB) | any employee |

## Roadmap
Next: **backups** (PostgreSQL, or at least a nightly copy of the SQLite file to S3; today the data lives on one EC2
volume); a least-privilege IAM user for CI; **Disha actions** (apply for leave, approve a
request from chat, with a confirmation step).

Later: email/WhatsApp notifications; payroll engine (PF/ESI/PT/TDS, Form 16); geo/selfie attendance, shifts;
onboarding/offboarding; performance reviews; helpdesk; reports/CSV, audit log, org chart; PWA, SSO, 2FA; files to S3.
