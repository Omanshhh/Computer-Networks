import { useReducedMotion, fmt } from '../lib.js';

// Positions in the map's 700 x 420 coordinate space.
const N = {
  vweb: { x: 82, y: 52 },
  vodafone: { x: 200, y: 118 },
  airtel: { x: 360, y: 222 },
  google: { x: 548, y: 104 },
  gweb: { x: 632, y: 40 },
  fastly: { x: 548, y: 340 },
  fweb: { x: 632, y: 398 },
  userisp: { x: 200, y: 330 },
  user: { x: 82, y: 392 },
};

const LINKS = [
  ['vweb', 'vodafone'], ['vodafone', 'airtel'], ['airtel', 'google'], ['google', 'gweb'],
  ['airtel', 'fastly'], ['fastly', 'fweb'], ['airtel', 'userisp'], ['userisp', 'user'],
];

const path = nodes => nodes.map((n, i) => `${i ? 'L' : 'M'}${N[n].x} ${N[n].y}`).join(' ');
const mid = (a, b) => ({ x: (N[a].x + N[b].x) / 2, y: (N[a].y + N[b].y) / 2 });

const COLORS = { ok: 'var(--ok)', leak: 'var(--leak)', idle: 'var(--quiet)' };

function flowFor(site, state, offline) {
  if (offline || !state) return { kind: 'idle', nodes: ['user', 'userisp', 'airtel'] };
  const up = state.session === 'Established';
  const leaking = state.injected > 0;
  if (site === 'Vodafone') {
    return state.reach?.Vodafone
      ? { kind: 'ok', nodes: ['user', 'userisp', 'airtel', 'vodafone', 'vweb'] }
      : { kind: 'leak', nodes: ['user', 'userisp', 'airtel'], blocked: true };
  }
  const dest = site === 'Google' ? ['google', 'gweb'] : ['fastly', 'fweb'];
  if (state.reach?.[site]) return { kind: 'ok', nodes: ['user', 'userisp', 'airtel', ...dest] };
  if (up && leaking) return { kind: 'leak', nodes: ['user', 'userisp', 'airtel', 'vodafone'], sink: true };
  return { kind: 'leak', nodes: ['user', 'userisp', 'airtel'] };
}

function Packets({ d, color, reduced, offset }) {
  if (reduced) return null;
  return [0, 1, 2].map(i => (
    <circle key={i} r="5" fill={color} stroke="#fff" strokeWidth="1.5">
      <animateMotion dur="2.7s" begin={`${offset + i * 0.9}s`} repeatCount="indefinite" path={d} />
    </circle>
  ));
}

function Node({ id, name, asn, wide = 128, emphasis }) {
  const { x, y } = N[id];
  return (
    <g>
      <rect x={x - wide / 2} y={y - 25} width={wide} height="50" rx="14" fill="rgba(255,255,255,0.92)"
        stroke={emphasis || 'rgba(20,32,41,0.22)'} strokeWidth={emphasis ? 2.5 : 1.2} />
      <text x={x} y={y - 3} textAnchor="middle" fontSize="14" fontWeight="650" fill="var(--ink)">{name}</text>
      <text x={x} y={y + 14} textAnchor="middle" fontSize="11.5" fill="var(--ink-3)" fontFamily="var(--mono)">{asn}</text>
    </g>
  );
}

function Host({ id, label, ip }) {
  const { x, y } = N[id];
  return (
    <g>
      <rect x={x - 62} y={y - 17} width="124" height="34" rx="17" fill="rgba(255,255,255,0.75)" stroke="rgba(20,32,41,0.18)" strokeDasharray="3 3" />
      <text x={x} y={y - 1} textAnchor="middle" fontSize="11.5" fontWeight="600" fill="var(--ink-2)">{label}</text>
      <text x={x} y={y + 11} textAnchor="middle" fontSize="10" fill="var(--ink-3)" fontFamily="var(--mono)">{ip}</text>
    </g>
  );
}

