// Self-check: node test.mjs — verifies access control, approvals and leave rules against the FastAPI backend,
// using a throwaway database recreated each run: backend/disha_test.db (SQLite), or set
// TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/disha_test to test on PostgreSQL.
import { spawn, spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';

const PORT = 3999, base = `http://localhost:${PORT}/api`;
const env = { ...process.env, ADMIN_PASSWORD: 'adminpass1',
  DATABASE_URL: process.env.TEST_DATABASE_URL || 'sqlite:///disha_test.db' };
const cwd = new URL('./backend/', import.meta.url);
if (spawnSync('python', ['-m', 'app.db', '--reset'], { cwd, env, stdio: 'inherit' }).status) process.exit(1);
const srv = spawn('python', ['-m', 'uvicorn', 'app.main:app', '--port', String(PORT), '--log-level', 'warning'], { cwd, env, stdio: ['ignore', 'ignore', 'inherit'] });
for (let i = 0; ; i++) {
  try { await fetch(base + '/me'); break; } catch {
    if (i > 100) { srv.kill(); throw new Error('API did not start'); }
    await new Promise((r) => setTimeout(r, 200));
  }
}

const client = () => {
  let cookie = '';
  return async (path, method = 'GET', body) => {
    const r = await fetch(base + path, { method, headers: { cookie, 'content-type': 'application/json' }, body: body && JSON.stringify(body) });
    cookie = r.headers.get('set-cookie')?.split(';')[0] || cookie;
    return { status: r.status, body: await r.json().catch(() => null) };
  };
};
try {
  const admin = client(), alice = client();
  assert.equal((await admin('/login', 'POST', { email: 'admin@company.com', password: 'adminpass1' })).status, 200);
  const a = (await admin('/employees', 'POST', { name: 'Alice', email: 'alice@x.com', password: 'alicepass' })).body.id;
  const b = (await admin('/employees', 'POST', { name: 'Bob', email: 'bob@x.com', password: 'bobpass12' })).body.id;
  await admin('/payslips', 'POST', { user_id: b, month: '2026-08', basic: 50000 });
  await admin('/documents', 'POST', { user_id: b, name: 'bob.pdf', data: 'aGVsbG8=' });

  assert.equal((await alice('/payslips')).status, 401);
  await alice('/login', 'POST', { email: 'alice@x.com', password: 'alicepass' });
  assert.equal((await alice('/payslips?user_id=' + b)).body.length, 0, 'user_id param ignored for users');
  assert.equal((await alice('/documents/1')).status, 404, 'cannot read others docs');
  assert.equal((await alice(`/employees/${b}`, 'PUT', { role: 'admin' })).status, 403);
  assert.equal((await alice(`/employees/${a}`, 'PUT', { role: 'admin', phone: '123' })).status, 200);
  assert.equal((await alice('/me')).body.role, 'user', 'self-edit cannot escalate role');
  assert.equal((await alice('/payslips', 'POST', { user_id: a, month: '2026-08' })).status, 403);

  assert.equal((await alice('/leaves', 'POST', { type: 'CL', from_date: '2026-01-01', to_date: '2026-01-20' })).status, 400, 'over quota');
  assert.equal((await alice('/leaves', 'POST', { type: 'CL', from_date: '2026-01-01', to_date: '2026-01-03' })).status, 200);
  assert.equal((await alice('/leaves', 'POST', { type: 'SL', from_date: '2026-01-02', to_date: '2026-01-02' })).status, 400, 'overlap');
  assert.equal((await alice('/leaves/1', 'PUT', { status: 'approved' })).status, 400, 'user cannot self-approve');
  assert.equal((await admin('/leaves/1', 'PUT', { status: 'approved' })).status, 200);
  assert.equal((await alice('/leaves/balance')).body.CL.left, 10, 'Thu–Sat = 2 working days');

  // manager approval: Mo manages Alice; Bob is a peer and must not see or decide her requests
  const mo = client(), bob = client();
  const moId = (await admin('/employees', 'POST', { name: 'Mo', email: 'mo@x.com', password: 'mopass123' })).body.id;
  await admin(`/employees/${a}`, 'PUT', { manager_id: moId });
  assert.equal((await admin(`/employees/${a}`, 'PUT', { manager_id: a })).status, 400, 'no self-manager');
  await mo('/login', 'POST', { email: 'mo@x.com', password: 'mopass123' });
  await bob('/login', 'POST', { email: 'bob@x.com', password: 'bobpass12' });
  await alice('/leaves', 'POST', { type: 'SL', from_date: '2026-02-02', to_date: '2026-02-02' });
  const sl = (await alice('/leaves')).body.find((l) => l.type === 'SL');
  assert.equal((await mo('/leaves')).body.length, 2, 'manager sees team leaves');
  assert.equal((await bob('/leaves')).body.length, 0, 'peer sees nothing');
  assert.equal((await bob(`/leaves/${sl.id}`, 'PUT', { status: 'approved' })).status, 404);
  assert.equal((await mo(`/leaves/${sl.id}`, 'PUT', { status: 'cancelled' })).status, 400, 'manager cannot cancel');
  assert.equal((await mo(`/leaves/${sl.id}`, 'PUT', { status: 'approved' })).status, 200);
  await mo('/leaves', 'POST', { type: 'CL', from_date: '2026-03-02', to_date: '2026-03-02' });
  const moLeave = (await mo('/leaves')).body.find((l) => l.user_id === moId);
  assert.equal((await admin(`/leaves/${moLeave.id}`, 'PUT', { status: 'approved' })).status, 200, 'admin approves anyone');

  // working days: Fri 2026-05-01 holiday → Fri..Mon = only Mon counts
  await admin('/holidays', 'POST', { date: '2026-05-01', name: 'Labour Day' });
  await alice('/leaves', 'POST', { type: 'EL', from_date: '2026-05-01', to_date: '2026-05-04' });
  assert.equal((await alice('/leaves')).body.find((l) => l.type === 'EL').days, 1);
  assert.equal((await alice('/leaves', 'POST', { type: 'EL', from_date: '2026-05-02', to_date: '2026-05-03' })).status, 400, 'weekend only');
  assert.equal((await alice('/holidays', 'POST', { date: '2026-06-01', name: 'x' })).status, 403);

  // expenses: manager approves, receipt visible to manager but not peer
  assert.equal((await alice('/expenses', 'POST', { date: '2026-04-01', category: 'Travel', amount: -5 })).status, 400);
  await alice('/expenses', 'POST', { date: '2026-04-01', category: 'Travel', amount: 1200, receipt_name: 'r.txt', receipt: 'aGk=' });
  const ex = (await mo('/expenses')).body[0];
  assert.equal((await bob(`/expenses/${ex.id}/receipt`)).status, 404);
  assert.equal((await mo(`/expenses/${ex.id}/receipt`)).status, 200);
  assert.equal((await alice(`/expenses/${ex.id}`, 'PUT', { status: 'approved' })).status, 400, 'no self-approval');
  assert.equal((await mo(`/expenses/${ex.id}`, 'PUT', { status: 'approved' })).status, 200);

  // announcements: admin only
  assert.equal((await alice('/announcements', 'POST', { title: 'hi' })).status, 403);
  await admin('/announcements', 'POST', { title: 'Hello' });
  assert.equal((await alice('/announcements')).body[0].title, 'Hello');

  assert.equal((await alice('/attendance/check', 'POST')).status, 200);
  assert.equal((await alice('/attendance/check', 'POST')).status, 200);
  assert.equal((await alice('/attendance/check', 'POST')).status, 400, 'no third punch');
  console.log('all checks passed');
} finally { srv.kill(); }
