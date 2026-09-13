"""DISHA HR API. Run from backend/:  uvicorn app.main:app --reload"""
import logfire  # configured first so every module's spans are captured
from .db import engine, hash_pw, init, iso, row, rows, run, utcnow, verify_pw, working_days  # loads backend/.env

logfire.configure(send_to_logfire="if-token-present", service_name="disha-hr", console=False)

import base64
import binascii
import datetime as dt
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from typing import Annotated, Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, Field
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

# ponytail: fixed yearly quotas for everyone, move to a table when policy differs per grade/location
QUOTA = {"CL": 12, "SL": 12, "EL": 15}
SECURE = bool(os.environ.get("HTTPS"))  # set behind TLS so the cookie is Secure
MAX_BODY = 10_000_000  # ~7 MB file after base64


@asynccontextmanager
async def lifespan(_):
    with engine.begin() as db:
        init(db)
    yield
    engine.dispose()


app = FastAPI(title="DISHA HR API", lifespan=lifespan)
api = APIRouter(prefix="/api")


@app.middleware("http")
async def guard(request: Request, call_next):
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        return JSONResponse({"detail": "Too large (max ~7 MB file)"}, 413)
    # JSON-only writes + SameSite=Strict cookie = no CSRF via plain HTML forms
    if request.method not in ("GET", "HEAD", "OPTIONS") and not request.headers.get("content-type", "").startswith("application/json"):
        return JSONResponse({"detail": "JSON only"}, 415)
    response = await call_next(request)
    response.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"})
    return response


@app.exception_handler(RequestValidationError)
async def bad_input(_, exc: RequestValidationError):
    return JSONResponse({"detail": "; ".join(f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors())}, 400)


@app.exception_handler(IntegrityError)
async def bad_data(_, exc: IntegrityError):
    return JSONResponse({"detail": str(exc.orig).splitlines()[0]}, 400)


def get_db():
    with engine.begin() as db:  # commits on success, rolls back if the request raised
        yield db


DB = Annotated[Connection, Depends(get_db)]


def current_user(db: DB, sid: Annotated[Optional[str], Cookie()] = None):
    user = sid and row(db, """SELECT u.*, s.token FROM sessions s JOIN users u ON u.id=s.user_id
        WHERE s.token=:sid AND s.expires>:now AND u.active""", sid=sid, now=utcnow())
    if not user:
        raise HTTPException(401, "Please log in")
    return user


User = Annotated[dict, Depends(current_user)]

# ---- helpers ----
Blank = BeforeValidator(lambda v: None if v == "" else v)  # empty form field -> null
OptStr = Annotated[Optional[str], Blank]
OptInt = Annotated[Optional[int], Blank]
OptDate = Annotated[Optional[dt.date], Blank]


def pub(u):
    return {k: v for k, v in u.items() if k not in ("pass", "token")}


def admin(u):
    if u["role"] != "admin":
        raise HTTPException(403, "Admin only")


def scope(u, user_id):
    """Admin sees everyone (or ?user_id=), a user only ever sees themself."""
    return user_id if u["role"] == "admin" else u["id"]


def own(u, r):
    if not r or (u["role"] != "admin" and r["user_id"] != u["id"]):
        raise HTTPException(404, "Not found")
    return r


def team_where(u, user_id):
    """For approvable requests (leaves, expenses): users also see their direct reports' rows."""
    if u["role"] == "admin":
        return "(CAST(:f AS INTEGER) IS NULL OR t.user_id=:f)", user_id
    return "(t.user_id=:f OR u.manager_id=:f)", u["id"]


def year_range(year):
    return f"{year}-01-01", f"{year + 1}-01-01"


def approvable(db, u, table, id):
    """Admin or the requester's manager approves (never their own request); the requester can only cancel."""
    r = row(db, f"SELECT t.*, u.manager_id FROM {table} t JOIN users u ON u.id=t.user_id WHERE t.id=:id", id=id)
    approver = bool(r) and r["user_id"] != u["id"] and (u["role"] == "admin" or r["manager_id"] == u["id"])
    if not r or (not approver and r["user_id"] != u["id"]):
        raise HTTPException(404, "Not found")
    return r, approver


