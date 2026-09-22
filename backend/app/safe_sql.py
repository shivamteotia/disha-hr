"""Text-to-SQL sandbox.

The model never sees the real tables. For each question we create TEMP VIEWS that already contain only
the rows the asking employee may see, then allow a single read-only SELECT over those view names.
Four layers: (1) the views filter rows, (2) the SQL is validated, (3) a row limit is forced,
(4) the database refuses any read of a real table made straight from the query: an authorizer on SQLite,
a NOLOGIN role with no table grants (`SET LOCAL ROLE`) on PostgreSQL. Views still work on both because
their body is checked against the view owner, not the caller.

ponytail: the Postgres role needs the app's DB user to hold CREATEROLE (Neon's default owner does); if it
cannot create/assume the role, run_sql returns an error instead of running unguarded. Not yet added:
`SET TRANSACTION READ ONLY`, and the role can still read pg_catalog (role names, not data).
"""
import re
import sqlite3

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from .db import DATABASE_URL, IS_SQLITE, md

# Its own engine with NullPool: every sandbox query gets a fresh connection that is closed afterwards.
# On a pooled connection the temp views would outlive the request and shadow the real tables for
# whatever query ran next — the app's own SELECTs must always see the real tables.
sandbox_engine = create_engine(DATABASE_URL, poolclass=NullPool,
                               connect_args={"check_same_thread": False} if IS_SQLITE else {})

MAX_ROWS = 200
MAX_SQL = 2000
# The views share their names with the real tables, so inside a view body the base table must be
# qualified — otherwise the view refers to itself ("circularly defined").
BASE = "main." if IS_SQLITE else "public."
TEMP = "temp" if IS_SQLITE else "pg_temp"

ROLE = "disha_sandbox"  # Postgres only: NOLOGIN, granted SELECT on the temp views and nothing else
_role_ready = False
# set_config('role', ...) would let a query climb back out of ROLE
BANNED = re.compile(r"\b(set_config|attach|detach|pragma|insert|update|delete|drop|alter|create|grant|revoke|"
                    r"vacuum|reindex|load_extension|sqlite_master|sqlite_schema|information_schema|recursive)\b", re.I)
TABLES_IN_SQL = re.compile(r"\b(?:from|join)\s+[\"`\[]?([A-Za-z_][A-Za-z0-9_]*)", re.I)
# FROM also appears inside EXTRACT(month FROM date), which is not a table read; WITH names are the query's own.
EXTRACT_FROM = re.compile(r"\bextract\s*\(\s*\w+\s+from\b", re.I)
CTE_NAME = re.compile(r"\b([A-Za-z_]\w*)\s+as\s*\(", re.I)


