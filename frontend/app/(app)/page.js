'use client';
import Link from 'next/link';
import { useApp } from '@/components/Shell';
import { Stat } from '@/components/ui';
import { api, onSubmit, thisMonth, today, useLoad } from '@/lib';

export default function Dashboard() {
  const { me, isAdmin, emps, act, canDecide } = useApp();
  const [d, load] = useLoad(() => Promise.all([api('/leaves/balance'), api(`/attendance?month=${thisMonth()}`),
    api('/leaves'), api('/expenses'), api('/announcements')]), []);
  if (!d) return null;
  const [bal, att, leaves, exps, news] = d;
  const t = att.find((a) => a.user_id === me.id && a.date === today());
  const btn = !t ? 'Check in' : !t.check_out ? 'Check out' : '';
  const toApprove = [...leaves, ...exps].filter((r) => r.status === 'pending' && canDecide(r)).length;

  return <>
    <div className="card">
      <h2>Hi {me.name} 👋</h2>
      <div className="row">
        <span className="m">Today: {t ? `in ${t.check_in}${t.check_out ? `, out ${t.check_out}` : ''}` : 'not checked in'}</span>
        {btn && <button className="btn" onClick={() => act(() => api('/attendance/check', 'POST'), `${btn} done`, load)}>{btn}</button>}
      </div>
    </div>

    <div className="card"><h3>Leave balance {new Date().getFullYear()}</h3>
      <div className="grid">{Object.entries(bal).map(([k, v]) => <Stat key={k} value={v.left} label={`${k} left of ${v.quota}`} />)}</div>
    </div>

    {toApprove > 0 && <div className="card row between">
      <b>{toApprove} request(s) waiting for your approval</b>
      <span className="row"><Link className="btn sm" href="/leaves">Leaves</Link><Link className="btn sm sec" href="/expenses">Expenses</Link></span>
    </div>}

    <div className="card"><h3>Announcements</h3>
      {news.length ? news.map((a) => <div key={a.id} className="news">
        <div className="row between"><b>{a.title}</b>
          <span className="m">{a.created.slice(0, 10)} {isAdmin && <button className="btn sm danger"
            onClick={() => confirm('Delete?') && act(() => api(`/announcements/${a.id}`, 'DELETE'), 'Deleted', load)}>×</button>}</span></div>
        {a.body && <div>{a.body}</div>}
      </div>) : <p className="m">No announcements.</p>}
      {isAdmin && <form className="f" style={{ marginTop: 12 }} onSubmit={onSubmit((b) => act(() => api('/announcements', 'POST', b), 'Posted', load))}>
        <label>Title<input name="title" required /></label><label>Message<input name="body" /></label><button className="btn">Post</button>
      </form>}
    </div>

    {isAdmin && <div className="card"><h3>Organisation today</h3><div className="grid">
      <Stat value={emps.filter((e) => e.active).length} label="Active employees" />
      <Stat value={new Set(att.filter((a) => a.date === today()).map((a) => a.user_id)).size} label="Checked in" />
      <Stat value={leaves.filter((l) => l.status === 'pending').length} label="Pending leaves" />
      <Stat value={exps.filter((x) => x.status === 'pending').length} label="Pending expenses" />
    </div></div>}
  </>;
}