class StatusIn(BaseModel):
    status: str


def decide(db, u, table, id, status):
    r, approver = approvable(db, u, table, id)
    if r["status"] != "pending":
        raise HTTPException(400, "Only pending requests can change")
    allowed = (["approved", "rejected"] if approver else []) + (["cancelled"] if r["user_id"] == u["id"] else [])
    if status not in allowed:
        raise HTTPException(400, "Invalid status")
    run(db, f"UPDATE {table} SET status=:s, decided_by=:u WHERE id=:id", s=status, u=u["id"], id=id)


def b64(data: str) -> bytes:
    try:
        return base64.b64decode(data, validate=True)
    except binascii.Error:
        raise HTTPException(400, "File must be base64")


def download(name, data):
    return Response(bytes(data), media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


# ---- auth ----
class LoginIn(BaseModel):
    email: str
    password: str


@api.post("/login")
def login(body: LoginIn, db: DB, response: Response):
    u = row(db, "SELECT * FROM users WHERE email=:e AND active", e=body.email.lower().strip())
    if not u or not verify_pw(body.password, u["pass"]):
        raise HTTPException(401, "Wrong email or password")
    token = secrets.token_hex(32)
    expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)).isoformat()
    run(db, "INSERT INTO sessions(token,user_id,expires) VALUES(:t,:u,:x)", t=token, u=u["id"], x=expires)
    response.set_cookie("sid", token, max_age=7 * 86400, httponly=True, samesite="strict", secure=SECURE)
    return pub(u)


@api.post("/logout")
def logout(user: User, db: DB, response: Response):
    run(db, "DELETE FROM sessions WHERE token=:t", t=user["token"])
    response.delete_cookie("sid", httponly=True, samesite="strict", secure=SECURE)


@api.get("/me")
def me(user: User):
    return pub(user)


class PasswordIn(BaseModel):
    old: str
    new: Annotated[str, Field(min_length=8)]


@api.post("/me/password")
def change_password(body: PasswordIn, user: User, db: DB):
    if not verify_pw(body.old, user["pass"]):
        raise HTTPException(400, "Current password is wrong")
    run(db, "UPDATE users SET pass=:p WHERE id=:id", p=hash_pw(body.new), id=user["id"])
    run(db, "DELETE FROM sessions WHERE user_id=:id AND token<>:t", id=user["id"], t=user["token"])


# ---- employees ----
EMP_FIELDS = {"emp_code", "name", "email", "role", "dept", "designation", "phone", "doj", "manager_id", "active"}


class EmployeeIn(BaseModel):
    emp_code: OptStr = None
    name: OptStr = None
    email: OptStr = None
    role: Annotated[Optional[Literal["user", "admin"]], Blank] = None
    dept: OptStr = None
    designation: OptStr = None
    phone: OptStr = None
    doj: OptDate = None
    manager_id: OptInt = None
    active: Optional[bool] = None
    password: OptStr = None


def update_emp(db, id, body: EmployeeIn, allowed):
    vals = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in allowed}
    if vals.get("email"):
        vals["email"] = vals["email"].lower().strip()
    if "doj" in vals:
        vals["doj"] = iso(vals["doj"])
    if vals:  # keys come from the EMP_FIELDS whitelist, so formatting them in is safe
        run(db, f"UPDATE users SET {', '.join(f'{k}=:{k}' for k in vals)} WHERE id=:id", **vals, id=id)


@api.get("/employees")
def employees(user: User, db: DB):
    if user["role"] == "admin":
        return rows(db, f"SELECT id, {', '.join(sorted(EMP_FIELDS))} FROM users ORDER BY name")
    return rows(db, "SELECT id, emp_code, name, email, dept, designation, manager_id FROM users WHERE active ORDER BY name")


