'use client';
import { useEffect, useState } from 'react';
import { api, onSubmit } from '@/lib';

export default function Login() {
  const [error, setError] = useState('');
  useEffect(() => { api('/me').then(() => (location.href = '/'), () => {}); }, []);
  const login = onSubmit(async (body) => {
    try { await api('/login', 'POST', body); location.href = '/'; } catch (e) { setError(e.message); }
  });
  return (
    <>
      <header><b>DISHA</b></header>
      <div className="card login">
        <h2>Sign in</h2>
        <form className="f" style={{ gridTemplateColumns: '1fr' }} onSubmit={login}>
          <label>Email<input type="email" name="email" required autoComplete="username" /></label>
          <label>Password<input type="password" name="password" required autoComplete="current-password" /></label>
          {error && <p style={{ color: 'var(--bad)', margin: 0 }}>{error}</p>}
          <button className="btn">Sign in</button>
        </form>
      </div>
    </>
  );
}
