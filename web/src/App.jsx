import { useEffect, useMemo } from 'react';
import Lenis from 'lenis';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Live from './sections/Live.jsx';
import { Decide, Problem } from './sections/Story.jsx';
import Results from './sections/Results.jsx';
import { Build, Papers } from './sections/Build.jsx';
import { useLab, useReducedMotion, useResults } from './lib.js';

gsap.registerPlugin(ScrollTrigger);

const LINKS = [
  ['#live', 'Live demo'], ['#problem', 'The problem'], ['#how', 'How it decides'],
  ['#results', 'Results'], ['#build', "How it's built"], ['#paper', 'Paper'],
];

let lenis = null;

/** A faint, fixed mesh of autonomous systems behind the glass. Seeded, so it looks the same every load. */
function Backdrop() {
  const { nodes, links } = useMemo(() => {
    let seed = 55410;
    const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const nodes = Array.from({ length: 90 }, () => ({ x: rand() * 1600, y: rand() * 1000 }));
    const links = [];
    nodes.forEach((a, i) => {
      nodes
        .map((b, j) => ({ j, d: (a.x - b.x) ** 2 + (a.y - b.y) ** 2 }))
        .filter(o => o.j !== i)
        .sort((p, q) => p.d - q.d)
        .slice(0, 2)
        .forEach(o => links.push([a, nodes[o.j]]));
    });
    return { nodes, links };
  }, []);
  return (
    <div className="backdrop" aria-hidden="true">
      <svg viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice">
        {links.map(([a, b], i) => <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="rgba(20,32,41,0.07)" strokeWidth="1.2" />)}
        {nodes.map((n, i) => <circle key={i} cx={n.x} cy={n.y} r="3" fill="rgba(20,32,41,0.16)" />)}
      </svg>
    </div>
  );
}

function Nav() {
  const go = e => {
    const href = e.currentTarget.getAttribute('href');
    if (!href.startsWith('#') || !lenis) return;
    e.preventDefault();
    lenis.scrollTo(href, { offset: -84 });
  };
  return (
    <nav className="nav" aria-label="Sections">
      <div className="wrap">
        <div className="glass bar">
          <a className="brand" href="#live" onClick={go}>
            <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
              <circle cx="16" cy="16" r="13" fill="none" stroke="var(--route)" strokeWidth="4" />
              <circle cx="16" cy="16" r="5" fill="var(--route)" />
            </svg>
            ConeGuard
          </a>
          {LINKS.map(([href, label]) => <a key={href} className="link" href={href} onClick={go}>{label}</a>)}
          <a className="link cta" href="https://github.com/Omanshhh/Computer-Networks" target="_blank" rel="noreferrer">GitHub</a>
        </div>
      </div>
    </nav>
  );
}

export default function App() {
  const lab = useLab();
  const results = useResults();
  const reduced = useReducedMotion();

  // Smooth scrolling (Lenis) driving GSAP's ScrollTrigger, which the React Bits animations use.
  useEffect(() => {
    if (reduced) return undefined;
    lenis = new Lenis({ lerp: 0.1 });
    lenis.on('scroll', ScrollTrigger.update);
    const raf = time => lenis.raf(time * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(raf);
      lenis.destroy();
      lenis = null;
    };
  }, [reduced]);

  // Sections below the demo load their numbers after first paint; recompute trigger positions then.
  useEffect(() => {
    if (results) requestAnimationFrame(() => ScrollTrigger.refresh());
  }, [results]);

  return (
    <>
      <Backdrop />
      <Nav />
      <main>
        <Live lab={lab} />
        {results ? (
          <>
            <Problem results={results} />
            <Decide />
            <Results results={results} />
            <Build results={results} />
            <Papers />
          </>
        ) : (
          <div className="wrap"><p className="small">Loading the measured results...</p></div>
        )}
      </main>
      <footer>
        <div className="wrap">
          <p style={{ margin: 0 }}>
            ConeGuard is a Computer Networks project by Sara Agrawal (24BAI0051), Omansh Sharma (24BAI0080) and Aakash Prathap (24BAI0082),
            guided by Thamizharasan S, School of Computer Science and Engineering (SCOPE), VIT Vellore.
          </p>
          <p style={{ margin: '8px 0 0' }}>
            Routing data from the RIPE NCC, CAIDA and RouteViews. Scroll animations from React Bits.
          </p>
        </div>
      </footer>
    </>
  );
}
