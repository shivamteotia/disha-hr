// Public walkthrough for reviewers (no login). Numbers are copied from backend/evals/baselines/RESULTS.md
// and one LangSmith trace; re-copy them when the baseline is re-blessed.
export const metadata = { title: 'How DISHA works' };

const box = { border: '1px solid var(--b)', borderRadius: 10, padding: '10px 12px', background: '#fff', textAlign: 'center' };
const node = { ...box, borderColor: 'var(--p)', background: '#eef2fc' };
const small = { fontSize: 13, color: 'var(--m)' };
const arrow = <div style={{ textAlign: 'center', color: 'var(--m)', fontSize: 18, lineHeight: '22px' }}>↓</div>;

const EVALS = [
  // metric, what it checks, LLM reranker (current), FlashRank (previous)
  ['Route correct', 'planner picked policy / data / conversational', '100%', '98%'],
  ['Data answers correct', 'answer contains the number the truth SQL returns', '100%', '100%'],
  ['Safety refusals', 'no other employee\'s data or system prompt leaked', '100%', '100%'],
  ['Correctness', 'judge vs expected answer (policy)', '0.93', '0.73'],
  ['Completeness', 'judge vs expected answer (policy)', '0.83', '0.70'],
  ['Faithfulness', 'answer backed by retrieved passages', '1.00', '0.99'],
  ['Contextual recall', 'retrieval found what the answer needs', '1.00', '0.80'],
  ['Contextual precision', 'relevant passages ranked first', '1.00', '0.84'],
  ['PII leakage', '1 = nothing leaked', '1.00', '1.00'],
  ['Scope adherence', 'declines off-topic requests', '0.75', '0.78'],
  ['Latency p50 / p95', 'end to end, through the live API', '4.5s / 6.9s', '7.9s / 10.1s'],
];

const TRACE = [
  // span, what happens, start ms, duration ms
  ['guard_plan', 'input rail ∥ planner (gpt-5.4-mini) → route: policy', 6, 1399],
  ['retrieve', 'embed rewritten query, Qdrant search, LLM rerank → 2 passages', 1405, 2734],
  ['responder', 'answer streamed from the 2 passages (gpt-5.4-mini)', 4146, 1306],
];
const TOTAL = 5452;

function Flow() {
  return (
    <div style={{ maxWidth: 560, margin: '0 auto' }}>
      <div style={box}>Question <span style={small}>(+ last few turns)</span></div>
      {arrow}
      <div style={node}>
        <b>guard_plan</b>
        <div style={small}>NeMo input rail and the planner run concurrently; a refusal discards the plan</div>
      </div>
      {arrow}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        <div style={node}><b>retrieve</b><div style={small}>policy: Qdrant RAG + rerank</div></div>
        <div style={node}><b>query_data</b><div style={small}>data: text-to-SQL on views scoped to the asker</div></div>
        <div style={box}><b>—</b><div style={small}>small talk or refused: skip straight to the answer</div></div>
      </div>
      <p style={{ ...small, textAlign: 'center', margin: '6px 0' }}>LangGraph ends here; the answer is written outside the graph so it can stream</p>
      <div style={box}><b>responder</b><div style={small}>streams the answer token by token</div></div>
      {arrow}
      <div style={box}><b>output rail</b><div style={small}>checks the finished answer; a block replaces the shown text</div></div>
    </div>
  );
}

export default function HowItWorks() {
  return (
    <>
      <header><b>DISHA</b><a className="btn sec sm" href="/login">Try the app</a></header>
      <main>
        <div className="card">
          <h2>How DISHA works</h2>
          <p style={{ margin: 0 }}>
            DISHA is a mobile-friendly HR app (Next.js → FastAPI → SQLite/PostgreSQL) with <b>Disha</b>, an
            assistant that answers HR-policy questions from company documents and personal questions from the
            employee's own records. This page shows the assistant's graph, how it is evaluated, and a real trace.
          </p>
          <p style={{ ...small, marginBottom: 0 }}>Demo login: rahul.sharma@company.com / password123</p>
        </div>

        <div className="card">
          <h2>Disha in the app</h2>
          <img src="/disha-chat.png" alt="Disha answering a holiday question from HR data and a WFH question from policy, with the steps it took under each answer"
            style={{ width: '100%', maxWidth: 720, display: 'block', border: '1px solid var(--b)', borderRadius: 10 }} />
          <p style={small}>
            Under each answer is the path it took: <i>Intent: data → Queried HR data (1 rows)</i> for the holiday,
            <i> Intent: policy → Searched policies (2 passages)</i> for WFH, with the source policy cited.
          </p>
        </div>

        <div className="card">
          <h2>The LangGraph planner</h2>
          <Flow />
          <p style={small}>
            The data route never sees raw tables: it may run one SELECT against temporary views already filtered to
            the asking employee (managers also see their team's leaves and expenses), with a forced row limit.
          </p>
        </div>

        <div className="card">
          <h2>Evaluation results</h2>
          <p style={{ marginTop: 0 }}>
            20 golden questions (policy, personal data, safety, off-topic) sent through the running API, 5 full runs
            averaged. Route, data and safety checks are deterministic; the rest are judged by an LLM (DeepEval,
            gpt-5.4-mini). A compare script gates changes against this baseline.
          </p>
          <div className="tbl">
            <table>
              <thead><tr><th>Metric</th><th>Checks</th><th>Current</th><th>Previous (FlashRank)</th></tr></thead>
              <tbody>{EVALS.map(([m, what, now, before]) => (
                <tr key={m}><td>{m}</td><td style={small}>{what}</td><td><b>{now}</b></td><td>{before}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <p style={small}>
            Switching the reranker from a local cross-encoder to an LLM fixed two policy questions where the right
            passage was being dropped. Known gap: a question mixing an HR part with an off-topic part is refused
            whole, which is what pulls scope adherence down.
          </p>
        </div>

        <div className="card">
          <h2>A real trace</h2>
          <p style={{ marginTop: 0 }}>
            <i>"A client wants to give me a gift. When do I have to declare it?"</i> → "If it's worth more than
            ₹2,500, you must decline it or declare it to HR. (Code of Conduct)"
          </p>
          {TRACE.map(([name, what, start, ms]) => (
            <div key={name} style={{ marginBottom: 10 }}>
              <div className="row" style={{ justifyContent: 'space-between' }}><b>{name}</b><span style={small}>{(ms / 1000).toFixed(2)}s</span></div>
              <div style={{ background: 'var(--bg)', borderRadius: 4, height: 10, position: 'relative' }}>
                <div style={{ position: 'absolute', left: `${(start / TOTAL) * 100}%`, width: `${(ms / TOTAL) * 100}%`, height: '100%', background: 'var(--p)', borderRadius: 4 }} />
              </div>
              <div style={small}>{what}</div>
            </div>
          ))}
          <p style={small}>
            About {(TOTAL / 1000).toFixed(1)}s in total, and the first words appear as soon as the responder starts. Every graph node and every
            model prompt/completion is traced in LangSmith, with Logfire spans for the same nodes.
          </p>
        </div>
      </main>
    </>
  );
}
