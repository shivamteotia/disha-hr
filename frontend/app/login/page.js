'use client';
import { useEffect, useState } from 'react';
import { api, onSubmit } from '@/lib';

export default function Login() {
  const [error, setError] = useState('');
  useEffect(() => { api('/me').then(() => (location.href = '/'), () => {}); }, []); // already signed in
  const login = onSubmit(async (body) => {
    try {
      setError('');
      await api('/login', 'POST', body);
      location.href = '/';
    } catch (e) { setError(e.message); }
  });
  return (
    <>
      <header><b>DISHA</b></header>
      <div className="card login">
        <h2>Sign in</h2>
        <form className="f" style={{ gridTemplateColumns: '1fr' }} onSubmit={login}>
          {/* seeded demo employee (python -m app.seed), not the admin */}
          <label>Email<input type="email" name="email" required autoComplete="username" defaultValue="rahul.sharma@company.com" /></label>
          <label>Password<input type="password" name="password" required autoComplete="current-password" defaultValue="password123" /></label>
          <p style={{ color: 'var(--m)', margin: 0, fontSize: 13 }}>
            Demo employee: rahul.sharma@company.com / password123 (a manager, so approvals show too)
          </p>
          <a href="/how-it-works" style={{ fontSize: 13 }}>How Disha works: graph, evals and traces →</a>
          {error && <p style={{ color: 'var(--bad)', margin: 0 }}>{error}</p>}
          <button className="btn">Sign in</button>
        </form>
      </div>
    </>
  );
}
