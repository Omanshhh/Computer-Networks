import { useRef, useState } from 'react';
import { fmt } from '../lib.js';

const pct = v => (v == null ? '-' : `${Number(v).toFixed(v % 1 ? 1 : 0)}%`);

/** Tracks which data index the pointer is over in an SVG chart drawn in a fixed viewBox. */
function useHoverIndex(count, width, padL, padR) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null);
  const onMove = e => {
    const rect = ref.current.getBoundingClientRect();
    const fx = (e.clientX - rect.left) / rect.width;
    const x = fx * width;
    const i = Math.round(((x - padL) / (width - padL - padR)) * (count - 1));
    setHover({ i: Math.max(0, Math.min(count - 1, i)), left: e.clientX - rect.left, top: e.clientY - rect.top });
  };
  return { ref, hover, onMove, onLeave: () => setHover(null) };
}

function LineChart({ data, series, width = 640, height = 220, xKey, yMax, yLabel, tip }) {
  const padL = 46, padR = 12, padT = 12, padB = 28;
  const n = data.length;
  const max = yMax ?? Math.max(10, ...data.flatMap(d => series.map(s => d[s.key])));
  const X = i => padL + (n <= 1 ? 0 : (i / (n - 1)) * (width - padL - padR));
  const Y = v => padT + (1 - v / max) * (height - padT - padB);
  const { ref, hover, onMove, onLeave } = useHoverIndex(n, width, padL, padR);
  const ticks = [0, 0.5, 1].map(f => Math.round(max * f));
  const xTicks = n > 1 ? [0, Math.floor((n - 1) / 2), n - 1] : [0];
  return (
    <div className="chart" ref={ref} onPointerMove={n ? onMove : undefined} onPointerLeave={onLeave}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={yLabel}>
        {ticks.map(t => (
          <g key={t}>
            <line x1={padL} x2={width - padR} y1={Y(t)} y2={Y(t)} stroke="var(--grid)" />
            <text x={padL - 8} y={Y(t) + 4} textAnchor="end" fontSize="11" fill="var(--ink-3)">{fmt(t)}</text>
          </g>
        ))}
        {xTicks.map(i => data[i] && (
          <text key={i} x={X(i)} y={height - 8} textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} fontSize="11" fill="var(--ink-3)">
            {data[i][xKey]}
          </text>
        ))}
        {series.map(s => (
          <path key={s.key} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round"
            d={data.map((d, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(d[s.key]).toFixed(1)}`).join(' ')} />
        ))}
        {hover && data[hover.i] && (
          <g>
            <line x1={X(hover.i)} x2={X(hover.i)} y1={padT} y2={height - padB} stroke="var(--ink-3)" strokeWidth="1" />
            {series.map(s => (
              <circle key={s.key} cx={X(hover.i)} cy={Y(data[hover.i][s.key])} r="5" fill={s.color} stroke="#fff" strokeWidth="2" />
            ))}
          </g>
        )}
      </svg>
      {hover && data[hover.i] && (
        <div className="tip" style={{ left: hover.left, top: hover.top }}>{tip(data[hover.i])}</div>
      )}
      <div className="legend">
        {series.map(s => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}
      </div>
    </div>
  );
}

/** The live demo: leaked routes Vodafone announces, and what Airtel actually accepts. */
export function LiveRoutes({ history }) {
  const data = history.map(h => ({ ...h, label: new Date(h.t * 1000).toLocaleTimeString('en-GB') }));
  if (!data.length) return <p className="small">The chart starts when the lab reports its first reading.</p>;
  return (
    <LineChart data={data} xKey="label" height={200} yLabel="Routes over time"
      series={[
        { key: 'injected', label: 'leaked routes Vodafone announces', color: 'var(--leak)' },
        { key: 'accepted', label: 'routes Airtel accepts from Vodafone', color: 'var(--route)' },
      ]}
      tip={d => (<><b>{d.label}</b>{fmt(d.injected)} announced<br />{fmt(d.accepted)} accepted by Airtel</>)} />
  );
}

/** The real 2021 leak as RIPE RIS rrc00 saw it. */
export function LeakTimeline({ data }) {
  return (
    <LineChart data={data} xKey="t" yMax={36000} yLabel="The 2021 leak over time"
      series={[
        { key: 'seen', label: 'distinct leaked prefixes seen', color: 'var(--seen)' },
        { key: 'active', label: 'still routed to Vodafone by at least one network', color: 'var(--route)' },
      ]}
      tip={d => (<><b>{d.t} UTC</b>{fmt(d.seen)} leaked so far<br />{fmt(d.active)} still routed to AS55410</>)} />
  );
}

const DEFENCES = [
  { key: 'rovThen', label: 'ROV, RPKI of the day' },
  { key: 'rovNow', label: 'ROV, RPKI today' },
  { key: 'pathChecks', label: 'Path checks (ASPA, RFC 9234)' },
  { key: 'maxPrefix2x', label: 'Max-prefix at 2x normal', cuts: true },
  { key: 'maxPrefix10x', label: 'Max-prefix at 10x normal', cuts: true },
  { key: 'coneguard', label: 'ConeGuard', main: true },
];

/** Share of each incident's leak that every defence stops; switch incidents with the buttons. */
export function DefenceBars({ incidents }) {
  const [id, setId] = useState(incidents[0].id);
  const [hover, setHover] = useState(null);
  const inc = incidents.find(i => i.id === id);
  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="seg" role="group" aria-label="Choose an incident">
        {incidents.map(i => (
          <button key={i.id} aria-pressed={i.id === id} onClick={() => setId(i.id)}>{i.name} {i.year}</button>
        ))}
      </div>
      <p className="small" style={{ margin: 0 }}>
        AS{inc.asn} leaked <b className="num">{fmt(inc.leaked)}</b> prefixes ({inc.kind === 'path-preserving' ? 'path-preserving leak, real owners kept in the path' : 're-originated as its own'}), first seen at {inc.firstLeak} UTC.
      </p>
      <div className="bars" role="list">
        {DEFENCES.map(d => {
          const v = inc[d.key];
          return (
            <div key={d.key} role="listitem" className="bar-row" onPointerEnter={() => setHover(d.key)} onPointerLeave={() => setHover(null)}>
              <span className="bar-label">{d.label}</span>
              <span className="bar-track">
                <i style={{ width: `${v ?? 0}%`, background: d.main ? 'var(--route)' : 'var(--quiet)' }} />
              </span>
              <span className="bar-value num">{v == null ? 'no archive' : pct(v)}</span>
              {hover === d.key && (
                <span className="tip" style={{ left: '62%', top: 0 }}>
                  <b>{d.label}</b>
                  {v == null ? 'No archived RPKI data for that day.' : `Stops ${pct(v)} of the leaked prefixes.`}
                  {d.cuts && <><br />Also disconnects all {fmt(inc.normal)} of the customer's own routes.</>}
                  {d.main && inc.triggerSeconds != null && <><br />Detects the leak {inc.triggerSeconds} s after it starts.</>}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <p className="small" style={{ margin: 0 }}>Max-prefix limits stop leaks by shutting the whole session, so the customer's own routes go down too. ConeGuard never does.</p>
    </div>
  );
}

/** ROV coverage of each leak with the RPKI of the day and of today. */
export function RovDumbbell({ incidents }) {
  const width = 560, rowH = 40, padL = 150, padR = 40, padT = 8;
  const height = padT + incidents.length * rowH + 30;
  const X = v => padL + (v / 100) * (width - padL - padR);
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Share of each leak that ROV would drop, then and today">
        {[0, 50, 100].map(t => (
          <g key={t}>
            <line x1={X(t)} x2={X(t)} y1={padT} y2={height - 26} stroke="var(--grid)" />
            <text x={X(t)} y={height - 8} textAnchor="middle" fontSize="11" fill="var(--ink-3)">{t}%</text>
          </g>
        ))}
        {incidents.map((inc, i) => {
          const y = padT + i * rowH + rowH / 2;
          return (
            <g key={inc.id}>
              <text x={padL - 12} y={y + 4} textAnchor="end" fontSize="12.5" fill="var(--ink)">{inc.name} {inc.year}</text>
              {inc.rovThen != null && <line x1={X(inc.rovThen)} x2={X(inc.rovNow)} y1={y} y2={y} stroke="var(--quiet)" strokeWidth="3" />}
              {inc.rovThen != null ? (
                <g>
                  <circle cx={X(inc.rovThen)} cy={y} r="7" fill="var(--seen)" stroke="#fff" strokeWidth="2"><title>{`${inc.name}: ${inc.rovThen}% with the RPKI of the day`}</title></circle>
                  <text x={X(inc.rovThen)} y={y - 12} textAnchor="middle" fontSize="11" fill="var(--ink-2)">{inc.rovThen.toFixed(1)}%</text>
                </g>
              ) : (
                <text x={X(0) + 4} y={y + 4} fontSize="11" fill="var(--ink-3)">no archive then</text>
              )}
              <rect x={X(inc.rovNow) - 7} y={y - 7} width="14" height="14" rx="3" fill="var(--route)" stroke="#fff" strokeWidth="2" transform={`rotate(45 ${X(inc.rovNow)} ${y})`}>
                <title>{`${inc.name}: ${inc.rovNow}% with today's RPKI`}</title>
              </rect>
              <text x={X(inc.rovNow)} y={y - 12} textAnchor="middle" fontSize="11" fill="var(--ink-2)">{inc.rovNow.toFixed(1)}%</text>
            </g>
          );
        })}
      </svg>
      <div className="legend">
        <span><i style={{ background: 'var(--seen)' }} />RPKI on the day of the incident</span>
        <span><i style={{ background: 'var(--route)' }} />RPKI today</span>
      </div>
    </div>
  );
}

