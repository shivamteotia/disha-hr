'use client';
import { useEffect, useState } from 'react';
import { apiWithWake, onSubmit } from '@/lib';

export default function Login() {
  const [error, setError] = useState('');
  const [waking, setWaking] = useState(0);
  useEffect(() => {
    apiWithWake('/me', 'GET', undefined, { onRetry: setWaking })
      .then(() => (location.href = '/'), (e) => { setWaking(0); if (e.hibernating) setError(e.message); });
  }, []);
  const login = onSubmit(async (body) => {
    try {
      setError('');
      await apiWithWake('/login', 'POST', body, { onRetry: setWaking });
      location.href = '/';
    } catch (e) { setError(e.message); } finally { setWaking(0); }
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
          {waking > 0 && <p style={{ color: 'var(--m)', margin: 0 }}>Waking up the server… (attempt {waking})</p>}
          {error && <p style={{ color: 'var(--bad)', margin: 0 }}>{error}</p>}
          <button className="btn" disabled={waking > 0}>Sign in</button>
        </form>
      </div>
    </>
  );
}
