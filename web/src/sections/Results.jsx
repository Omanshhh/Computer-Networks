import { DefenceBars, FalseAlarmBars, RovDumbbell, SimLines } from '../components/Charts.jsx';
import { Count, Reveal } from '../components/Motion.jsx';
import { fmt } from '../lib.js';

export default function Results({ results }) {
  const reorigination = results.incidents;
  const contained = reorigination.map(i => i.coneguard);
  const triggers = reorigination.map(i => i.triggerSeconds).filter(v => v != null);
  const fa = results.falseAlarms;
  const atDefault = fa.coneguard.find(c => c.n === 25 && c.k === 5).perYear;
  const sim = results.simulation.withoutRoa;
  const baseline = Math.max(...Object.values(sim).flatMap(s => s.value));
  return (
    <section id="results">
      <div className="wrap">
        <Reveal className="section-head">
          <h2>What we measured</h2>
          <p className="lede">
            Five real leaks from 2010 to 2021, replayed from recorded BGP data. One of them, Verizon/DQE, kept the real owners in the path,
            so it shows what path checks are good at.
          </p>
        </Reveal>
        <div className="bento">
          <Reveal className="s-8 r-3">
            <div className="glass tile hero">
              <div className="tile-head"><h3>How much of each leak every defence stops</h3></div>
              <DefenceBars incidents={results.incidents} />
            </div>
          </Reveal>
          <Reveal className="s-4" delay={0.08}>
            <div className="glass tile tone-route">
              <div className="big num"><Count to={Math.min(...contained)} />&ndash;<Count to={Math.max(...contained)} />%</div>
              <p className="body">of each leak contained by ConeGuard, with the customer's own routes untouched.</p>
            </div>
          </Reveal>
          <Reveal className="s-4" delay={0.14}>
            <div className="glass tile">
              <div className="big num"><Count to={Math.max(...triggers)} /> s</div>
              <p className="body">at most, from the first leaked route to burst detection. For Vodafone Idea it took {reorigination[0].triggerSeconds} second.</p>
            </div>
          </Reveal>
          <Reveal className="s-4" delay={0.2}>
            <div className="glass tile">
              <div className="big num"><Count to={Math.round(atDefault * 1000) / 1000} /></div>
              <p className="body">false alarms per customer link per year, across {fmt(fa.sessions)} real links and {fa.days} normal days.</p>
            </div>
          </Reveal>

          <Reveal className="s-6">
            <div className="glass tile">
              <div className="tile-head"><h3>RPKI coverage, then and today</h3></div>
              <RovDumbbell incidents={results.incidents} />
            </div>
          </Reveal>
          <Reveal className="s-6" delay={0.08}>
            <div className="glass tile">
              <div className="tile-head"><h3>False alarms on normal days</h3></div>
              <FalseAlarmBars fa={fa} />
            </div>
          </Reveal>

          <Reveal className="s-8">
            <div className="glass tile">
              <div className="tile-head"><h3>Across the whole Internet (BGPy simulation)</h3></div>
              <SimLines sim={results.simulation} />
            </div>
          </Reveal>
          <Reveal className="s-4" delay={0.08}>
            <div className="glass tile tone-route">
              <h3>The only defence for unsigned victims</h3>
              <p className="body">
                When the victim has no RPKI record, ROV, ASPA, RFC 9234 and Peerlock-lite change nothing. With ConeGuard on 99% of
                networks, the leaker's reach falls from {baseline}% to {sim.ConeGuard.value.at(-1)}% of networks,
                and to {sim['ConeGuard + peers'].value.at(-1)}% when peer sessions are checked too.
              </p>
              <p className="small">Each point averages 20 simulated leaks on CAIDA's 2026 topology. Bars show the spread between trials.</p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