@api.post("/employees")
def create_employee(body: EmployeeIn, user: User, db: DB):
    admin(user)
    if not body.name or not body.email or len(body.password or "") < 8:
        raise HTTPException(400, "Name, email and 8+ char password required")
    id = row(db, "INSERT INTO users(name,email,pass) VALUES(:n,:e,:p) RETURNING id",
             n=body.name, e=body.email.lower().strip(), p=hash_pw(body.password))["id"]
    update_emp(db, id, body, EMP_FIELDS - {"name", "email"})
    return {"id": id}


@api.put("/employees/{id}")
def update_employee(id: int, body: EmployeeIn, user: User, db: DB):
    if user["role"] != "admin" and id != user["id"]:
        raise HTTPException(403, "Forbidden")
    if body.manager_id == id:
        raise HTTPException(400, "Employee cannot be their own manager")
    update_emp(db, id, body, EMP_FIELDS if user["role"] == "admin" else {"phone"})
    if user["role"] == "admin" and body.password:
        if len(body.password) < 8:
            raise HTTPException(400, "Password must be at least 8 characters")
        run(db, "UPDATE users SET pass=:p WHERE id=:id", p=hash_pw(body.password), id=id)
        run(db, "DELETE FROM sessions WHERE user_id=:id", id=id)


