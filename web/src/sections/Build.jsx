import { Reveal } from '../components/Motion.jsx';

const REPO = 'https://github.com/Omanshhh/Computer-Networks';
const STACK = ['Python 3.13', 'pybgpkit', 'pandas', 'BGPy', 'FRRouting 10.7', 'containerlab', 'Docker on WSL2', 'React + Vite', 'React Bits', 'LaTeX'];

export function Build({ results }) {
  return (
    <section id="build">
      <div className="wrap">
        <Reveal className="section-head">
          <h2>How it's built</h2>
          <p className="lede">
            Python for the measurements and the engine, real routers for the demo. Every number on this page is read from a results file
            in the repository.
          </p>
        </Reveal>
        <div className="bento">
          {results.code.map((c, i) => (
            <Reveal key={c.path} className="s-4" delay={(i % 3) * 0.06}>
              <div className={`glass tile ${c.path === 'guard/engine.py' ? 'tone-route' : ''}`}>
                <div className="tile-head">
                  <span className="mono" style={{ fontWeight: 500 }}>{c.path}</span>
                  <span className="small num">{c.lines} lines</span>
                </div>
                <p className="body">{c.what}</p>
              </div>
            </Reveal>
          ))}
          <Reveal className="s-8">
            <div className="glass tile">
              <h3>Tools</h3>
              <div className="row">{STACK.map(s => <span key={s} className="pill">{s}</span>)}</div>
              <p className="small">{results.tests} unit tests pin down the engine's behaviour: <span className="code">python -m pytest tests</span></p>
            </div>
          </Reveal>
          <Reveal className="s-4" delay={0.08}>
            <div className="glass tile">
              <h3>Source code</h3>
              <p className="body">Code, data pipelines, lab configuration and this site.</p>
              <a className="btn primary" href={REPO} target="_blank" rel="noreferrer">Open the repository on GitHub</a>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

export function Papers() {
  return (
    <section id="paper">
      <div className="wrap">
        <Reveal className="section-head">
          <h2>Paper and report</h2>
          <p className="lede">The full method, every result and the limitations, written up for a conference and for the course.</p>
        </Reveal>
        <div className="bento">
          <Reveal className="s-6">
            <div className="glass tile hero">
              <span className="small">Conference paper, IEEE format, 7 pages</span>
              <h3 style={{ fontSize: '1.35rem' }}>ConeGuard: Containing Mass Re-origination Route Leaks at the Upstream Provider</h3>
              <p className="body">Sara Agrawal, Omansh Sharma, Aakash Prathap and Thamizharasan S, SCOPE, VIT Vellore.</p>
              <div className="row" style={{ marginTop: 'auto' }}>
                <a className="btn primary" href="/files/coneguard-paper.pdf" target="_blank" rel="noreferrer">Open the paper (PDF)</a>
              </div>
            </div>
          </Reveal>
          <Reveal className="s-6" delay={0.08}>
            <div className="glass tile hero">
              <span className="small">Project report, 34 pages</span>
              <h3 style={{ fontSize: '1.35rem' }}>Design, implementation, results and how to reproduce them</h3>
              <p className="body">Literature review, system design, implementation, results, the live demo and step-by-step instructions.</p>
              <div className="row" style={{ marginTop: 'auto' }}>
                <a className="btn primary" href="/files/coneguard-report.pdf" target="_blank" rel="noreferrer">Open the report (PDF)</a>
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
