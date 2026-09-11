'use client';
import { useApp } from '@/components/Shell';
import { DecideButtons, EmpFilter, Table, Tag } from '@/components/ui';
import { api, money, onSubmit, readB64, today, useLoad } from '@/lib';

export default function Expenses() {
  const { q, act, toast, others } = useApp();
  const [rows, load] = useLoad(() => api(`/expenses?${q}`), [q]);
  if (!rows) return null;

  const claim = onSubmit(async (body, form) => {
    const file = form.receipt.files[0];
    delete body.receipt;
    if (file) {
      if (file.size > 7e6) { toast('Receipt too large (max 7 MB)'); return false; }
      Object.assign(body, { receipt_name: file.name, receipt: await readB64(file) });
    }
    return act(() => api('/expenses', 'POST', body), 'Claim submitted', load);
  });

  return <>
    <EmpFilter />
    <div className="card"><h2>Expense claims</h2>
      <Table rows={rows} cols={[...(others(rows) ? [['Employee', 'name']] : []), ['Date', 'date'], ['Category', 'category'],
        ['Amount', '', (x) => money(x.amount)], ['Description', 'description'],
        ['Receipt', '', (x) => x.has_receipt && <a href={`/api/expenses/${x.id}/receipt`}>Download</a>],
        ['Status', '', (x) => <Tag s={x.status} />], ['', '', (x) => <DecideButtons path="expenses" r={x} onDone={load} />]]} />
    </div>
    <div className="card"><h3>New claim</h3>
      <form className="f" onSubmit={claim}>
        <label>Date<input type="date" name="date" required max={today()} /></label>
        <label>Category<select name="category">{['Travel', 'Meals', 'Internet', 'Training', 'Other'].map((c) => <option key={c}>{c}</option>)}</select></label>
        <label>Amount (₹)<input type="number" name="amount" min="1" step="0.01" required /></label>
        <label>Description<input name="description" /></label>
        <label>Receipt (optional, max 7 MB)<input type="file" name="receipt" /></label>
        <button className="btn">Submit</button>
      </form></div>
  </>;
}
