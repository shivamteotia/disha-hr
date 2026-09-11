"""Dummy data: 20 employees with Jan 2026 → yesterday records. Run once from backend/:  python -m app.seed
All dummy passwords: password123
"""
import datetime as dt
import random

from sqlalchemy import text

from .db import engine, hash_pw, init, iso, row, run, working_days

D, days = dt.date, dt.timedelta
rnd = random.Random(42)  # same data on every run
TODAY = D.today()
START = D(2026, 1, 1)
# ponytail: dummy window + holidays are fixed to 2026; edit START/HOLIDAYS to reseed another year
END = min(TODAY - days(1), D(2026, 12, 31))
HOLIDAYS = [(D(2026, 1, 26), "Republic Day"), (D(2026, 3, 4), "Holi"), (D(2026, 4, 3), "Good Friday"),
            (D(2026, 5, 1), "Labour Day"), (D(2026, 8, 15), "Independence Day"), (D(2026, 10, 2), "Gandhi Jayanti"),
            (D(2026, 10, 20), "Dussehra"), (D(2026, 11, 9), "Diwali"), (D(2026, 12, 25), "Christmas")]

# (name, dept, designation, date of joining, manager name or None (= admin), monthly basic)
PEOPLE = [
    ("Rahul Sharma", "Engineering", "Engineering Manager", D(2021, 4, 12), None, 95000),
    ("Priya Nair", "Sales", "Sales Manager", D(2022, 1, 10), None, 85000),
    ("Anjali Mehta", "HR", "HR Manager", D(2021, 8, 2), None, 80000),
    ("Vikram Rao", "Finance", "Finance Manager", D(2022, 6, 20), None, 90000),
    ("Arjun Verma", "Engineering", "Senior Software Engineer", D(2022, 9, 5), "Rahul Sharma", 65000),
    ("Sneha Iyer", "Engineering", "Software Engineer", D(2023, 7, 17), "Rahul Sharma", 45000),
    ("Karan Singh", "Engineering", "Software Engineer", D(2024, 2, 1), "Rahul Sharma", 42000),
    ("Neha Gupta", "Engineering", "QA Engineer", D(2023, 11, 13), "Rahul Sharma", 38000),
    ("Rohan Das", "Engineering", "DevOps Engineer", D(2026, 2, 16), "Rahul Sharma", 50000),
    ("Pooja Reddy", "Engineering", "UI Designer", D(2024, 5, 6), "Rahul Sharma", 40000),
    ("Amit Patel", "Sales", "Account Executive", D(2023, 3, 20), "Priya Nair", 36000),
    ("Kavya Menon", "Sales", "Account Executive", D(2024, 8, 12), "Priya Nair", 34000),
    ("Siddharth Joshi", "Sales", "Business Development Lead", D(2022, 11, 28), "Priya Nair", 55000),
    ("Ritu Agarwal", "Sales", "Sales Associate", D(2026, 4, 6), "Priya Nair", 28000),
    ("Deepak Kumar", "HR", "HR Executive", D(2023, 5, 15), "Anjali Mehta", 32000),
    ("Meera Pillai", "HR", "Talent Acquisition Specialist", D(2024, 10, 1), "Anjali Mehta", 36000),
    ("Nikhil Bansal", "Finance", "Accountant", D(2023, 1, 9), "Vikram Rao", 38000),
    ("Swati Kulkarni", "Finance", "Payroll Specialist", D(2025, 3, 3), "Vikram Rao", 40000),
    ("Manish Yadav", "Operations", "Operations Executive", D(2024, 1, 22), "Vikram Rao", 30000),
    ("Divya Shah", "Operations", "Office Administrator", D(2026, 6, 1), "Vikram Rao", 27000),
]
GOALS = {
    "Engineering": ["Ship Q3 release on time", "Reduce production bugs by 30%", "Complete cloud certification", "Improve test coverage to 80%"],
    "Sales": ["Close ₹50L new business", "Onboard 10 new clients", "Improve CRM hygiene", "Grow repeat orders by 15%"],
    "HR": ["Hire 12 engineers", "Launch employee engagement survey", "Digitise onboarding", "Reduce attrition below 10%"],
    "Finance": ["Close books by 5th of every month", "Automate expense reconciliation", "Complete statutory audit", "Cut vendor costs by 8%"],
    "Operations": ["Streamline office procurement", "Maintain 99% asset records", "Plan annual offsite", "Reduce facility costs by 5%"],
}
EXPENSES = {"Travel": (800, 6000, "Client visit cab/train"), "Meals": (300, 2500, "Team/client meal"),
            "Internet": (500, 1200, "Home broadband"), "Training": (2000, 15000, "Online course"), "Other": (200, 3000, "Office supplies")}