export default function NetworkMap({ state, offline }) {
  const reduced = useReducedMotion();
  const flows = ['Google', 'Fastly', 'Vodafone'].map(site => ({ site, ...flowFor(site, state, offline) }));
  const up = state?.session === 'Established';
  const leaking = up && state?.injected > 0;
  const torn = state && !offline && state.mode === 'maxprefix' && !up;
  const quarantining = state?.mode === 'coneguard' && state?.burst;
  const modeName = { none: 'no protection', rov: 'ROV', maxprefix: 'max-prefix limit', coneguard: 'ConeGuard on' }[state?.mode] || 'lab offline';
  const sinking = flows.some(f => f.sink);
  const va = mid('vodafone', 'airtel');

  return (
    <div className="map">
      <svg viewBox="0 0 700 430" role="img"
        aria-label={`Network map. User traffic: ${flows.map(f => `${f.site} ${f.kind === 'ok' ? 'reachable' : 'lost'}`).join(', ')}.`}>
        <defs>
          <marker id="arrow-leak" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0L10 5L0 10z" fill="var(--leak)" />
          </marker>
        </defs>

        {LINKS.map(([a, b]) => {
          const isVA = (a === 'vodafone' && b === 'airtel');
          return (
            <line key={a + b} x1={N[a].x} y1={N[a].y} x2={N[b].x} y2={N[b].y}
              stroke={isVA && torn ? 'var(--quiet)' : 'rgba(20,32,41,0.28)'} strokeWidth="2"
              strokeDasharray={isVA && torn ? '6 6' : undefined} />
          );
        })}

        <text x={va.x - 112} y={va.y + 2} fontSize="11" fill="var(--ink-3)">customer of Airtel</text>
        <text x={mid('userisp', 'airtel').x - 16} y={mid('userisp', 'airtel').y - 10} textAnchor="end" fontSize="11" fill="var(--ink-3)">customer of Airtel</text>
        <text x={mid('airtel', 'google').x + 6} y={mid('airtel', 'google').y + 16} fontSize="11" fill="var(--ink-3)">peer</text>
        <text x={mid('airtel', 'fastly').x + 8} y={mid('airtel', 'fastly').y - 8} fontSize="11" fill="var(--ink-3)">peer</text>

        {leaking && (
          <g>
            <path d={path(['vodafone', 'airtel'])} stroke="var(--leak)" strokeWidth="4" fill="none"
              strokeDasharray="8 8" className="announce" markerEnd="url(#arrow-leak)" opacity="0.85" />
            <text x={va.x + 14} y={va.y - 12} fontSize="12" fontWeight="650" fill="var(--leak-ink)">
              announces {fmt(state.injected)} prefixes it doesn't own
            </text>
          </g>
        )}
        {torn && (
          <text x={va.x + 14} y={va.y - 12} fontSize="12" fontWeight="650" fill="var(--leak-ink)">session torn down</text>
        )}

        {flows.map((f, i) => (
          <g key={f.site}>
            <path d={path(f.nodes)} fill="none" stroke={COLORS[f.kind]} strokeWidth="1.5" opacity="0.5" />
            {f.kind !== 'idle' && <Packets d={path(f.nodes)} color={COLORS[f.kind]} reduced={reduced} offset={i * 0.3} />}
          </g>
        ))}

        {sinking && (
          <g>
            {!reduced && <circle cx={N.vodafone.x} cy={N.vodafone.y} r="10" fill="var(--leak)" className="sink" />}
            <text x={N.vodafone.x + 70} y={N.vodafone.y - 32} fontSize="12" fontWeight="650" fill="var(--leak-ink)">user traffic dropped here</text>
          </g>
        )}
        {flows.find(f => f.blocked) && (
          <g transform={`translate(${(N.airtel.x + va.x) / 2} ${(N.airtel.y + va.y) / 2})`}>
            <circle r="11" fill="var(--leak)" />
            <path d="M-4 -4L4 4M4 -4L-4 4" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
          </g>
        )}

        {quarantining && (
          <rect x={N.airtel.x - 92} y={N.airtel.y - 38} width="184" height="98" rx="22"
            fill="rgba(255, 244, 214, 0.95)" stroke="var(--hold)" strokeWidth="2.5" />
        )}

        <Host id="vweb" label="Vodafone site" ip="118.185.0.10" />
        <Host id="gweb" label="Google site" ip="172.217.179.10" />
        <Host id="fweb" label="Fastly site" ip="167.82.163.10" />
        <Host id="user" label="User" ip="100.64.0.10" />
        <Node id="vodafone" name="Vodafone Idea" asn="AS55410" wide={140} emphasis={leaking ? 'var(--leak)' : undefined} />
        <Node id="google" name="Google" asn="AS15169" />
        <Node id="fastly" name="Fastly" asn="AS54113" />
        <Node id="userisp" name="User's ISP" asn="AS64600" />
        <Node id="airtel" name="Airtel" asn="AS9498" wide={140}
          emphasis={state?.mode === 'coneguard' ? 'var(--route)' : undefined} />
        <text x={N.airtel.x} y={N.airtel.y + 44} textAnchor="middle" fontSize="12" fontWeight="650"
          fill={quarantining ? 'var(--hold-ink)' : state?.mode === 'coneguard' ? 'var(--route-ink)' : 'var(--ink-3)'}>
          {quarantining ? `quarantining ${fmt(state.counts?.quarantine)} routes` : modeName}
        </text>
      </svg>
      <div className="legend">
        <span><i style={{ background: 'var(--ok)' }} />user traffic that arrives</span>
        <span><i style={{ background: 'var(--leak)' }} />user traffic lost to the leak</span>
        <span><i style={{ background: 'var(--hold)' }} />routes ConeGuard holds back</span>
      </div>
    </div>
  );
}
