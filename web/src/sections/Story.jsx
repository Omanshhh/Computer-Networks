import { LeakTimeline, TwoGates } from '../components/Charts.jsx';
import { Count, Reveal, RevealText } from '../components/Motion.jsx';
import { fmt } from '../lib.js';

export function Problem({ results }) {
  const vodafone = results.incidents.find(i => i.id === 'as55410-2021');
  return (
    <section id="problem">
      <div className="wrap">
        <Reveal className="section-head">
          <h2>Why the 2021 leak got through</h2>
          <p className="lede">
            At {vodafone.firstLeak} UTC on 16 April 2021, Vodafone Idea began announcing {fmt(vodafone.leaked)} address blocks it did not own.
            We replayed all 211 million BGP messages that one public collector recorded that afternoon, and tested every defence against them.
          </p>
        </Reveal>
        <div className="bento">
          <Reveal className="s-8">
            <div className="glass tile hero">
              <div className="tile-head"><h3>The leak, minute by minute</h3><span className="small">RIPE RIS rrc00</span></div>
              <LeakTimeline data={results.timeline2021} />
            </div>
          </Reveal>
          <Reveal className="s-4" delay={0.08}>
            <div className="glass tile">
              <div className="tile-head"><h3>It left through two upstreams</h3></div>
              <TwoGates gates={results.gates2021} />
            </div>
          </Reveal>
          <Reveal className="s-4">
            <div className="glass tile">
              <h3>RPKI covered too little</h3>
              <div className="big num"><Count to={Math.round(vodafone.rovThen)} />%</div>
              <p className="body">of the leaked prefixes had an RPKI record in 2021, so ROV could drop only those. With today's records it would be {Math.round(vodafone.rovNow)}%.</p>
            </div>
          </Reveal>
          <Reveal className="s-4" delay={0.08}>
            <div className="glass tile">
              <h3>Path checks saw nothing wrong</h3>
              <div className="big num"><Count to={vodafone.pathChecks} />%</div>
              <p className="body">stopped by ASPA-style path checks. The route <span className="mono">9498 55410</span> looks like any normal customer route; only the claimed owner was fake.</p>
            </div>
          </Reveal>
          <Reveal className="s-4" delay={0.16}>
            <div className="glass tile">
              <h3>Max-prefix cuts the customer off</h3>
              <div className="big num"><Count to={vodafone.normal} /></div>
              <p className="body">of Vodafone's own routes would go down with the leak, because the limit shuts the whole session.</p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

const STEPS = [
  { q: 'Does RPKI say the route is forged?', a: 'Reject', tone: 'bad', note: 'Standard route origin validation. Rejections also count as evidence of a leak.' },
  { q: 'Does this customer normally announce it?', a: 'Accept', tone: 'ok', note: "Routes from the last 30 days, or ones RPKI authorises for the customer's cone." },
  { q: "Does a network outside the customer's cone own it?", a: 'Accept with an alert', tone: '', note: 'One foreign route can be legitimate: a migration, or a DDoS-protection service.' },
  { q: '25 such routes from 5 owners within 5 minutes?', a: 'Quarantine', tone: 'hold', note: 'Every unexpected route is held back, including the ones alerted just before.' },
];

export function Decide() {
  return (
    <section id="how">
      <div className="wrap">
        <div className="section-head" style={{ maxWidth: 980 }}>
          <h2 style={{ marginBottom: 20 }}>How ConeGuard decides</h2>
          <RevealText>
            Known routes pass. Forged routes are rejected. A sudden flood of other networks' routes is held back, and the customer stays online.
          </RevealText>
        </div>
        <div className="bento">
          {STEPS.map((s, i) => (
            <Reveal key={s.q} className="s-3" delay={i * 0.08}>
              <div className="glass tile step">
                <div className="n">{i + 1}</div>
                <h3>{s.q}</h3>
                <p className="body">{s.note}</p>
                <div className="outcome"><span className={`pill ${s.tone}`}>{s.a}</span></div>
              </div>
            </Reveal>
          ))}
          <Reveal className="s-6">
            <div className="glass tile tone-route">
              <h3>Why quarantine instead of a shutdown</h3>
              <p className="body">
                A max-prefix limit stops a leak by tearing the whole session down, so the customer disappears from the Internet too.
                ConeGuard keeps the session up and holds back only the routes that belong to someone else. Held routes stay in the router,
                unused, so an operator can release them in one step.
              </p>
            </div>
          </Reveal>
          <Reveal className="s-6" delay={0.08}>
            <div className="glass tile">
              <h3>Where it runs</h3>
              <p className="body">
                On the upstream provider's router, once per customer session. It reads the customer's routes before import policy, decides,
                and writes the routes to hold into a prefix list. The decision logic is about 100 lines in <span className="mono">guard/engine.py</span>.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
