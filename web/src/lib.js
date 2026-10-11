import { useEffect, useState } from 'react';

export const fmt = n => (n == null ? '-' : Number(n).toLocaleString('en-US'));

export function useReducedMotion() {
  const query = '(prefers-reduced-motion: reduce)';
  const [reduced, setReduced] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const onChange = () => setReduced(m.matches);
    m.addEventListener('change', onChange);
    return () => m.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

/** Polls the demo controller (lab/demo.py) once a second. `offline` is true when it cannot be reached. */
export function useLab() {
  const [state, setState] = useState(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const res = await fetch('/api/state', { cache: 'no-store' });
        const s = await res.json();
        if (!alive) return;
        setState(s && s.mode ? s : null);
        setOffline(false);
      } catch {
        if (alive) setOffline(true);
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  return { state, offline };
}

export async function act(path) {
  const res = await fetch(`/api/${path}`, { method: 'POST' });
  if (!res.ok) throw new Error(`The lab did not accept "${path}" (HTTP ${res.status}).`);
}

/** Numbers measured offline (analysis/export_web.py writes public/results.json). */
export function useResults() {
  const [results, setResults] = useState(null);
  useEffect(() => {
    fetch('/results.json')
      .then(r => r.json())
      .then(setResults)
      .catch(() => setResults(null));
  }, []);
  return results;
}
