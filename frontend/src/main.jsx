import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const examples = [
  ['Pagination', 'GET /products?page=1&size=2 skips Notebook and Pencil. Page 1 should include IDs 1 and 2.'],
  ['Missing product', 'GET /products/999 returns a server error instead of 404 when the product does not exist.'],
  ['Filtering', 'GET /products/search?category=stationery includes inactive Pencil and active home products. Only active stationery should be returned.'],
  ['Vague issue', 'The catalog sometimes looks wrong. Can you investigate?'],
  ['Missing context', 'Our payment provider charges customers twice after checkout. Find the cause of the duplicate charge.'],
];
const terminal = new Set(['awaiting_review', 'accepted', 'failed']);
const label = value => value?.replaceAll('_', ' ') || 'loading';

async function api(path, body) {
  const response = await fetch(`/api${path}`, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  } : undefined);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.map(x => x.msg).join('; ') || `Request failed (${response.status})`);
  }
  return response.json();
}

function App() {
  const [health, setHealth] = useState(null);
  const [issue, setIssue] = useState('');
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(location.hash.slice(1));
  const [investigation, setInvestigation] = useState(null);
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [error, setError] = useState('');
  const [historyPage, setHistoryPage] = useState(0);

  useEffect(() => {
    let alive = true;
    async function refresh() {
      try {
        const [info, rows] = await Promise.all([api('/health'), api(`/investigations?limit=20&offset=${historyPage * 20}`)]);
        if (alive) { setHealth(info); setHistory(rows); }
      } catch (e) { if (alive) setError(`Backend unavailable: ${e.message}`); }
    }
    refresh();
    const timer = setInterval(refresh, 2500);
    return () => { alive = false; clearInterval(timer); };
  }, [historyPage]);

  useEffect(() => {
    const onHash = () => setSelected(location.hash.slice(1));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    setInvestigation(null); setFeedback('');
  }, [selected]);

  useEffect(() => {
    let alive = true, timer;
    async function poll() {
      try {
        const row = await api(`/investigations/${encodeURIComponent(selected)}`);
        if (alive) {
          setInvestigation(row);
          if (!terminal.has(row.status)) timer = setTimeout(poll, 800);
        }
      } catch (e) { if (alive) { setError(e.message); timer = setTimeout(poll, 2500); } }
    }
    if (selected) poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [selected, refreshToken]);

  function choose(id) { setError(''); setSelected(id); location.hash = id; window.scrollTo({top: 0}); }
  async function create(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const row = await api('/investigations', { issue });
      setHistoryPage(0); setHistory(rows => [row, ...rows].slice(0, 20)); choose(row.id); setIssue('');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function review(decision) {
    setBusy(true); setError('');
    try {
      const row = await api(`/investigations/${selected}/review`, { decision, feedback, report_version: investigation.state.report_version });
      setInvestigation(row); setFeedback('');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); setRefreshToken(n => n + 1); }
  }

  const state = investigation?.state;
  const report = state?.report;
  return <div className="app">
    <aside>
      <a className="brand" href="#" onClick={() => choose('')}><span className="brand-icon">⌕</span><span>Issue Lab<small>LOCAL REPOSITORY INVESTIGATIONS</small></span></a>
      <button className="new" onClick={() => choose('')}>＋ New investigation</button>
      <div className="sidebar-title">HISTORY <span>{history.length}</span></div>
      <nav aria-label="Investigation history">
        {history.length === 0 && <p className="empty-history">Your investigations will appear here.</p>}
        {history.map(row => <button key={row.id} className={`history-item ${selected === row.id ? 'selected' : ''}`} onClick={() => choose(row.id)}>
          <span>{row.issue}</span><small><i className={`dot ${row.status}`} />{label(row.status)} · {row.mode}</small>
        </button>)}
      </nav>
      <div className="history-pages"><button className="more" disabled={historyPage === 0} onClick={() => setHistoryPage(n => n - 1)}>Newer</button><button className="more" disabled={history.length < 20} onClick={() => setHistoryPage(n => n + 1)}>Older</button></div>
      <div className="repo"><span className="repo-icon">▱</span><div>{health?.repository || 'Connecting…'}<small>Read-only · local Python repository</small></div></div>
    </aside>
    <main>
      <header><span>WORKSPACE <b>/</b> Investigation assistant</span><span className={`mode ${health?.mode === 'mock' ? 'mock' : ''}`}>{health ? `${health.mode === 'mock' ? '● Mock demo' : '● Live Gemini'}` : 'Connecting'}</span></header>
      <div className="content">
        {error && <div role="alert" className="error">{error}<button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
        {health?.mode === 'mock' && <div className="notice">DEMO MODE <span>Deterministic sample responses. No live AI calls are being made.</span></div>}
        {!selected ? <>
          <div className="eyebrow">FROM ISSUE TO EVIDENCE</div>
          <h1>A clearer starting point<br />for your next fix.</h1>
          <p className="intro">Describe a bug. Follow the evidence. Review a diagnosis before deciding what to do next.</p>
          <form className="panel composer" onSubmit={create}>
            <label htmlFor="issue">What’s going wrong?</label><p>Include the endpoint, inputs, and expected versus actual behavior.</p>
            <textarea id="issue" value={issue} onChange={e => setIssue(e.target.value)} minLength={10} maxLength={6000} required placeholder="For example: the first page of products skips the first two items…" rows={6} />
            <div className="composer-footer"><span>{issue.length} / 6,000 characters</span><button className="primary" disabled={busy || issue.trim().length < 10}>{busy ? 'Starting…' : 'Investigate issue →'}</button></div>
          </form>
          <div className="section-heading">TRY A SAMPLE ISSUE <span>Tiny Catalog</span></div>
          <div className="examples">{examples.map(([title, description], index) => <button key={title} onClick={() => setIssue(description)}><span>0{index + 1}</span><strong>{title}</strong><span>↗</span></button>)}</div>
          <div className="workflow-preview"><span>01 <b>Search</b></span><i>→</i><span>02 <b>Investigate</b></span><i>→</i><span>03 <b>Review together</b></span></div>
        </> : investigation ? <>
          <div className="detail-title"><div><div className="eyebrow">INVESTIGATION · {investigation.id.slice(0, 8)}</div><h1>Follow the evidence.</h1></div><span className={`status ${investigation.status}`}>{label(investigation.status)}</span></div>
          <p className="issue-text">{investigation.issue}</p>
          <div className="metrics"><div><small>SEARCH ROUNDS</small><b>{state.search_rounds || 0} <em>/ 3</em></b></div><div><small>EVIDENCE SNIPPETS</small><b>{state.snippets?.length || 0}</b></div><div><small>REPORT VERSION</small><b>{state.report_version || '—'}</b></div><div><small>EXECUTION</small><b>{investigation.mode === 'mock' ? 'Mock demo' : investigation.mode === 'gemini' ? 'Gemini' : 'Legacy provider'}</b></div></div>
          {!terminal.has(investigation.status) && <p className="progress" role="status"><span className="spinner" />{label(investigation.status)}… This page updates automatically.</p>}
          {investigation.error && <div className="error" role="alert">{investigation.error}</div>}
          {state.plan && <details className="search-details"><summary>Search plan & retrieval notes</summary><p>Terms: {state.plan.terms.join(', ')}</p><p>Files: {state.plan.files.join(', ') || 'Keyword search'}</p>{state.retrieval_notes?.map((note, i) => <p key={i}>{note}</p>)}</details>}
          {report && <>
            <section className="panel report"><div className="section-heading">DIAGNOSIS <span>{report.partial ? 'Partial report · more information needed' : 'Hypothesis · requires verification'}</span></div>
              <h2>Likely cause</h2><p className="preserve">{report.likely_cause}</p>
              <div className="citations">{report.citations.map((c, i) => <a href={`#evidence-${c.snippet_id}`} key={i} onClick={e => {e.preventDefault(); const el = document.getElementById(`evidence-${c.snippet_id}`); if (el) { el.open = true; el.scrollIntoView({ behavior: 'smooth' }); }}}><code>{c.snippet_id} · {c.path}:{c.start_line}–{c.end_line}</code><span>{c.explanation}</span></a>)}</div>
              <h2>Suggested fix</h2><pre className="fix">{report.suggested_fix}</pre>
              <h2>Suggested test cases</h2><ul>{report.suggested_tests.map((test, i) => <li key={i}>{test}</li>)}</ul>
              <div className="uncertainty"><h2>Uncertainties</h2><ul>{report.uncertainties.map((text, i) => <li key={i}>{text}</li>)}</ul></div>
              <p className="footnote">References are checked against retrieved snippets. That does not prove the diagnosis is correct. No target code was executed or modified.</p>
            </section>
            {investigation.status === 'awaiting_review' && <section className="panel review"><div className="section-heading">YOUR REVIEW <span>Workflow paused</span></div><h2>Does this report help?</h2><label htmlFor="feedback">Feedback for a revision</label><textarea id="feedback" rows={3} maxLength={3000} value={feedback} onChange={e => setFeedback(e.target.value)} placeholder="What should the assistant reconsider or explain?" /><div className="review-actions"><button disabled={busy || !feedback.trim()} onClick={() => review('revise')}>Request revision</button><button className="primary" disabled={busy} onClick={() => review('accept')}>Accept report ✓</button></div></section>}
            {investigation.status === 'accepted' && <div className="accepted-banner">✓ Report accepted. The suggested fix remains text for you to review and implement.</div>}
          </>}
          <section className="evidence"><div className="section-heading">COLLECTED EVIDENCE <span>Saved snapshots</span></div>{state.snippets?.map(s => <details className="panel snippet" id={`evidence-${s.id}`} key={s.id}><summary><span>{s.id}</span> {s.path} <small>Lines {s.start_line}–{s.end_line}</small></summary><pre>{s.content.split('\n').map((line, i) => <div key={i}><span className="line-number">{s.start_line + i}</span>{line || ' '}</div>)}</pre></details>)}</section>
        </> : <p role="status">Loading investigation…</p>}
        <footer>GitHub Issue Investigation Assistant · Local baseline · Human-reviewed hypotheses</footer>
      </div>
    </main>
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
