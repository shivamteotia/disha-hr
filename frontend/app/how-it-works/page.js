// Public walkthrough for reviewers (no login). Numbers are copied from backend/evals/baselines/RESULTS.md
// and one LangSmith trace; re-copy them when the baseline is re-blessed.
export const metadata = { title: 'How DISHA works' };

const box = { border: '1px solid var(--b)', borderRadius: 10, padding: '10px 12px', background: '#fff', textAlign: 'center' };
const node = { ...box, borderColor: 'var(--p)', background: '#eef2fc' };
const small = { fontSize: 13, color: 'var(--m)' };
const arrow = <div style={{ textAlign: 'center', color: 'var(--m)', fontSize: 18, lineHeight: '22px' }}>↓</div>;

const EVALS = [
  // metric, what it checks, current baseline (2026-09-25), FlashRank (previous)
  ['Route correct', 'planner picked policy / data / conversational', '100%', '98%'],
  ['Data answers correct', 'answer contains the number the truth SQL returns', '100%', '100%'],
  ['Safety refusals', 'no other employee\'s data or system prompt leaked', '100%', '100%'],
  ['Correctness', 'judge vs expected answer (policy)', '0.92', '0.73'],
  ['Completeness', 'judge vs expected answer (policy)', '0.84', '0.70'],
  ['Faithfulness', 'answer backed by retrieved passages', '0.99', '0.99'],
  ['Contextual recall', 'retrieval found what the answer needs', '1.00', '0.80'],
  ['Contextual precision', 'relevant passages ranked first', '1.00', '0.84'],
  ['PII leakage', '1 = nothing leaked', '1.00', '1.00'],
  ['Scope adherence', 'declines off-topic requests', '0.79', '0.78'],
  ['Latency p50 / p95', 'end to end, through the API (p95 inflated by a flaky local network)', '5.2s / 8.5s', '7.9s / 10.1s'],
];

// checked against the live API as rahul.sharma on 2026-09-23
const TRY = [
  ['How many days a week do I need to be in the office?', 'policy', 'searches the policies, cites the Remote Work policy'],
  ['How many casual leaves do I have left this year?', 'data', 'text-to-SQL on your own leave records'],
  ['How many leave requests from my team are waiting for my approval?', 'data', 'manager-only: Rahul\'s views include his team'],
  ['What was my net pay in August 2026?', 'data', 'reads your own payslip'],
  ['What is Sneha Iyer\'s net salary?', 'refused', 'another employee\'s pay: blocked by the input rail'],
  ['Write me a poem about cricket.', 'refused', 'off-topic: blocked by the input rail'],
];

const LAYERS = [
  ['Scoped views', 'For each question, temporary views named like the real tables (leaves, payslips…) hold only the rows the asker may see. The model writes SQL against these.'],
  ['SQL validation', 'One statement, SELECT/WITH only, only whitelisted view names, no PRAGMA / ATTACH / set_config / system catalogs / recursive CTEs, 2,000-char cap.'],
  ['Forced row limit', 'LIMIT 200 is appended to every query.'],
  ['Database-level block', 'Even a query that slips past validation cannot read a real table: a SQLite authorizer (or, on Postgres, a NOLOGIN role with no table grants) refuses it.'],
  ['Throwaway connection', 'Never pooled, always rolled back, so the views can\'t leak into the app\'s own queries.'],
];

const BLOCKED = [
  ['SELECT u.pass FROM leaves l, users u', 'comma join to a real table: passes the name check, stopped by the database block'],
  ['WITH users AS (SELECT 1 AS id) SELECT * FROM users', 'a CTE shadowing a real table name'],
  ['WITH RECURSIVE c AS (… n+1 …) SELECT count(*) FROM c', 'unbounded recursion, a denial-of-service'],
  ['SELECT set_config(\'role\', \'postgres\', true)', 'climbing out of the sandbox role'],
];

const CAUGHT = [
  ['Wrong passage from the reranker', 'A local cross-encoder (FlashRank) dropped the answering passage for 2 policy questions after the planner rewrote them, so the office-days question was answered "five days, Mon–Fri". Switching to an LLM reranker: contextual recall 0.80 → 1.00, correctness 0.73 → 0.93.'],
  ['Data route broken by a security fix', 'A tighter SQLite authorizer also blocked a read SQLite makes internally when it flattens a view: data answers fell to 1/5. The eval caught it; the fix and a regression test brought it back to 5/5 in every run.'],
  ['Planner misrouting', 'An HRA question went to small talk in 2 of 5 runs. The current setup routed it correctly in all 5 baseline runs, but it still slips occasionally (1 of 3 runs on 2026-09-25).'],
  ['A manager counted the team\'s leave as their own', 'Asked "how many casual leaves do I have left?", Rahul (a manager) was told 0 instead of 12: his view includes the team\'s leave and the SQL didn\'t filter to him. The golden set only asked as a non-manager, so it never showed. Fixed with an explicit rule plus a golden case asked as a manager.'],
  ['Valid SQL, wrong question', 'One CI run summed every leave type for a casual-leave balance, and compared an employee\'s name with ids for "waiting for my approval". Both were sometimes-wrong, not always-wrong: hints and a worked example in the SQL prompt fixed them in 3 of 3 re-runs.'],
];

