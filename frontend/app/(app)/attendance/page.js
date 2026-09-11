'use client';
import { useState } from 'react';
import { useApp } from '@/components/Shell';
import { EmpFilter, EmpOptions, Table } from '@/components/ui';
import { api, onSubmit, thisMonth, useLoad } from '@/lib';

const hours = (r) => r.check_in && r.check_out
  ? ((Date.parse(`2000-01-01T${r.check_out}`) - Date.parse(`2000-01-01T${r.check_in}`)) / 36e5).toFixed(1) : '';

export default function Attendance() {
  const { isAdmin, uid, q, act } = useApp();
  const [month, setMonth] = useState(thisMonth());
  const [rows, load] = useLoad(() => api(`/attendance?month=${month}&${q}`), [month, q]);
  if (!rows) return null;
  return <>
    <EmpFilter />
    <div className="card">
      <div className="row between"><h2>Attendance</h2>
        <input type="month" value={month} style={{ width: 'auto' }} onChange={(e) => setMonth(e.target.value)} /></div>
      <p className="m">{rows.length} day(s) recorded</p>
      <Table rows={rows} cols={[['Date', 'date'], ...(isAdmin ? [['Employee', 'name']] : []),
        ['In', 'check_in'], ['Out', 'check_out'], ['Hours', '', hours]]} />
    </div>
    {isAdmin && <div className="card"><h3>Regularise / mark attendance</h3>
      <form className="f" onSubmit={onSubmit((b) => act(() => api('/attendance', 'PUT', b), 'Saved', load))}>
        <label>Employee<select name="user_id" required defaultValue={uid}><EmpOptions /></select></label>
        <label>Date<input type="date" name="date" required /></label>
        <label>In<input type="time" name="check_in" step="1" /></label>
        <label>Out<input type="time" name="check_out" step="1" /></label>
        <button className="btn">Save</button>
      </form></div>}
  </>;
}
