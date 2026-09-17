"""Database: SQLite file by default (backend/disha.db); PostgreSQL by setting
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/disha — the SQL below is written to run on both.

`python -m app.db --reset` recreates an empty *_test database (used by test.mjs).
"""
import datetime as dt
import hashlib
import hmac
import os
import secrets
import sys
from pathlib import Path

from sqlalchemy import (Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, LargeBinary, MetaData,
                        Numeric, Table, Text, Time, UniqueConstraint, create_engine, event, func, text)
from sqlalchemy.engine import make_url

try:  # backend/.env holds the API keys and optional DATABASE_URL
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{Path(__file__).resolve().parents[1] / 'disha.db'}")
if DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
    # hosting providers (e.g. Render) hand out a plain postgres:// URL, which SQLAlchemy
    # defaults to the psycopg2 dialect — we only install psycopg (v3), so force that driver.
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]
IS_SQLITE = DATABASE_URL.startswith("sqlite")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if IS_SQLITE else {})
if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")


# ---- schema ----
md = MetaData()


def _id():
    return Column("id", Integer, primary_key=True)


def _owner():
    return Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


def _status():
    return (Column("status", Text, nullable=False, server_default="pending"),
            CheckConstraint("status IN ('pending','approved','rejected','cancelled')"),
            Column("decided_by", Integer, ForeignKey("users.id")),
            Column("created", DateTime(timezone=True), nullable=False, server_default=func.now()))


Table("users", md, _id(), Column("emp_code", Text, unique=True), Column("name", Text, nullable=False),
      Column("email", Text, unique=True, nullable=False), Column("pass", Text, nullable=False),
      Column("role", Text, nullable=False, server_default="user"), CheckConstraint("role IN ('user','admin')"),
      Column("dept", Text), Column("designation", Text), Column("phone", Text), Column("doj", Date),
      Column("manager_id", Integer, ForeignKey("users.id")), Column("active", Boolean, nullable=False, server_default=text("true")))
Table("sessions", md, Column("token", Text, primary_key=True), _owner(), Column("expires", DateTime(timezone=True), nullable=False))
Table("attendance", md, _id(), _owner(), Column("date", Date, nullable=False), Column("check_in", Time), Column("check_out", Time),
      UniqueConstraint("user_id", "date"))
Table("leaves", md, _id(), _owner(), Column("type", Text, nullable=False), Column("from_date", Date, nullable=False),
      Column("to_date", Date, nullable=False), Column("days", Integer, nullable=False), Column("reason", Text), *_status())
Table("payslips", md, _id(), _owner(), Column("month", Text, nullable=False),
      *(Column(k, Numeric(12, 2), nullable=False, server_default="0") for k in ("basic", "hra", "allowances", "deductions")),
      UniqueConstraint("user_id", "month"))
Table("goals", md, _id(), _owner(), Column("title", Text, nullable=False), Column("description", Text), Column("due", Date),
      Column("progress", Integer, nullable=False, server_default="0"), CheckConstraint("progress BETWEEN 0 AND 100"),
      Column("status", Text, nullable=False, server_default="open"))
Table("documents", md, _id(), _owner(), Column("name", Text, nullable=False), Column("size", Integer),
      Column("data", LargeBinary, nullable=False), Column("uploaded", DateTime(timezone=True), nullable=False, server_default=func.now()))
Table("holidays", md, _id(), Column("date", Date, unique=True, nullable=False), Column("name", Text, nullable=False))
Table("announcements", md, _id(), Column("title", Text, nullable=False), Column("body", Text),
      Column("by", Integer, ForeignKey("users.id", ondelete="SET NULL")),
      Column("created", DateTime(timezone=True), nullable=False, server_default=func.now()))
Table("expenses", md, _id(), _owner(), Column("date", Date, nullable=False), Column("category", Text, nullable=False),
      Column("amount", Numeric(12, 2), nullable=False), CheckConstraint("amount > 0"), Column("description", Text),
      Column("receipt_name", Text), Column("receipt", LargeBinary), *_status())


# ---- query helpers (named :params; dates/times are bound as ISO strings so both databases agree) ----
def rows(db, sql, **p):
    return [dict(r) for r in db.execute(text(sql), p).mappings()]


def row(db, sql, **p):
    r = db.execute(text(sql), p).mappings().first()
    return dict(r) if r else None


def run(db, sql, **p):
    return db.execute(text(sql), p)


def iso(v):
    return v.isoformat() if v is not None else None


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


# Same format as the old Node app (salt:scrypt-hex), so existing hashes keep working.
def hash_pw(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    return f"{salt}:{hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64).hex()}"


def verify_pw(password: str, stored: str) -> bool:
    return hmac.compare_digest(hash_pw(password, stored.split(":")[0]), stored)


def working_days(db, start: dt.date, end: dt.date) -> int:
    """Mon–Fri days in [start, end] that are not holidays."""
    hol = {str(r["date"]) for r in rows(db, "SELECT date FROM holidays WHERE date BETWEEN :s AND :e", s=iso(start), e=iso(end))}
    return sum(1 for i in range((end - start).days + 1)
               if (d := start + dt.timedelta(i)).weekday() < 5 and d.isoformat() not in hol)


def init(db):
    md.create_all(db)
    if not row(db, "SELECT 1 AS x FROM users LIMIT 1"):
        pw = os.environ.get("ADMIN_PASSWORD") or secrets.token_hex(6)
        run(db, "INSERT INTO users(emp_code,name,email,pass,role) VALUES('EMP001','Administrator','admin@company.com',:p,'admin')",
            p=hash_pw(pw))
        print(f"Created admin: admin@company.com / {pw}  (change it after first login)", flush=True)


if __name__ == "__main__" and sys.argv[1:] == ["--reset"]:
    url = make_url(DATABASE_URL)
    name = url.database or ""
    if not Path(name).stem.endswith("_test"):
        sys.exit(f"Refusing to reset {name!r}: only databases ending in _test")
    if IS_SQLITE:
        Path(name).unlink(missing_ok=True)
    else:
        with create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT").connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{name}"'))