# ---- attendance ----
@api.get("/attendance")
def attendance(user: User, db: DB, month: Optional[str] = None, user_id: Optional[int] = None):
    month = month or dt.date.today().strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(400, "Month must be YYYY-MM")
    y, m = map(int, month.split("-"))
    return rows(db, """SELECT a.*, u.name FROM attendance a JOIN users u ON u.id=a.user_id
        WHERE (CAST(:uid AS INTEGER) IS NULL OR a.user_id=:uid) AND a.date >= :s AND a.date < :e
        ORDER BY a.date DESC, u.name""", uid=scope(user, user_id), s=f"{month}-01", e=iso(dt.date(y + m // 12, m % 12 + 1, 1)))


@api.post("/attendance/check")
def check_in_out(user: User, db: DB):
    now = dt.datetime.now()  # server time zone (set TZ)
    date, time = now.date().isoformat(), now.strftime("%H:%M:%S")
    r = row(db, "SELECT * FROM attendance WHERE user_id=:u AND date=:d", u=user["id"], d=date)
    if not r:
        run(db, "INSERT INTO attendance(user_id,date,check_in) VALUES(:u,:d,:t)", u=user["id"], d=date, t=time)
    elif not r["check_out"]:
        run(db, "UPDATE attendance SET check_out=:t WHERE id=:id", t=time, id=r["id"])
    else:
        raise HTTPException(400, "Already checked out today")


class AttendanceIn(BaseModel):
    user_id: int
    date: dt.date
    check_in: Annotated[Optional[dt.time], Blank] = None
    check_out: Annotated[Optional[dt.time], Blank] = None


@api.put("/attendance")
def regularise(body: AttendanceIn, user: User, db: DB):
    admin(user)
    run(db, """INSERT INTO attendance(user_id,date,check_in,check_out) VALUES(:u,:d,:i,:o)
        ON CONFLICT(user_id,date) DO UPDATE SET check_in=excluded.check_in, check_out=excluded.check_out""",
        u=body.user_id, d=iso(body.date), i=iso(body.check_in), o=iso(body.check_out))


# ---- leaves ----
def balance(db, uid, year):
    s, e = year_range(year)
    used = {r["type"]: r["d"] for r in rows(db, """SELECT type, SUM(days) AS d FROM leaves WHERE user_id=:u
        AND status IN ('pending','approved') AND from_date >= :s AND from_date < :e GROUP BY type""", u=uid, s=s, e=e)}
    return {t: {"quota": q, "used": used.get(t, 0), "left": q - used.get(t, 0)} for t, q in QUOTA.items()}


@api.get("/leaves/balance")
def leave_balance(user: User, db: DB, user_id: Optional[int] = None):
    return balance(db, scope(user, user_id) or user["id"], dt.date.today().year)


@api.get("/leaves")
def leaves(user: User, db: DB, user_id: Optional[int] = None):
    where, f = team_where(user, user_id)
    return rows(db, f"""SELECT t.*, u.name, u.manager_id FROM leaves t JOIN users u ON u.id=t.user_id WHERE {where}
        ORDER BY (t.status='pending') DESC, t.from_date DESC""", f=f)


class LeaveIn(BaseModel):
    type: Literal["CL", "SL", "EL", "LWP"]
    from_date: dt.date
    to_date: dt.date
    reason: OptStr = None


@api.post("/leaves")
def apply_leave(body: LeaveIn, user: User, db: DB):
    if body.to_date < body.from_date:
        raise HTTPException(400, "Invalid dates")
    if body.from_date.year != body.to_date.year:
        raise HTTPException(400, "Split leaves that cross a year end")
    days = working_days(db, body.from_date, body.to_date)
    if not days:
        raise HTTPException(400, "No working days in that range")
    if body.type in QUOTA and days > balance(db, user["id"], body.from_date.year)[body.type]["left"]:
        raise HTTPException(400, f"Not enough {body.type} balance")
    f, t = iso(body.from_date), iso(body.to_date)
    if row(db, """SELECT 1 AS x FROM leaves WHERE user_id=:u AND status IN ('pending','approved')
        AND from_date<=:t AND to_date>=:f""", u=user["id"], f=f, t=t):
        raise HTTPException(400, "Overlaps an existing leave")
    run(db, "INSERT INTO leaves(user_id,type,from_date,to_date,days,reason) VALUES(:u,:ty,:f,:t,:d,:r)",
        u=user["id"], ty=body.type, f=f, t=t, d=days, r=body.reason)


@api.put("/leaves/{id}")
def decide_leave(id: int, body: StatusIn, user: User, db: DB):
    decide(db, user, "leaves", id, body.status)


# ---- holidays ----
@api.get("/holidays")
def holidays(user: User, db: DB, year: Optional[int] = None):
    s, e = year_range(year or dt.date.today().year)
    return rows(db, "SELECT * FROM holidays WHERE date >= :s AND date < :e ORDER BY date", s=s, e=e)


class HolidayIn(BaseModel):
    date: dt.date
    name: Annotated[str, Field(min_length=1)]


@api.post("/holidays")
def add_holiday(body: HolidayIn, user: User, db: DB):
    admin(user)
    run(db, "INSERT INTO holidays(date,name) VALUES(:d,:n) ON CONFLICT(date) DO UPDATE SET name=excluded.name",
        d=iso(body.date), n=body.name)


@api.delete("/holidays/{id}")
def delete_holiday(id: int, user: User, db: DB):
    admin(user)
    run(db, "DELETE FROM holidays WHERE id=:id", id=id)


# ---- announcements ----
@api.get("/announcements")
def announcements(user: User, db: DB):
    return rows(db, """SELECT a.*, u.name AS author FROM announcements a LEFT JOIN users u ON u.id=a.by
        ORDER BY a.id DESC LIMIT 20""")


class AnnouncementIn(BaseModel):
    title: Annotated[str, Field(min_length=1)]
    body: OptStr = None


@api.post("/announcements")
def post_announcement(body: AnnouncementIn, user: User, db: DB):
    admin(user)
    run(db, "INSERT INTO announcements(title,body,by) VALUES(:t,:b,:u)", t=body.title, b=body.body, u=user["id"])


@api.delete("/announcements/{id}")
def delete_announcement(id: int, user: User, db: DB):
    admin(user)
    run(db, "DELETE FROM announcements WHERE id=:id", id=id)


# ---- expenses ----
@api.get("/expenses")
def expenses(user: User, db: DB, user_id: Optional[int] = None):
    where, f = team_where(user, user_id)
    return rows(db, f"""SELECT t.id, t.user_id, t.date, t.category, t.amount, t.description, t.status,
        t.receipt_name IS NOT NULL AS has_receipt, u.name, u.manager_id
        FROM expenses t JOIN users u ON u.id=t.user_id WHERE {where}
        ORDER BY (t.status='pending') DESC, t.date DESC""", f=f)


class ExpenseIn(BaseModel):
    date: dt.date
    category: Literal["Travel", "Meals", "Internet", "Training", "Other"]
    amount: Annotated[float, Field(gt=0)]
    description: OptStr = None
    receipt_name: OptStr = None
    receipt: OptStr = None  # base64


@api.post("/expenses")
def claim_expense(body: ExpenseIn, user: User, db: DB):
    receipt = b64(body.receipt) if body.receipt else None
    run(db, """INSERT INTO expenses(user_id,date,category,amount,description,receipt_name,receipt)
        VALUES(:u,:d,:c,:a,:desc,:rn,:r)""", u=user["id"], d=iso(body.date), c=body.category, a=body.amount,
        desc=body.description, rn=(body.receipt_name or "receipt")[:200] if receipt else None, r=receipt)


@api.put("/expenses/{id}")
def decide_expense(id: int, body: StatusIn, user: User, db: DB):
    decide(db, user, "expenses", id, body.status)


@api.get("/expenses/{id}/receipt")
def expense_receipt(id: int, user: User, db: DB):
    r, _ = approvable(db, user, "expenses", id)
    if not r["receipt"]:
        raise HTTPException(404, "No receipt")
    return download(r["receipt_name"], r["receipt"])


# ---- payslips ----
@api.get("/payslips")
def payslips(user: User, db: DB, user_id: Optional[int] = None):
    return rows(db, """SELECT p.*, basic+hra+allowances AS gross, basic+hra+allowances-deductions AS net,
        u.name, u.emp_code, u.designation, u.dept FROM payslips p JOIN users u ON u.id=p.user_id
        WHERE (CAST(:uid AS INTEGER) IS NULL OR p.user_id=:uid) ORDER BY month DESC, u.name""", uid=scope(user, user_id))


Money = Annotated[float, Field(ge=0), BeforeValidator(lambda v: 0 if v == "" else v)]


class PayslipIn(BaseModel):
    user_id: int
    month: Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    basic: Money = 0
    hra: Money = 0
    allowances: Money = 0
    deductions: Money = 0


@api.post("/payslips")
def save_payslip(body: PayslipIn, user: User, db: DB):
    admin(user)
    run(db, """INSERT INTO payslips(user_id,month,basic,hra,allowances,deductions) VALUES(:user_id,:month,:basic,:hra,:allowances,:deductions)
        ON CONFLICT(user_id,month) DO UPDATE SET basic=excluded.basic, hra=excluded.hra,
        allowances=excluded.allowances, deductions=excluded.deductions""", **body.model_dump())


# ---- goals ----
@api.get("/goals")
def goals(user: User, db: DB, user_id: Optional[int] = None):
    return rows(db, """SELECT g.*, u.name FROM goals g JOIN users u ON u.id=g.user_id
        WHERE (CAST(:uid AS INTEGER) IS NULL OR g.user_id=:uid) ORDER BY g.status DESC, g.due""", uid=scope(user, user_id))


class GoalIn(BaseModel):
    title: Annotated[str, Field(min_length=1)]
    description: OptStr = None
    due: OptDate = None
    user_id: OptInt = None


@api.post("/goals")
def add_goal(body: GoalIn, user: User, db: DB):
    uid = body.user_id if user["role"] == "admin" and body.user_id else user["id"]
    run(db, "INSERT INTO goals(user_id,title,description,due) VALUES(:u,:t,:d,:due)",
        u=uid, t=body.title, d=body.description, due=iso(body.due))


class ProgressIn(BaseModel):
    progress: Annotated[int, Field(ge=0, le=100)]


@api.put("/goals/{id}")
def update_goal(id: int, body: ProgressIn, user: User, db: DB):
    own(user, row(db, "SELECT user_id FROM goals WHERE id=:id", id=id))
    run(db, "UPDATE goals SET progress=:p, status=:s WHERE id=:id",
        p=body.progress, s="done" if body.progress == 100 else "open", id=id)


@api.delete("/goals/{id}")
def delete_goal(id: int, user: User, db: DB):
    own(user, row(db, "SELECT user_id FROM goals WHERE id=:id", id=id))
    run(db, "DELETE FROM goals WHERE id=:id", id=id)


# ---- documents ----
@api.get("/documents")
def documents(user: User, db: DB, user_id: Optional[int] = None):
    return rows(db, """SELECT d.id, d.user_id, d.name, d.size, d.uploaded, u.name AS owner
        FROM documents d JOIN users u ON u.id=d.user_id
        WHERE (CAST(:uid AS INTEGER) IS NULL OR d.user_id=:uid) ORDER BY d.uploaded DESC""", uid=scope(user, user_id))


class DocumentIn(BaseModel):
    name: Annotated[str, Field(min_length=1)]
    data: Annotated[str, Field(min_length=1)]  # base64
    user_id: OptInt = None


@api.post("/documents")
def upload_document(body: DocumentIn, user: User, db: DB):
    uid = body.user_id if user["role"] == "admin" and body.user_id else user["id"]
    data = b64(body.data)
    run(db, "INSERT INTO documents(user_id,name,size,data) VALUES(:u,:n,:s,:d)", u=uid, n=body.name[:200], s=len(data), d=data)


@api.get("/documents/{id}")
def download_document(id: int, user: User, db: DB):
    d = own(user, row(db, "SELECT * FROM documents WHERE id=:id", id=id))
    return download(d["name"], d["data"])


@api.delete("/documents/{id}")
def delete_document(id: int, user: User, db: DB):
    own(user, row(db, "SELECT user_id FROM documents WHERE id=:id", id=id))
    run(db, "DELETE FROM documents WHERE id=:id", id=id)


# ---- Disha assistant ----
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]  # clients can't inject system or tool messages
    content: Annotated[str, Field(min_length=1, max_length=4000)]


class ChatIn(BaseModel):
    messages: Annotated[list[ChatMessage], Field(min_length=1, max_length=20)]


# Each question costs several model calls, so cap how many one person can ask.
# ponytail: in-memory, so the cap is per API process; move the counter to a table if you run more than one worker.
CHAT_LIMITS = ((8, 60, "minute"), (50, 3600, "hour"))
_chat_hits: dict[int, list[float]] = {}


def check_chat_limit(user_id: int):
    now = time.monotonic()
    hits = [t for t in _chat_hits.get(user_id, []) if now - t < CHAT_LIMITS[-1][1]]
    _chat_hits[user_id] = hits
    for count, window, unit in CHAT_LIMITS:
        recent = [t for t in hits if now - t < window]
        if len(recent) >= count:
            wait = max(1, int(window - (now - recent[0])))
            raise HTTPException(429, f"That's {count} questions in a {unit}. Please wait {wait}s before asking Disha again.",
                                headers={"Retry-After": str(wait)})
    hits.append(now)


@api.post("/chat")
def chat(body: ChatIn, sid: Annotated[Optional[str], Cookie()] = None):
    from .agent import chat as ask  # lazy: agent imports heavy deps and this module's db helpers
    with engine.begin() as db:  # auth only; don't hold a transaction while waiting on OpenAI
        user = current_user(db, sid)
    check_chat_limit(user["id"])  # before the key check, so the cap holds even when chat is unconfigured
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(503, "Disha isn't set up yet: the server has no OPENAI_API_KEY")
    return ask(dict(user), [m.model_dump() for m in body.messages])


app.include_router(api)