def many(db, sql, params):
    if params:
        db.execute(text(sql), params)


def main():
    with engine.begin() as db:  # one transaction, committed at the end
        init(db)
        if row(db, "SELECT 1 AS x FROM users WHERE email='rahul.sharma@company.com'"):
            print("Already seeded.")
            return
        admin_id = row(db, "SELECT id FROM users WHERE email='admin@company.com'")["id"]
        pw = hash_pw("password123")  # one hash for all dummy accounts, scrypt is slow on purpose
        n = dict(attendance=0, leaves=0, payslips=0, goals=0, expenses=0)
        many(db, "INSERT INTO holidays(date,name) VALUES(:d,:n) ON CONFLICT DO NOTHING", [dict(d=iso(d), n=nm) for d, nm in HOLIDAYS])
        holidays = {d for d, _ in HOLIDAYS}

        ids = {}
        for i, (name, dept, desig, doj, mgr, _) in enumerate(PEOPLE):
            ids[name] = row(db, """INSERT INTO users(emp_code,name,email,pass,dept,designation,phone,doj,manager_id)
                VALUES(:c,:n,:e,:p,:d,:g,:ph,:j,:m) RETURNING id""",
                            c=f"EMP{i + 2:03}", n=name, e=name.lower().replace(" ", ".") + "@company.com", p=pw, d=dept, g=desig,
                            ph=f"+91 98{rnd.randint(10000000, 99999999)}", j=iso(doj), m=ids[mgr] if mgr else admin_id)["id"]

        for name, dept, _, doj, mgr, basic in PEOPLE:
            uid, approver = ids[name], ids[mgr] if mgr else admin_id
            start = max(doj, START)
            span = (END - start).days

            # leaves: a few past ones (mostly approved), some upcoming pending ones
            taken, used = [], {"CL": 0, "SL": 0, "EL": 0}

            def add_leave(s, length, status):
                typ, e = rnd.choice(["CL", "CL", "SL", "EL"]), s + days(length - 1)
                wd = working_days(db, s, e)
                if not wd or s.year != e.year or used[typ] + wd > 10 or any(a <= e and b >= s for a, b in taken):
                    return
                used[typ] += wd
                taken.append((s, e))
                reason = rnd.choice(["Fever", "Doctor appointment", "Not feeling well"] if typ == "SL"
                                    else ["Family function", "Personal work", "Travel", "Vacation"])
                run(db, """INSERT INTO leaves(user_id,type,from_date,to_date,days,reason,status,decided_by,created)
                    VALUES(:u,:t,:f,:e,:d,:r,:s,:by,:c)""", u=uid, t=typ, f=iso(s), e=iso(e), d=wd, r=reason, s=status,
                    by=None if status == "pending" else approver, c=f"{s - days(rnd.randint(2, 10))} 10:00:00")
                n["leaves"] += 1

            if span > 20:
                for _ in range(rnd.randint(2, 5)):
                    add_leave(start + days(rnd.randint(5, span - 3)), rnd.randint(1, 3), "approved" if rnd.random() < 0.85 else "rejected")
            if rnd.random() < 0.4:
                add_leave(TODAY + days(rnd.randint(3, 30)), rnd.randint(1, 4), "pending")

            # attendance: every working day since joining, minus leave and ~3% unexplained absence
            att, d = [], start
            while d <= END:
                if d.weekday() < 5 and d not in holidays and not any(a <= d <= b for a, b in taken) and rnd.random() >= 0.03:
                    m_in = 9 * 60 + rnd.randint(-15, 70)
                    m_out = m_in + rnd.randint(480, 600)
                    att.append(dict(u=uid, d=iso(d), i=f"{m_in // 60:02}:{m_in % 60:02}:00", o=f"{m_out // 60:02}:{m_out % 60:02}:00"))
                d += days(1)
            many(db, "INSERT INTO attendance(user_id,date,check_in,check_out) VALUES(:u,:d,:i,:o)", att)
            n["attendance"] += len(att)

            # payslips: each completed month since joining
            slips, (y, m) = [], (start.year, start.month)
            while (y, m) < (TODAY.year, TODAY.month):
                slips.append(dict(u=uid, m=f"{y}-{m:02}", b=basic, h=round(basic * 0.4),
                                  a=round(basic * 0.15) + (rnd.randint(0, 3) * 5000 if m == 3 else 0), x=round(basic * 0.12) + 200))
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
            many(db, "INSERT INTO payslips(user_id,month,basic,hra,allowances,deductions) VALUES(:u,:m,:b,:h,:a,:x)", slips)
            n["payslips"] += len(slips)

            for title in rnd.sample(GOALS[dept], rnd.randint(2, 3)):
                progress = rnd.choice([0, 10, 25, 40, 50, 60, 75, 90, 100])
                run(db, "INSERT INTO goals(user_id,title,description,due,progress,status) VALUES(:u,:t,:d,:due,:p,:s)",
                    u=uid, t=title, d=f"{dept} objective for 2026", due=rnd.choice(["2026-06-30", "2026-09-30", "2026-12-31"]),
                    p=progress, s="done" if progress == 100 else "open")
                n["goals"] += 1

            for _ in range(rnd.randint(0, 4)):
                cat = rnd.choice(list(EXPENSES))
                lo, hi, desc = EXPENSES[cat]
                date = start + days(rnd.randint(0, span))
                status = ("pending" if date > END - days(20) and rnd.random() < 0.6
                          else "approved" if rnd.random() < 0.85 else "rejected")
                run(db, "INSERT INTO expenses(user_id,date,category,amount,description,status,decided_by) VALUES(:u,:d,:c,:a,:desc,:s,:by)",
                    u=uid, d=iso(date), c=cat, a=rnd.randint(lo, hi), desc=desc, s=status, by=None if status == "pending" else approver)
                n["expenses"] += 1

            for doc in ["Offer Letter", "ID Proof"]:
                data = f"{doc} — {name}\nDummy document generated by app.seed\n".encode()
                run(db, "INSERT INTO documents(user_id,name,size,data,uploaded) VALUES(:u,:n,:s,:d,:t)",
                    u=uid, n=f"{doc}.txt", s=len(data), d=data, t=f"{start} 11:00:00")

        many(db, "INSERT INTO announcements(title,body,by) VALUES(:t,:b,:u)", [
            dict(t="Welcome to DISHA", b="Check in daily, apply for leave and download payslips here. Contact HR for help.", u=admin_id),
            dict(t="Diwali holiday", b="Office will remain closed on 9 November for Diwali.", u=admin_id),
            dict(t="Q3 townhall", b="All-hands townhall on the last Friday of September at 4 PM in the main conference room.", u=admin_id),
        ])

    print(f"Seeded {len(PEOPLE)} employees ({START} → {END}): " + ", ".join(f"{v} {k}" for k, v in n.items())
          + f", {len(HOLIDAYS)} holidays.")
    print("Login as firstname.lastname@company.com / password123 — e.g. rahul.sharma@company.com (manager of 6).")


if __name__ == "__main__":
    main()
