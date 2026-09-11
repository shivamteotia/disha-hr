'use client';
import { useState } from 'react';
import { useApp } from '@/components/Shell';
import { EmpFilter, EmpOptions, Table } from '@/components/ui';
import { api, money, onSubmit, thisMonth, useLoad } from '@/lib';

export default function Payslips() {
  const { isAdmin, uid, q, act } = useApp();
  const [rows, load] = useLoad(() => api(`/payslips?${q}`), [q]);
  const [slipId, setSlipId] = useState(null);
  if (!rows) return null;
  const slip = rows.find((p) => p.id === slipId);

  return <>
    <EmpFilter />
    {slip && <div className="card slip">
      <div className="row between noprint"><h2>Payslip</h2>
        <span className="row"><button className="btn sm" onClick={() => print()}>Print / Save PDF</button>
          <button className="btn sm sec" onClick={() => setSlipId(null)}>Close</button></span></div>
      <h3>Payslip for {slip.month}</h3>
      <p>{slip.name} · {slip.emp_code} · {slip.designation} · {slip.dept}</p>
      <table><tbody>
        <tr><td>Basic</td><td>{money(slip.basic)}</td></tr>
        <tr><td>HRA</td><td>{money(slip.hra)}</td></tr>
        <tr><td>Allowances</td><td>{money(slip.allowances)}</td></tr>
        <tr><th>Gross</th><th>{money(slip.gross)}</th></tr>
        <tr><td>Deductions</td><td>− {money(slip.deductions)}</td></tr>
        <tr><th>Net pay</th><th>{money(slip.net)}</th></tr>
      </tbody></table>
    </div>}

    <div className="card noprint"><h2>Payslips</h2>
      <Table rows={rows} cols={[['Month', 'month'], ...(isAdmin ? [['Employee', 'name']] : []),
        ['Gross', '', (p) => money(p.gross)], ['Net', '', (p) => money(p.net)],
        ['', '', (p) => <button className="btn sm sec" onClick={() => { setSlipId(p.id); scrollTo(0, 0); }}>View</button>]]} />
    </div>

    {isAdmin && <div className="card noprint"><h3>Add / update payslip</h3>
      <form className="f" onSubmit={onSubmit((b) => act(() => api('/payslips', 'POST', b), 'Payslip saved', load))}>
        <label>Employee<select name="user_id" required defaultValue={uid}><EmpOptions /></select></label>
        <label>Month<input type="month" name="month" required defaultValue={thisMonth()} /></label>
        {['basic', 'hra', 'allowances', 'deductions'].map((k) =>
          <label key={k}>{k}<input type="number" min="0" step="0.01" name={k} defaultValue="0" /></label>)}
        <button className="btn">Save</button>
      </form></div>}
  </>;
}
