'use client';
import { useApp } from '@/components/Shell';
import { EmpFilter, EmpOptions, Table } from '@/components/ui';
import { api, onSubmit, readB64, useLoad } from '@/lib';

export default function Documents() {
  const { me, isAdmin, uid, q, act, toast } = useApp();
  const [rows, load] = useLoad(() => api(`/documents?${q}`), [q]);
  if (!rows) return null;

  const upload = onSubmit(async (body, form) => {
    const file = form.file.files[0];
    if (file.size > 7e6) { toast('File too large (max 7 MB)'); return false; }
    const data = await readB64(file);
    return act(() => api('/documents', 'POST', { name: file.name, data, user_id: body.user_id }), 'Uploaded', load);
  });

  return <>
    <EmpFilter />
    <div className="card"><h2>Documents</h2>
      <Table rows={rows} cols={[['Name', 'name'], ...(isAdmin ? [['Employee', 'owner']] : []),
        ['Size', '', (d) => `${(d.size / 1024).toFixed(0)} KB`], ['Uploaded', '', (d) => d.uploaded.slice(0, 10)],
        ['', '', (d) => <span className="row"><a className="btn sm sec" href={`/api/documents/${d.id}`}>Download</a>
          <button className="btn sm danger" onClick={() => confirm('Delete?') && act(() => api(`/documents/${d.id}`, 'DELETE'), 'Deleted', load)}>Delete</button></span>]]} />
    </div>
    <div className="card"><h3>Upload</h3>
      <form className="f" onSubmit={upload}>
        {isAdmin && <label>For employee<select name="user_id" defaultValue={uid || me.id}><EmpOptions /></select></label>}
        <label>File (max 7 MB)<input type="file" name="file" required /></label>
        <button className="btn">Upload</button>
      </form></div>
  </>;
}
