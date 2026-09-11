"""Self-check for the Disha chatbot, no OpenAI calls: python test_disha.py (from backend/)

Checks that chat tools obey the same permissions as the API, and that the tool-calling loop works (fake client).
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS

DB = Path(__file__).with_name("disha_chat_test.db")
DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["ADMIN_PASSWORD"] = "adminpass1"

from app.db import engine, hash_pw, init, row, run  # noqa: E402  (env must be set first)
from app import disha  # noqa: E402

with engine.begin() as db:
    init(db)
    mk = lambda name, mgr=None: row(db, "INSERT INTO users(name,email,pass,manager_id,phone) VALUES(:n,:e,:p,:m,'999') RETURNING *",
                                    n=name, e=f"{name}@x.com", p=hash_pw("password1"), m=mgr)
    m = mk("mo")
    a, b = mk("alice", m["id"]), mk("bob")
    run(db, "INSERT INTO payslips(user_id,month,basic) VALUES(:u,'2026-08',50000)", u=b["id"])
    run(db, "INSERT INTO leaves(user_id,type,from_date,to_date,days) VALUES(:u,'CL','2026-02-02','2026-02-02',1)", u=a["id"])

tool = lambda user, name, **args: json.loads(disha.run_tool(user, name, args))

assert tool(a, "list_payslips", user_id=b["id"]) == [], "employee cannot read another's payslip"
assert tool(a, "get_leave_balance", user_id=b["id"])["CL"]["used"] == 1, "user_id ignored for employees"
assert len(tool(m, "list_leaves")) == 1, "manager sees team leave"
assert tool(b, "list_leaves") == [], "peer sees nothing"
assert "phone" not in tool(a, "search_employees", query="bob")[0], "directory fields only"
assert tool(a, "my_profile")["manager"]["name"] == "mo"
assert "pass" not in tool(a, "my_profile"), "password hash never reaches the model"
assert "error" in tool(a, "drop_tables"), "unknown tool is an error, not a crash"
assert "error" in tool(a, "get_attendance", month="bad"), "API errors come back as tool errors"

# tool-calling loop with a fake OpenAI client: one tool call, then a final answer
seen = []


def create(**kw):
    seen.append([dict(x) for x in kw["messages"]])
    if len(seen) == 1:
        call = NS(id="c1", function=NS(name="get_leave_balance", arguments="{}"))
        return NS(choices=[NS(message=NS(content=None, tool_calls=[call]))])
    return NS(choices=[NS(message=NS(content="You have 11 CL left.", tool_calls=None))])


fake = NS(chat=NS(completions=NS(create=create)))
reply = disha.chat(a, [{"role": "user", "content": "leave balance?"}], client=fake)
assert reply == "You have 11 CL left.", reply
tool_msg = seen[1][-1]
assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["CL"]["left"] == 11
assert "alice" in seen[0][0]["content"], "system prompt knows who is asking"

engine.dispose()
DB.unlink(missing_ok=True)
print("disha checks passed")