const LIMITS = [
  'A question mixing an HR part with an off-topic part is refused whole instead of answering the HR half.',
  'The chat rate limit (8/min, 50/hour per employee) is kept in memory, so it holds per API process, not across several workers.',
  'LLM-judged scores vary by 0.07–0.22 between runs, more than the compare script\'s 0.02–0.05 tolerances, so a single run can be flagged from noise alone. Deterministic checks don\'t have this problem.',
  'Policy documents are sample content, and 8 policy questions is a small sample: one question flipping moves a quality score by 0.125.',
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
            employee's own records. This page shows what to try, the assistant's graph, how its SQL is kept safe, how it is evaluated, a real trace, and its known limits.
          </p>
          <p style={{ ...small, marginBottom: 0 }}>Demo login: rahul.sharma@company.com / password123</p>
        </div>

        <div className="card">
          <h2>Try these in Disha</h2>
          <p style={{ marginTop: 0 }}>
            <a href="/login">Sign in as Rahul</a>, tap the chat button in the bottom-right corner and ask. The line under each answer
            shows the route it took.
          </p>
          <div className="tbl">
            <table>
              <thead><tr><th>Ask</th><th>Route</th><th>What it shows</th></tr></thead>
              <tbody>{TRY.map(([q, route, what]) => (
                <tr key={q}><td style={{ whiteSpace: 'normal' }}>{q}</td>
                  <td><span className="tag" style={route === 'refused' ? { color: 'var(--bad)' } : undefined}>{route}</span></td>
                  <td style={{ ...small, whiteSpace: 'normal' }}>{what}</td></tr>
              ))}</tbody>
            </table>
          </div>
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
        </div>

        <div className="card">
          <h2>Keeping text-to-SQL safe</h2>
          <p style={{ marginTop: 0 }}>
            Letting a model write SQL over HR data is the riskiest part of the app, so the data route is boxed in by
            five layers (<code>backend/app/safe_sql.py</code>). Any one of them failing still leaves the others.
          </p>
          <ol style={{ paddingLeft: 20 }}>
            {LAYERS.map(([name, what]) => <li key={name} style={{ marginBottom: 6 }}><b>{name}.</b> {what}</li>)}
          </ol>
          <p style={{ marginBottom: 6 }}>Queries the tests prove are refused (<code>backend/test_agent.py</code>):</p>
          <div className="tbl">
            <table>
              <tbody>{BLOCKED.map(([sql, why]) => (
                <tr key={sql}><td><code style={{ fontSize: 12 }}>{sql}</code></td><td style={{ ...small, whiteSpace: 'normal' }}>{why}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <p style={small}>
            In front of all this, NeMo Guardrails screen every question and every answer. That's why the salary
            question in "Try these" never reaches the SQL step, and if it did, Rahul's payslips view holds only his
            own rows.
          </p>
        </div>

        <div className="card">
          <h2>Evaluation results</h2>
          <p style={{ marginTop: 0 }}>
            21 golden questions (policy, personal data, safety, off-topic) sent through the running API, 5 full runs
            averaged. Route, data and safety checks are deterministic; the rest are judged by an LLM (DeepEval,
            gpt-5.4-mini). Every push to main re-runs the deterministic checks against this baseline before it can deploy.
          </p>
          <div className="tbl">
            <table>
              <thead><tr><th>Metric</th><th>Checks</th><th>Current</th><th>Previous (FlashRank)</th></tr></thead>
              <tbody>{EVALS.map(([m, what, now, before]) => (
                <tr key={m}><td>{m}</td><td style={small}>{what}</td><td><b>{now}</b></td><td>{before}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h2>What the evals caught</h2>
          {CAUGHT.map(([title, what]) => (
            <div key={title} style={{ borderLeft: '3px solid var(--p)', padding: '2px 0 2px 12px', marginBottom: 12 }}>
              <b>{title}</b>
              <div style={{ fontSize: 14 }}>{what}</div>
            </div>
          ))}
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

        <div className="card">
          <h2>Known limitations</h2>
          <ul style={{ paddingLeft: 20, margin: 0 }}>
            {LIMITS.map((l) => <li key={l} style={{ marginBottom: 6 }}>{l}</li>)}
          </ul>
        </div>
      </main>
    </>
  );
}
