import { useState } from 'react';
import NetworkMap from '../components/NetworkMap.jsx';
import { LiveRoutes } from '../components/Charts.jsx';
import { Reveal } from '../components/Motion.jsx';
import { act, fmt } from '../lib.js';

const MODES = [
  { id: 'none', name: 'No protection', note: 'How Airtel ran in 2021' },
  { id: 'rov', name: 'ROV', note: 'Drop routes RPKI marks invalid' },
  { id: 'maxprefix', name: 'Max-prefix limit', note: 'Cut the session above 16 routes' },
  { id: 'coneguard', name: 'ConeGuard', note: 'Hold back a burst of foreign routes' },
];

const SITES = [
  { name: 'Google', prefix: '172.217.179.0/24', note: 'signed with RPKI in 2021' },
  { name: 'Fastly', prefix: '167.82.163.0/24', note: 'no RPKI record in 2021' },
  { name: 'Vodafone', prefix: '118.185.0.0/16', note: "Vodafone's own site" },
];

const Tick = () => <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3 3 7-7" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Cross = () => <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" /></svg>;

function ReachTile({ site, state, offline }) {
  const known = state && !offline;
  const ok = known && state.reach?.[site.name];
  return (
    <div className={`glass tile reach ${known ? (ok ? 'tone-ok' : 'tone-bad') : ''}`}>
      <div className="tile-head">
        <h3>User to {site.name}</h3>
      </div>
      <div className="verdict" aria-live="polite">
        <span className="dot" style={known ? undefined : { background: 'var(--quiet)' }}>{known ? (ok ? <Tick /> : <Cross />) : null}</span>
        {known ? (ok ? 'Reachable' : 'Unreachable') : 'No reading'}
      </div>
      <p className="small"><span className="mono">{site.prefix}</span>, {site.note}</p>
    </div>
  );
}

export default function Live({ lab }) {
  const { state, offline } = lab;
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const run = async path => {
    setBusy(path);
    setError(null);
    try {
      await act(path);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };
  const live = state && !offline;
  const up = state?.session === 'Established';
  const counts = state?.counts || {};
  const guarding = state?.mode === 'coneguard';

  return (
    <section id="live" style={{ paddingTop: 112 }}>
      <div className="wrap">
        <div className="section-head" style={{ maxWidth: 980, marginBottom: 24 }}>
          <h1>Contain a mass route leak in seconds, without cutting the customer off</h1>
          <p className="lede">
            A live replay of the 16 April 2021 Vodafone Idea leak on real routers. Choose how Airtel protects
            its Vodafone session, start the leak, and watch whether the user can still reach each site.
          </p>
          <p className="small" style={{ marginTop: 14 }}>
            Sara Agrawal, Omansh Sharma and Aakash Prathap, guided by Thamizharasan S, SCOPE, VIT Vellore.
          </p>
        </div>

        {offline && (
          <div className="banner" role="status">
            <span>
              The lab isn't answering. In Ubuntu, start it with <span className="code">containerlab deploy -t lab/coneguard.clab.yml</span> and
              {' '}<span className="code">python3 lab/demo.py</span>, then this page updates by itself.
            </span>
          </div>
        )}
        {error && <div className="banner" role="alert">{error}</div>}

        <div className="bento">
          <Reveal className="s-7 r-3" delay={0}><div className="glass tile hero">
            <div className="tile-head">
              <h3>Live network</h3>
              <span className={`pill ${live ? 'route' : ''}`}>{live ? 'live, updated every second' : 'waiting for the lab'}</span>
            </div>
            <NetworkMap state={state} offline={offline} />
          </div></Reveal>

          <Reveal className="s-5" delay={0.08}><div className="glass tile">
            <div className="tile-head"><h3>Airtel's protection</h3></div>
            <div className="modes">
              {MODES.map(m => (
                <button key={m.id} className="btn mode" aria-pressed={state?.mode === m.id} disabled={!live || busy != null}
                  onClick={() => run(`mode/${m.id}`)}>
                  <strong>{busy === `mode/${m.id}` ? 'Switching...' : m.name}</strong>
                  <span>{m.note}</span>
                </button>
              ))}
            </div>
          </div></Reveal>

          <Reveal className="s-5" delay={0.16}><div className={`glass tile ${state?.injected > 0 ? 'tone-bad' : ''}`}>
            <div className="tile-head">
              <h3>Vodafone's leak</h3>
              <span className={`pill ${up ? 'ok' : 'bad'}`}>{live ? (up ? 'session up' : `session ${state.session}`) : 'session unknown'}</span>
            </div>
            <div>
              <div className="meter" aria-hidden="true"><i style={{ width: `${((state?.injected || 0) / 3000) * 100}%` }} /></div>
              <p className="small num" style={{ marginTop: 8 }}>
                {fmt(state?.injected || 0)} of 3,000 real leaked prefixes announced. Airtel accepts <b>{fmt(state?.accepted ?? 0)}</b> routes from Vodafone, 8 of them Vodafone's own.
              </p>
            </div>
            <div className="row">
              <button className="btn danger" disabled={!live || busy != null || state?.leaking} onClick={() => run('leak')}>
                {busy === 'leak' ? 'Starting...' : 'Start the leak'}
              </button>
              <button className="btn" disabled={!live || busy != null} onClick={() => run('stop')}>{busy === 'stop' ? 'Stopping...' : 'Stop the leak'}</button>
              <button className="btn" disabled={!live || busy != null} onClick={() => run('reset')}>{busy === 'reset' ? 'Resetting...' : 'Reset the lab'}</button>
            </div>
          </div></Reveal>

          <Reveal className="s-5" delay={0.24}><div className={`glass tile ${guarding && state?.burst ? 'tone-hold' : guarding ? 'tone-route' : ''}`}>
            <div className="tile-head">
              <h3>ConeGuard</h3>
              <span className={`pill ${guarding ? (state?.burst ? 'hold' : 'route') : ''}`}>
                {guarding ? (state?.burst ? 'mass leak detected' : 'watching') : state?.mode === 'rov' ? 'ROV only' : 'off'}
              </span>
            </div>
            <div className="stats">
              <div className="stat"><div className="v num">{fmt(counts.reject ?? 0)}</div><div className="k">rejected as RPKI-invalid</div></div>
              <div className="stat"><div className="v num">{fmt(counts.quarantine ?? 0)}</div><div className="k">quarantined as foreign</div></div>
              <div className="stat"><div className="v num">{fmt(counts.alert ?? 0)}</div><div className="k">accepted with an alert</div></div>
            </div>
          </div></Reveal>

          {SITES.map((site, i) => (
            <Reveal key={site.name} className="s-4" delay={0.3 + i * 0.06}><ReachTile site={site} state={state} offline={offline} /></Reveal>
          ))}

          <Reveal className="s-7" delay={0.1}><div className="glass tile">
            <div className="tile-head"><h3>Routes over time</h3></div>
            <LiveRoutes history={state?.history || []} />
          </div></Reveal>

          <Reveal className="s-5" delay={0.16}><div className="glass tile">
            <div className="tile-head"><h3>What happened</h3></div>
            {state?.events?.length ? (
              <ol className="log">
                {state.events.map((e, i) => <li key={i}><time className="num">{e.t}</time><span>{e.msg}</span></li>)}
              </ol>
            ) : (
              <p className="small">Events appear here as you switch protection and start the leak.</p>
            )}
          </div></Reveal>
        </div>
      </div>
    </section>
  );
}

