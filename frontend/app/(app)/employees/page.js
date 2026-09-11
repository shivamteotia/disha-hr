'use client';
import { useState } from 'react';
import { useApp } from '@/components/Shell';
import { EmpOptions, Table } from '@/components/ui';
import { api, onSubmit } from '@/lib';

export default function Employees() {
  const { isAdmin, emps, reloadEmps, act } = useApp();
  const [editId, setEditId] = useState(null);
  const reportsTo = ['Reports to', '', (x) => emps.find((m) => m.id === x.manager_id)?.name || '—'];
  const team = ['Direct reports', '', (x) => emps.filter((r) => r.manager_id === x.id).length || '—'];

  if (!isAdmin) return <div className="card"><h2>Directory</h2>
    <Table rows={emps} cols={[['Name', 'name'], ['Code', 'emp_code'], ['Dept', 'dept'], ['Designation', 'designation'],
      reportsTo, team, ['Email', 'email']]} /></div>;

  const e = emps.find((x) => x.id === editId) || {};
  const field = (k, label, type = 'text') => <label>{label}<input type={type} name={k} defaultValue={e[k] ?? ''} /></label>;
  const save = onSubmit(async (body) => {
    if (!body.password) delete body.password;
    const ok = await act(() => (e.id ? api(`/employees/${e.id}`, 'PUT', body) : api('/employees', 'POST', body)), 'Saved', reloadEmps);
    if (ok) setEditId(null);
    return ok;
  });

  return <>
    <div className="card"><h2>Employees ({emps.length})</h2>
      <Table rows={emps} cols={[['Code', 'emp_code'], ['Name', 'name'], ['Email', 'email'], ['Dept', 'dept'], reportsTo, team, ['Role', 'role'],
        ['Status', '', (x) => (x.active ? 'Active' : <span className="tag rejected">Inactive</span>)],
        ['', '', (x) => <button className="btn sm sec" onClick={() => { setEditId(x.id); setTimeout(() => scrollTo(0, document.body.scrollHeight)); }}>Edit</button>]]} />
    </div>
    <div className="card"><h3>{e.id ? `Edit ${e.name}` : 'Add employee'}</h3>
      <form key={e.id || 'new'} className="f" onSubmit={save}>
        {field('emp_code', 'Employee code')}{field('name', 'Name')}{field('email', 'Email', 'email')}{field('phone', 'Phone', 'tel')}
        {field('dept', 'Department')}{field('designation', 'Designation')}{field('doj', 'Date of joining', 'date')}
        <label>Manager<select name="manager_id" defaultValue={e.manager_id ?? ''}><option value="">—</option><EmpOptions /></select></label>
        <label>Role<select name="role" defaultValue={e.role || 'user'}><option value="user">User</option><option value="admin">Admin</option></select></label>
        <label>Status<select name="active" defaultValue={String(e.active ?? true)}><option value="true">Active</option><option value="false">Inactive</option></select></label>
        <label>{e.id ? 'Reset password (optional)' : 'Password'}<input type="password" name="password" minLength={8} required={!e.id} /></label>
        <span className="row"><button className="btn">{e.id ? 'Update' : 'Add'}</button>
          {e.id && <button type="button" className="btn sec" onClick={() => setEditId(null)}>New</button>}</span>
      </form></div>
  </>;
}
