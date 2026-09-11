'use client';
import { useApp } from '@/components/Shell';
import { DecideButtons, EmpFilter, Stat, Table, Tag } from '@/components/ui';
import { api, onSubmit, useLoad } from '@/lib';

export default function Leaves() {
  const { isAdmin, q, act, others } = useApp();
  const [d, load] = useLoad(() => Promise.all([api(`/leaves/balance?${q}`), api(`/leaves?${q}`), api('/holidays')]), [q]);
  if (!d) return null;
  const [bal, rows, hols] = d;
  return <>
    <EmpFilter />
    <div className="card"><h2>Leaves</h2>
      <div className="grid">{Object.entries(bal).map(([k, v]) => <Stat key={k} value={v.left} label={`${k} left (used ${v.used}/${v.quota})`} />)}</div>
    </div>

    <div className="card"><h3>Apply for leave</h3>
      <form className="f" onSubmit={onSubmit((b) => act(() => api('/leaves', 'POST', b), 'Leave applied', load))}>
        <label>Type<select name="type"><option value="CL">Casual (CL)</option><option value="SL">Sick (SL)</option>
          <option value="EL">Earned (EL)</option><option value="LWP">Leave without pay</option></select></label>
        <label>From<input type="date" name="from_date" required /></label>
        <label>To<input type="date" name="to_date" required /></label>
        <label>Reason<input name="reason" /></label>
        <button className="btn">Apply</button>
      </form></div>

    <div className="card"><h3>Requests</h3>
      <p className="m">Days count working days only (weekends and holidays excluded).</p>
      <Table rows={rows} cols={[...(others(rows) ? [['Employee', 'name']] : []), ['Type', 'type'], ['From', 'from_date'],
        ['To', 'to_date'], ['Days', 'days'], ['Reason', 'reason'], ['Status', '', (l) => <Tag s={l.status} />],
        ['', '', (l) => <DecideButtons path="leaves" r={l} onDone={load} />]]} />
    </div>

    <div className="card"><h3>Holidays {new Date().getFullYear()}</h3>
      <Table rows={hols} cols={[['Date', 'date'],
        ['Day', '', (h) => new Date(h.date).toLocaleDateString('en-IN', { weekday: 'short' })], ['Holiday', 'name'],
        ...(isAdmin ? [['', '', (h) => <button className="btn sm danger"
          onClick={() => confirm('Delete holiday?') && act(() => api(`/holidays/${h.id}`, 'DELETE'), 'Deleted', load)}>Delete</button>]] : [])]} />
      {isAdmin && <form className="f" style={{ marginTop: 12 }} onSubmit={onSubmit((b) => act(() => api('/holidays', 'POST', b), 'Holiday saved', load))}>
        <label>Date<input type="date" name="date" required /></label><label>Name<input name="name" required /></label>
        <button className="btn">Add holiday</button>
      </form>}
    </div>
  </>;
}
