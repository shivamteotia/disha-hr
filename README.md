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
`API_URL` (frontend → API, default `http://127.0.0.1:8000`).

## Layout
| Path | What |
|---|---|
| `backend/app/db.py` | Postgres schema, password hashing, working-day helper |
| `backend/app/main.py` | FastAPI routes + permission rules |
| `backend/app/seed.py` | dummy data |
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