/** False alarms on 41 normal days, on a log scale. */
export function FalseAlarmBars({ fa }) {
  const cg = (n, k) => fa.coneguard.find(c => c.n === n && c.k === k)?.perYear;
  const rows = [
    { label: 'Strict prefix filter', note: 'rejects legitimate new routes', v: fa.strictFilter },
    { label: 'Max-prefix at 2x', note: 'tears the session down', v: fa.maxPrefix2x },
    { label: 'ConeGuard, 25 from 5 owners', note: 'holds back new foreign routes', v: cg(25, 5), main: true },
    { label: 'ConeGuard, 50 from 5 owners', note: 'holds back new foreign routes', v: cg(50, 5), main: true },
  ];
  const lo = Math.log10(5e-4), hi = Math.log10(10);
  const w = v => Math.max(2, ((Math.log10(v) - lo) / (hi - lo)) * 100);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="bars" role="list">
        {rows.map(r => (
          <div key={r.label} role="listitem" className="bar-row" title={`${r.label}: ${r.v} days with a false alarm per session-year (${r.note})`}>
            <span className="bar-label">{r.label}<span className="small" style={{ display: 'block' }}>{r.note}</span></span>
            <span className="bar-track"><i style={{ width: `${w(r.v)}%`, background: r.main ? 'var(--route)' : 'var(--quiet)' }} /></span>
            <span className="bar-value num">{Number(r.v.toPrecision(3))}</span>
          </div>
        ))}
      </div>
      <p className="small" style={{ margin: 0 }}>Days with a false alarm per customer session per year, log scale. {fmt(fa.sessions)} sessions x {fa.days} normal days in 2026.</p>
    </div>
  );
}

