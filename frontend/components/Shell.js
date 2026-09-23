'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { api } from '@/lib';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

const TABS = [['/', 'Dashboard'], ['/disha', 'Disha ✨'], ['/attendance', 'Attendance'], ['/leaves', 'Leaves'], ['/expenses', 'Expenses'],
  ['/payslips', 'Payslips'], ['/goals', 'Goals'], ['/documents', 'Documents'], ['/employees', 'Employees'], ['/profile', 'Profile'], ['/how-it-works', 'How it works']];

export default function Shell({ children }) {
  const [me, setMe] = useState(null);
  const [emps, setEmps] = useState([]);
  const [uid, setUid] = useState(''); // admin's "view employee" filter, shared across pages
  const [msg, setMsg] = useState('');
  const timer = useRef();
  const pathname = usePathname();

  const reloadMe = useCallback(() => api('/me').then(setMe), []);
  const reloadEmps = useCallback(() => api('/employees').then(setEmps), []);
  useEffect(() => { reloadMe().then(reloadEmps).catch(() => {}); }, [reloadMe, reloadEmps]);

  const toast = useCallback((m) => { setMsg(m); clearTimeout(timer.current); timer.current = setTimeout(() => setMsg(''), 2500); }, []);
  // run an API call; toast the result; reload on success. Returns true on success.
  const act = useCallback(async (fn, okMsg, after) => {
    try { await fn(); if (okMsg) toast(okMsg); await after?.(); return true; } catch (e) { toast(e.message); return false; }
  }, [toast]);

  if (!me) return null;
  const isAdmin = me.role === 'admin';
  const value = {
    me, reloadMe, emps, reloadEmps, isAdmin, toast, act, setUid,
    uid: isAdmin ? uid : '',
    q: isAdmin && uid ? `user_id=${uid}` : '',
    // requests (leaves/expenses) include the viewer's team; approver = admin or the requester's manager, never self
    canDecide: (r) => r.user_id !== me.id && (isAdmin || r.manager_id === me.id),
    others: (rows) => isAdmin || rows.some((r) => r.user_id !== me.id),
  };
  const logout = async () => { await api('/logout', 'POST').catch(() => {}); location.href = '/login'; };

  return (
    <Ctx.Provider value={value}>
      <header><b>DISHA</b><span className="row">{me.name}<button className="btn sec sm" onClick={logout}>Logout</button></span></header>
      <nav>{TABS.map(([href, label]) => <Link key={href} href={href} className={pathname === href ? 'on' : ''}>{label}</Link>)}</nav>
      <main>{children}</main>
      {msg && <div className="toast">{msg}</div>}
    </Ctx.Provider>
  );
}
