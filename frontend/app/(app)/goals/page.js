'use client';
import { useState } from 'react';
import { useApp } from '@/components/Shell';
import { EmpFilter, EmpOptions, Tag } from '@/components/ui';
import { api, onSubmit, useLoad } from '@/lib';

function Goal({ g, load }) {
  const { isAdmin, act } = useApp();
  const [progress, setProgress] = useState(g.progress);
  const save = () => progress !== g.progress && act(() => api(`/goals/${g.id}`, 'PUT', { progress }), null, load);
  return (
    <div className="card">
      <div className="row between"><b>{g.title}</b><Tag s={g.status} /></div>
      <p className="m">{isAdmin && `${g.name} · `}{g.due && `Due ${g.due}`}</p>
      {g.description && <p>{g.description}</p>}
      <div className="row">
        <input type="range" min="0" max="100" step="5" value={progress} style={{ flex: 1 }}
          onChange={(e) => setProgress(+e.target.value)} onPointerUp={save} onKeyUp={save} />
        <span>{progress}%</span>
        <button className="btn sm danger" onClick={() => confirm('Delete goal?') && act(() => api(`/goals/${g.id}`, 'DELETE'), 'Deleted', load)}>Delete</button>
      </div>
    </div>
  );
}

export default function Goals() {
  const { me, isAdmin, uid, q, act } = useApp();
  const [rows, load] = useLoad(() => api(`/goals?${q}`), [q]);
  if (!rows) return null;
  return <>
    <EmpFilter />
    <div className="card"><h2>Goals</h2>
      {rows.length ? rows.map((g) => <Goal key={`${g.id}-${g.progress}`} g={g} load={load} />) : <p className="m">No goals yet.</p>}
    </div>
    <div className="card"><h3>New goal</h3>
      <form className="f" onSubmit={onSubmit((b) => act(() => api('/goals', 'POST', b), 'Goal added', load))}>
        {isAdmin && <label>Employee<select name="user_id" defaultValue={uid || me.id}><EmpOptions /></select></label>}
        <label>Title<input name="title" required /></label>
        <label>Due<input type="date" name="due" /></label>
        <label>Description<input name="description" /></label>
        <button className="btn">Add</button>
      </form></div>
  </>;
}
