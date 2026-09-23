'use client';
import { useEffect, useRef, useState } from 'react';
import { useApp } from '@/components/Shell';
import { apiStream } from '@/lib';

const SUGGESTIONS = ['How many leaves do I have left?', 'How much notice do I need for earned leave?',
  'Show my attendance this month', 'When is the next holiday?'];

export default function Disha() {
  const { me } = useApp();
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, busy]);

  async function send(text) {
    text = text.trim();
    if (!text || busy) return;
    const next = [...msgs, { role: 'user', content: text }];
    setMsgs(next); setInput(''); setBusy(true);
    try {
      // failed turns are shown but never sent back as history
      const history = next.filter((m) => !m.error).slice(-20).map(({ role, content }) => ({ role, content }));
      let content = '';
      const show = (meta) => setMsgs([...next, { role: 'assistant', content, meta }]);
      await apiStream('/chat/stream', { messages: history }, (e) => {
        if (e.error) throw new Error(e.error);
        if (e.delta) content += e.delta;
        if (e.replace) content = e.replace; // input refused, or the final check withheld the answer
        if (e.done) {
          content = e.done.reply;
          return show({ route: e.done.route, trace: e.done.trace, sources: e.done.sources });
        }
        show();
      });
    } catch (e) {
      setMsgs([...next, { role: 'assistant', content: `Sorry, something went wrong: ${e.message}`, error: true }]);
    } finally { setBusy(false); }
  }

  return (
    <div className="card">
      <div className="row between"><h2>Disha ✨</h2>
        {msgs.length > 0 && <button className="btn sm sec" onClick={() => setMsgs([])}>New chat</button>}</div>
      <div className="chat-log">
        {!msgs.length && <div className="m">
          <p>Hi {me.name.split(' ')[0]}, I'm Disha. Ask about your leaves, attendance, payslips, goals, expenses,
            your team, or company policy.</p>
          <div className="row">{SUGGESTIONS.map((s) => <button key={s} className="btn sm sec" onClick={() => send(s)}>{s}</button>)}</div>
        </div>}
        {msgs.map((m, i) => <div key={i}>
          <div className={`bubble ${m.role}${m.error ? ' error' : ''}`}>{m.content}</div>
          {m.meta?.trace?.length > 0 && <div className="meta">
            {m.meta.trace.join(' → ')}
            {m.meta.sources?.length > 0 && ` · policy: ${m.meta.sources.join(', ')}`}
          </div>}
        </div>)}
        {busy && msgs.at(-1)?.role === 'user' && <div className="bubble assistant m">Disha is thinking…</div>}
        <div ref={end} />
      </div>
      <form className="row" style={{ marginTop: 12, flexWrap: 'nowrap' }} onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask Disha…" maxLength={2000} disabled={busy} />
        <button className="btn" disabled={busy || !input.trim()}>Send</button>
      </form>
      <p className="m" style={{ fontSize: 12, marginBottom: 0 }}>Disha can make mistakes. Check important numbers on the related page.</p>
    </div>
  );
}
