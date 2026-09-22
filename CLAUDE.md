# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

DISHA HR: mobile-friendly HR app. Next.js frontend → FastAPI backend → SQLite now / PostgreSQL later.
Includes an agentic assistant ("Disha") built on LangGraph with RAG (Qdrant) and text-to-SQL.

## Commands

Setup:
```
pip install -r backend/requirements.txt
cd frontend && npm install
```

Run:
```
cd backend && uvicorn app.main:app --reload     # API on :8000, docs at http://localhost:8000/docs
cd frontend && npm run dev                      # app on http://localhost:3000
cd backend && python -m app.seed                # optional: 20 dummy employees (password123)
```

Tests:
```
node test.mjs                                   # API contract tests, against a throwaway *_test database
cd backend && python test_agent.py              # SQL sandbox + routing checks, no OpenAI calls
```
`test.mjs` needs `TEST_DATABASE_URL` set when testing against Postgres; SQLite is the default and needs no setup.
There is no single-test runner for `test.mjs` or `test_agent.py` — both are plain scripts you run whole.

Frontend build: `cd frontend && npm run build` (no separate lint/typecheck script is configured).

Database reset (only works on a `*_test` database, refuses otherwise):
```
cd backend && python -m app.db --reset
```

Disha assistant setup and evals:
```
cd backend && python -m app.knowledge --wipe    # embeds data/policies/*.md into Qdrant

pip install -r evals/requirements.txt
python -m evals.run                 # API must be running on :8000; golden set in evals/golden.json
python -m evals.run --no-judge      # deterministic checks only, no judge/LLM calls
python -m evals.run --from-report   # re-judge saved answers without re-asking the agent
python -m evals.traces --hours 2    # recent LangSmith traces for the same runs
```

Env vars live in `backend/.env` (copy from `backend/.env.example`): `DATABASE_URL`, `ADMIN_PASSWORD`, `TZ`,
`HTTPS` (Secure cookie behind TLS), `API_URL` (frontend proxy target), `OPENAI_API_KEY`, `QDRANT_*`,
`LOGFIRE_TOKEN`, `LANGSMITH_*`, `JUDGE_MODEL`.

## Architecture

**Split repo, one DB.** `backend/app/db.py` defines the whole schema with SQLAlchemy Core (not the ORM) and
raw parameterized SQL (`db.py`'s `rows`/`row`/`run` helpers) written to run unchanged on SQLite and Postgres —
dates/times are always bound as ISO strings so both backends agree. `DATABASE_URL` selects the engine; unset,
it falls back to a local `backend/disha.db` SQLite file. Schema changes go in `db.py`'s table definitions;
there's no migration tool, tables are created on first start via `init()`.

**Auth**: cookie session (`sid`) → `sessions` table row → `users` row, looked up per-request in
`current_user()` (`backend/app/main.py`). Two roles only, `user` and `admin`; managers are just users whose
`manager_id` is referenced by others, so "am I this person's manager" is a query, not a role. Permission
checks live inline in each route in `main.py`, not in a separate authorization layer.

**Frontend** talks to the API only through `frontend/lib.js`'s `api()` helper, which calls same-origin `/api/*`
— `next.config.mjs` rewrites that to `API_URL` (default `http://127.0.0.1:8000`) so the session cookie stays
same-origin even from phones on the LAN. There's no client-side data-fetching library; `useLoad()` in `lib.js`
is the shared "fetch on mount / reload" hook. Routes live under `frontend/app/(app)/<module>/page.js`, one
page per HR module (attendance, leaves, expenses, payslips, goals, documents, employees, disha), sharing
`frontend/components/Shell.js` (layout/nav) and `frontend/components/ui.js` (form/table primitives).

**Disha assistant** (`backend/app/agent.py`, LangGraph) routes a question through:
```
question -> input rail -> planner -> conversational          -> responder -> output rail -> answer
                                  -> policy  (Qdrant RAG)    -^
                                  -> data    (text-to-SQL)   -^
```
- The **planner** picks the route so small talk skips retrieval entirely.
- The **policy** route embeds and searches `data/policies/*.md` in Qdrant (OpenAI embeddings); reindex with
  `python -m app.knowledge --wipe`.
- The **data** route generates SQL but only against **temp views already scoped to the asking employee**
  (`backend/app/safe_sql.py`) — one SELECT, whitelisted view names, forced row limit, a connection that is
  never pooled. This is the load-bearing security boundary for the agent: it must never gain access to raw
  tables or write access. Managers' views additionally expose their team's leaves/expenses; admins see
  everything.
- **Guardrails** (`backend/app/rails.py`, NeMo) screen both the question and the answer, and degrade to open
  (not fail-closed) if the guardrail service is unavailable.
- **Tracing** is dual: Logfire spans per graph node (`LOGFIRE_TOKEN`) and LangSmith traces of the same nodes
  plus every prompt/completion (`LANGSMITH_API_KEY` + `LANGSMITH_TRACING=true`; the OpenAI client is wrapped
  when the key is set).
- **Rate limiting** (8/min, 50/hour per employee) is held in memory in the API process — see the `ponytail:`
  comment in `main.py` before assuming it holds across multiple workers.

**Evals** (`backend/evals/`) hit the *running* API rather than calling the agent in-process, so they measure
the deployed system. `evals/golden.json` is the question set; scoring is deterministic (route taken, does a
data answer contain the number `truth_sql` returns from the live DB, does a safety question leak anything —
no judge, never flaky) plus DeepEval-judged metrics (faithfulness, answer relevancy, contextual
precision/recall, GEval correctness) written to `evals/report.json` with reasons. RAGAS was tried and dropped
(pins `openai<2`, needs an old pinned `langchain-community`, sends `max_tokens` which gpt-5 models reject) —
don't reintroduce it without checking those constraints still apply.

## Layout

| Path | What |
|---|---|
| `backend/app/db.py` | schema, password hashing (scrypt, salt:hex — compatible with a prior Node app), working-day helper |
| `backend/app/main.py` | FastAPI routes + inline permission rules |
| `backend/app/seed.py` | dummy data |
| `backend/app/agent.py` | Disha agent graph |
| `backend/app/safe_sql.py` | per-employee views + SQL validation for the data route |
| `backend/app/knowledge.py` | policy chunking, embeddings, Qdrant search + `--wipe` ingest |
| `backend/app/rails.py` | NeMo Guardrails input/output checks |
| `backend/test_agent.py` | SQL sandbox + routing checks (no OpenAI calls) |
| `data/policies/*.md` | company policies the policy route answers from (sample content) |
| `frontend/app/(app)/*/page.js` | one page per HR module |
| `frontend/lib.js` | `api()` fetch wrapper, `useLoad()`, small formatting helpers |
| `test.mjs` | HTTP contract tests: access control, approvals, leave rules |

## Modules and permissions

| Module | User | Admin |
|---|---|---|
| Employees | directory, edit own phone, change password | add/edit/deactivate, roles, reset password |
| Attendance | check-in / check-out, monthly view | all employees, regularise |
| Leaves | balance (CL 12 / SL 12 / EL 15 / LWP), apply, cancel; managers approve their team | approve/reject any, holiday calendar |
| Expenses | claim with receipt, cancel; managers approve their team | approve/reject any |
| Announcements | read on dashboard | post/delete |
| Payslips | view, print/save PDF | create/update monthly |
| Goals | create, update progress | assign to anyone |
| Documents | upload/download own (≤7 MB) | any employee |

Leave quotas (`QUOTA` in `main.py`) are fixed per year for everyone — deliberately not per-grade/location yet
(marked with a `ponytail:` comment there).
