import { useCallback, useEffect, useState } from 'react';

export async function api(path, method = 'GET', body) {
  const r = await fetch('/api' + path, method === 'GET' ? {} :
    { method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body ?? {}) });
  const d = await r.json().catch(() => null);
  if (r.status === 401 && location.pathname !== '/login') location.href = '/login';
  if (!r.ok) throw new Error(d?.detail || r.statusText);
  return d;
}

export const money = (n) => Number(n || 0).toLocaleString('en-IN', { style: 'currency', currency: 'INR' });
export const today = () => new Date().toLocaleDateString('sv-SE'); // YYYY-MM-DD, local
export const thisMonth = () => today().slice(0, 7);
export const readB64 = (file) => new Promise((ok) => {
  const rd = new FileReader();
  rd.onload = () => ok(rd.result.split(',')[1]);
  rd.readAsDataURL(file);
});

// [data, reload] — refetches whenever deps change
export function useLoad(fn, deps) {
  const [data, setData] = useState(null);
  const load = useCallback(() => fn().then(setData, () => {}), deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  return [data, load];
}

// <form onSubmit={onSubmit(async (body, form) => ok?)}> — resets the form when the handler returns true
export const onSubmit = (handler) => async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  if (await handler(Object.fromEntries(new FormData(form)), form)) form.reset();
};