def _authorizer(views):
    """SQLite authorizer: a query may read only the temp views. Reads that a view itself triggers (its body
    selects from the real tables) carry the view's name as `source`, so they pass; a direct read does not."""
    def auth(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_READ and source is None and arg1.lower() not in views:
            return sqlite3.SQLITE_DENY
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    return auth


def _ensure_role():
    """Create the sandbox role once per process and let the app's own DB user assume it."""
    global _role_ready
    if _role_ready:
        return
    with sandbox_engine.begin() as c:
        try:
            c.exec_driver_sql(f"CREATE ROLE {ROLE} NOLOGIN")
        except Exception:  # noqa: BLE001 - already exists (or another worker just made it)
            pass
    with sandbox_engine.begin() as c:
        c.exec_driver_sql(f"GRANT {ROLE} TO CURRENT_USER")
    _role_ready = True


def views_for(user) -> dict[str, str]:
    """View name -> SELECT that is already scoped to this user. Ids are ints, so they are safe to inline."""
    me = int(user["id"])
    admin = user["role"] == "admin"
    own = "" if admin else f"WHERE t.user_id = {me}"
    # managers also see their direct reports' leaves and expenses, exactly like the app
    team = "" if admin else f"WHERE (t.user_id = {me} OR u.manager_id = {me})"
    return {
        "me": f"SELECT id, emp_code, name, email, dept, designation, phone, doj, manager_id, role FROM {BASE}users WHERE id = {me}",
        "employees": (f"SELECT id, emp_code, name, email, dept, designation, phone, doj, manager_id, role, active FROM {BASE}users"
                      if admin else
                      f"SELECT id, emp_code, name, email, dept, designation, manager_id FROM {BASE}users WHERE active"),
        "attendance": f"""SELECT t.id, t.user_id, u.name AS employee, t.date, t.check_in, t.check_out
                          FROM {BASE}attendance t JOIN {BASE}users u ON u.id = t.user_id {own}""",
        "leaves": f"""SELECT t.id, t.user_id, u.name AS employee, t.type, t.from_date, t.to_date, t.days,
                             t.reason, t.status FROM {BASE}leaves t JOIN {BASE}users u ON u.id = t.user_id {team}""",
        "expenses": f"""SELECT t.id, t.user_id, u.name AS employee, t.date, t.category, t.amount, t.description,
                               t.status FROM {BASE}expenses t JOIN {BASE}users u ON u.id = t.user_id {team}""",
        "payslips": f"""SELECT t.id, t.user_id, u.name AS employee, t.month, t.basic, t.hra, t.allowances,
                               t.deductions, t.basic + t.hra + t.allowances AS gross,
                               t.basic + t.hra + t.allowances - t.deductions AS net
                        FROM {BASE}payslips t JOIN {BASE}users u ON u.id = t.user_id {own}""",
        "goals": f"""SELECT t.id, t.user_id, u.name AS employee, t.title, t.description, t.due, t.progress,
                            t.status FROM {BASE}goals t JOIN {BASE}users u ON u.id = t.user_id {own}""",
        "holidays": f"SELECT id, date, name FROM {BASE}holidays",
        "announcements": f"SELECT id, title, body, created FROM {BASE}announcements",
    }


SCHEMA_DOC = """Views you may query (each is ALREADY filtered to what this user is allowed to see):

me(id, emp_code, name, email, dept, designation, phone, doj, manager_id, role) - one row: the asking user
  role is only 'user' or 'admin' - there is NO 'manager' role. Someone is a manager because other
  employees have manager_id = their id. Never filter on role to find managers; to count a manager's
  team use employees.manager_id = (SELECT id FROM me), and note the leaves and expenses views already
  contain the team's rows for a manager, so a plain WHERE status='pending' over them is usually right.
employees(id, emp_code, name, email, dept, designation, manager_id[, phone, doj, role, active for admins]) - directory
attendance(id, user_id, employee, date, check_in, check_out) - one row per day worked
leaves(id, user_id, employee, type, from_date, to_date, days, reason, status) - type: CL/SL/EL/LWP; status: pending/approved/rejected/cancelled
expenses(id, user_id, employee, date, category, amount, description, status)
payslips(id, user_id, employee, month, basic, hra, allowances, deductions, gross, net) - month is 'YYYY-MM'
goals(id, user_id, employee, title, description, due, progress, status)
holidays(id, date, name)
announcements(id, title, body, created)

Rules: one SELECT statement only; query only the views above (never a table); dates are 'YYYY-MM-DD' text;
leave `days` already counts working days (weekends and company holidays excluded). Regular employees see only
their own rows; managers also see their team's leaves and expenses; admins see everyone.

Leave balance (must match the app, which shows the same numbers):
  yearly quota is CL 12, SL 12, EL 15; LWP is unlimited and has no balance
  used  = SUM(days) for that type where status IN ('approved','pending') and from_date is in the year asked about
          -- pending requests already hold the days; 'rejected' and 'cancelled' never count
  left  = quota - used
Attendance: one row per day actually worked; there is no row for weekends, holidays, leave or absence.
  A "miss punch" is a day where check_in or check_out is null (forgot to punch in/out) - count with
  check_in IS NULL OR check_out IS NULL, filtered to the month/date range asked about."""


def check(sql: str) -> str | None:
    """Return an error message if this SQL may not run."""
    s = sql.strip().rstrip(";").strip()
    if not s:
        return "Empty query"
    if len(s) > MAX_SQL:
        return "Query too long"
    if ";" in s:
        return "Only one statement is allowed"
    if not re.match(r"^(select|with)\b", s, re.I):
        return "Only SELECT queries are allowed"
    if BANNED.search(s):
        return "Query uses a forbidden keyword"
    allowed = set(views_for({"id": 0, "role": "user"}))
    # a CTE may not reuse a real table name (users...): it would shadow it and let a real read through
    ctes = {c.lower() for c in CTE_NAME.findall(s)} - (set(md.tables) - allowed)
    used = {t.lower() for t in TABLES_IN_SQL.findall(EXTRACT_FROM.sub("extract(", s))} - ctes
    if not used <= allowed:
        return f"Query may only read these views: {', '.join(sorted(allowed))} (not {', '.join(sorted(used - allowed))})"
    return None


def run_sql(user, sql: str) -> dict:
    """Run one scoped SELECT. Returns {sql, columns, rows} or {error}."""
    err = check(sql)
    if err:
        return {"error": err, "sql": sql}
    s = sql.strip().rstrip(";").strip()
    if not re.search(r"\blimit\b", s, re.I):
        s += f" LIMIT {MAX_ROWS}"
    views = views_for(user)
    conn = sandbox_engine.connect()
    try:
        if not IS_SQLITE:
            _ensure_role()
        for name, body in views.items():
            conn.exec_driver_sql(f"DROP VIEW IF EXISTS {TEMP}.{name}")
            conn.exec_driver_sql(f"CREATE TEMP VIEW {name} AS {body}")
        if IS_SQLITE:  # views are built; from here on only the user's query runs
            conn.connection.driver_connection.set_authorizer(_authorizer(views))
        else:
            for name in views:
                conn.exec_driver_sql(f"GRANT SELECT ON {name} TO {ROLE}")
            conn.exec_driver_sql(f"SET LOCAL ROLE {ROLE}")  # undone by the rollback in finally
        result = conn.execute(text(s))
        rows = [dict(r) for r in result.mappings().fetchmany(MAX_ROWS)]
        return {"sql": s, "columns": list(result.keys()), "row_count": len(rows), "rows": rows}
    except Exception as e:  # noqa: BLE001 - the message goes back to the model so it can retry
        return {"error": f"{type(e).__name__}: {str(e)[:300]}", "sql": s}
    finally:
        if IS_SQLITE:
            conn.connection.driver_connection.set_authorizer(None)
        for name in views:  # belt and braces: the connection is discarded anyway
            try:
                conn.exec_driver_sql(f"DROP VIEW IF EXISTS {TEMP}.{name}")
            except Exception:  # noqa: BLE001
                pass
        conn.rollback()  # nothing should have been written
        conn.close()
