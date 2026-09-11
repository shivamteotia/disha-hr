'use client';
import { api } from '@/lib';
import { useApp } from './Shell';

export const Tag = ({ s }) => <span className={`tag ${s}`}>{s}</span>;
export const Stat = ({ value, label }) => <div className="stat"><b>{value}</b><span>{label}</span></div>;

// cols: [header, key] or [header, key, row => node]
export function Table({ cols, rows }) {
  if (!rows?.length) return <p className="m">Nothing here yet.</p>;
  return (
    <div className="tbl"><table>
      <thead><tr>{cols.map((c, i) => <th key={i}>{c[0]}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={r.id ?? i}>{cols.map(([, k, f], j) => <td key={j}>{f ? f(r) : r[k]}</td>)}</tr>)}</tbody>
    </table></div>
  );
}

export function EmpOptions({ all }) {
  const { emps } = useApp();
  return <>{all && <option value="">All employees</option>}
    {emps.map((e) => <option key={e.id} value={e.id}>{e.name} ({e.emp_code || e.email})</option>)}</>;
}

export function EmpFilter() {
  const { isAdmin, uid, setUid } = useApp();
  if (!isAdmin) return null;
  return (
    <div className="card row noprint">
      <label style={{ flex: 1 }}>View employee
        <select value={uid} onChange={(e) => setUid(e.target.value)}><EmpOptions all /></select></label>
    </div>
  );
}

export function DecideButtons({ path, r, onDone }) {
  const { me, canDecide, act } = useApp();
  if (r.status !== 'pending') return null;
  const set = (status, msg) => act(() => api(`/${path}/${r.id}`, 'PUT', { status }), msg, onDone);
  return (
    <span className="row">
      {canDecide(r) && <>
        <button className="btn sm" onClick={() => set('approved', 'Approved')}>Approve</button>
        <button className="btn sm danger" onClick={() => set('rejected', 'Rejected')}>Reject</button></>}
      {r.user_id === me.id && <button className="btn sm sec" onClick={() => set('cancelled', 'Cancelled')}>Cancel</button>}
    </span>
  );
}
