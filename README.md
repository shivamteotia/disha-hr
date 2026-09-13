# DISHA HR

Mobile-friendly HR app: **Next.js** frontend → **FastAPI** backend → **SQLite now, PostgreSQL later**.
The AI layer (orchestrator, RAG with pgvector, OpenAI, Logfire, RAG Triad) comes next — see Roadmap.

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
- **Rate limit**: 8 questions a minute and 50 an hour per employee; a refusal says how long to wait.
  Held in memory, so the cap is per API process — move it to a table before running several workers.

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
```

Last run: routes 17/17, data 5/5, safety 3/3; contextual precision 1.00, contextual recall 1.00, faithfulness 0.96,
correctness 0.91, answer relevancy 0.77. Relevancy reads low because the judge penalises the trailing source tag
(`… (Leave Policy)`) that we deliberately keep for provenance — the answers themselves are correct and complete. (RAGAS was tried first and dropped — it pins `openai<2`, needs a
pinned old `langchain-community` to import, and sends `max_tokens`, which the gpt-5 models reject.)

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
| `test.mjs` | HTTP tests for access control, approvals, leave rules |

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
Next: **Disha assistant** — AI orchestrator calling the permission-checked API functions as tools (never raw SQL),
RAG over policy documents (S3 + pgvector), OpenAI, Logfire tracing with PII scrubbing, RAG Triad evals on a golden question set.

Later: email/WhatsApp notifications; payroll engine (PF/ESI/PT/TDS, Form 16); geo/selfie attendance, shifts;
onboarding/offboarding; performance reviews; helpdesk; reports/CSV, audit log, org chart; PWA, SSO, 2FA; files to S3.
