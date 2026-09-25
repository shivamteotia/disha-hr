'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { api } from '@/lib';
import DishaChat from '@/components/DishaChat';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

const TABS = [['/', 'Dashboard'], ['/disha', 'Disha ✨'], ['/attendance', 'Attendance'], ['/leaves', 'Leaves'], ['/expenses', 'Expenses'],
  ['/payslips', 'Payslips'], ['/goals', 'Goals'], ['/documents', 'Documents'], ['/employees', 'Employees'], ['/profile', 'Profile'], ['/how-it-works', 'How it works']];

export default function Shell({ children }) {
  const [me, setMe] = useState(null);
  const [emps, setEmps] = useState([]);
  const [uid, setUid] = useState(''); // admin's "view employee" filter, shared across pages
  const [msg, setMsg] = useState('');
  const [chat, setChat] = useState(false); // floating Disha popup; stays mounted once opened so the chat survives navigation
  const [chatUsed, setChatUsed] = useState(false);
  const timer = useRef();
  const pathname = usePathname();

  const reloadMe = useCallback(() => api('/me').then(setMe), []);
  const reloadEmps = useCallback(() => api('/employees').then(setEmps), []);
  const [loadErr, setLoadErr] = useState('');
  const start = useCallback(() => {
    setLoadErr('');
    reloadMe().then(reloadEmps).catch((e) => setLoadErr(e.message)); // 401 already redirected to /login
  }, [reloadMe, reloadEmps]);
  useEffect(start, [start]);

  const toast = useCallback((m) => { setMsg(m); clearTimeout(timer.current); timer.current = setTimeout(() => setMsg(''), 2500); }, []);
  // run an API call; toast the result; reload on success. Returns true on success.
  const act = useCallback(async (fn, okMsg, after) => {
    try { await fn(); if (okMsg) toast(okMsg); await after?.(); return true; } catch (e) { toast(e.message); return false; }
  }, [toast]);

  if (!me) return loadErr ? (
    <>
      <header><b>DISHA</b></header>
      <main><div className="card login">
        <h2>Can't load DISHA</h2>
        <p>{loadErr}</p>
        <button className="btn" onClick={start}>Retry</button>
      </div></main>
    </>
  ) : null;
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
      {pathname !== '/disha' && <>
        <div className={`chat-pop noprint${chat ? ' shown' : ''}`}>{chatUsed && <DishaChat />}</div>
        <button className={`fab noprint${chat ? ' shown' : ''}`} aria-label={chat ? 'Close Disha' : 'Chat with Disha'}
          onClick={() => { setChat(!chat); setChatUsed(true); }}>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {chat ? <path d="M18 6 6 18M6 6l12 12" />
              : <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />}
          </svg>
        </button>
      </>}
      {msg && <div className="toast">{msg}</div>}
    </Ctx.Provider>
  );
}