/** Internet-wide simulation (BGPy): how far the leak reaches as more networks deploy each defence. */
export function SimLines({ sim }) {
  const [roa, setRoa] = useState('withoutRoa');
  const names = { ROV: 'ROV', ASPA: 'ASPA', OnlyToCustomers: 'RFC 9234', 'Peerlock Lite': 'Peerlock-lite', ConeGuard: 'ConeGuard', 'ConeGuard + peers': 'ConeGuard + peers' };
  const series = sim[roa];
  const baseline = Math.max(...Object.values(series).flatMap(s => s.value));
  const groups = [];
  Object.keys(names).forEach(p => {
    if (!series[p]) return;
    const key = series[p].value.join();
    const g = groups.find(x => x.key === key);
    if (g) g.members.push(p); else groups.push({ key, members: [p], ...series[p] });
  });
  groups.forEach(g => {
    g.noEffect = g.value.every(v => Math.abs(v - baseline) < 0.05);
    g.color = g.noEffect ? 'var(--quiet)' : g.members.length === 1 && g.members[0] === 'ConeGuard' ? 'var(--route)'
      : g.members.length === 1 && g.members[0] === 'ConeGuard + peers' ? 'var(--seen)' : 'var(--ok)';
    g.label = g.members.map(m => names[m]).join(', ') + (g.noEffect ? ' (no effect)' : '');
  });
  const width = 640, height = 260, padL = 46, padR = 16, padT = 14, padB = 30;
  const X = a => padL + (a / 100) * (width - padL - padR);
  const Y = v => padT + (1 - v / 90) * (height - padT - padB);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="seg" role="group" aria-label="Victim type">
        <button aria-pressed={roa === 'withoutRoa'} onClick={() => setRoa('withoutRoa')}>Victim without RPKI (77% of 2021)</button>
        <button aria-pressed={roa === 'withRoa'} onClick={() => setRoa('withRoa')}>Victim with RPKI</button>
      </div>
      <div className="chart">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Share of networks whose traffic reaches the leaker, by deployment">
          {[0, 30, 60, 90].map(t => (
            <g key={t}>
              <line x1={padL} x2={width - padR} y1={Y(t)} y2={Y(t)} stroke="var(--grid)" />
              <text x={padL - 8} y={Y(t) + 4} textAnchor="end" fontSize="11" fill="var(--ink-3)">{t}%</text>
            </g>
          ))}
          {sim.adoption.map(a => (
            <text key={a} x={X(a)} y={height - 8} textAnchor="middle" fontSize="11" fill="var(--ink-3)">{a}% deploy</text>
          ))}
          {groups.map(g => (
            <g key={g.key}>
              <path fill="none" stroke={g.color} strokeWidth="3" d={g.value.map((v, i) => `${i ? 'L' : 'M'}${X(sim.adoption[i])} ${Y(v)}`).join(' ')} />
              {g.value.map((v, i) => (
                <g key={i}>
                  <line x1={X(sim.adoption[i])} x2={X(sim.adoption[i])} y1={Y(Math.min(90, v + g.err[i]))} y2={Y(Math.max(0, v - g.err[i]))} stroke={g.color} strokeWidth="1" opacity="0.6" />
                  <circle cx={X(sim.adoption[i])} cy={Y(v)} r="6" fill={g.color} stroke="#fff" strokeWidth="2">
                    <title>{`${g.label}: ${v}% of networks reach the leaker at ${sim.adoption[i]}% deployment`}</title>
                  </circle>
                </g>
              ))}
            </g>
          ))}
        </svg>
        <div className="legend">
          {groups.map(g => <span key={g.key}><i style={{ background: g.color }} />{g.label}</span>)}
        </div>
      </div>
    </div>
  );
}

/** Where the 2021 leak left Vodafone: two upstreams, not one. */
export function TwoGates({ gates }) {
  const share = v => `${(v / gates.total) * 100}%`;
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="bar-row stacked">
        <span className="bar-label">via Airtel, AS9498</span>
        <span className="bar-track"><i style={{ width: share(gates.airtel), background: 'var(--leak)' }} /></span>
        <span className="bar-value num">{fmt(gates.airtel)}</span>
      </div>
      <div className="bar-row stacked">
        <span className="bar-label">via Vodafone Global, AS1273</span>
        <span className="bar-track"><i style={{ width: share(gates.vodafoneGlobal), background: 'var(--leak)', opacity: 0.7 }} /></span>
        <span className="bar-value num">{fmt(gates.vodafoneGlobal)}</span>
      </div>
      <p className="body">{fmt(gates.onlyVodafoneGlobal)} leaked prefixes never touched Airtel, so a filter at Airtel alone would not have contained the incident.</p>
    </div>
  );
}
