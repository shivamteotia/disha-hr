'use client';
import { useApp } from '@/components/Shell';
import { Table } from '@/components/ui';
import { api, onSubmit } from '@/lib';

export default function Profile() {
  const { me, emps, reloadMe, act } = useApp();
  const fields = [['Code', me.emp_code], ['Email', me.email], ['Department', me.dept], ['Designation', me.designation], ['Joined', me.doj], ['Role', me.role]];
  const manager = emps.find((e) => e.id === me.manager_id);
  const reports = emps.filter((e) => e.manager_id === me.id);
  return <>
    <div className="card"><h2>{me.name}</h2>
      <div className="grid">{fields.map(([k, v]) => <div key={k}><span className="m">{k}</span><br />{v || '—'}</div>)}</div>
    </div>
    <div className="card"><h3>Reporting</h3>
      <p><span className="m">Reports to</span><br />
        {manager ? <>{manager.name} · {manager.designation || '—'} · <a href={`mailto:${manager.email}`}>{manager.email}</a></> : '—'}</p>
      <span className="m">Direct reports ({reports.length})</span>
      <Table rows={reports} cols={[['Name', 'name'], ['Code', 'emp_code'], ['Designation', 'designation'], ['Email', 'email']]} />
    </div>
    <div className="card"><h3>Contact</h3>
      <form className="f" onSubmit={onSubmit((b) => act(() => api(`/employees/${me.id}`, 'PUT', b), 'Saved', reloadMe).then(() => false))}>
        <label>Phone<input type="tel" name="phone" defaultValue={me.phone ?? ''} /></label><button className="btn">Save</button>
      </form></div>
    <div className="card"><h3>Change password</h3>
      <form className="f" onSubmit={onSubmit((b) => act(() => api('/me/password', 'POST', b), 'Password changed'))}>
        <label>Current<input type="password" name="old" required /></label>
        <label>New (8+ chars)<input type="password" name="new" minLength={8} required /></label>
        <button className="btn">Change</button>
      </form></div>
  </>;
}
