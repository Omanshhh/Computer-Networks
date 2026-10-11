import AnimatedContent from '../reactbits/AnimatedContent.jsx';
import CountUp from '../reactbits/CountUp.jsx';
import ScrollReveal from '../reactbits/ScrollReveal.jsx';
import { useReducedMotion } from '../lib.js';

/** A grid cell that rises into place the first time it scrolls into view (React Bits AnimatedContent). */
export function Reveal({ children, className = '', delay = 0 }) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={`reveal ${className}`}>{children}</div>;
  return (
    <AnimatedContent className={`reveal ${className}`} distance={36} duration={0.9} ease="power3.out" delay={delay} threshold={0.12}>
      {children}
    </AnimatedContent>
  );
}

/** A number that counts up when it first appears (React Bits CountUp). */
export function Count({ to, decimals = 0, separator = ',' }) {
  const reduced = useReducedMotion();
  if (reduced) return <>{Number(to).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}</>;
  return <CountUp to={to} duration={1.4} separator={separator} />;
}

/** A sentence whose words sharpen as it scrolls into view (React Bits ScrollReveal). */
export function RevealText({ children }) {
  const reduced = useReducedMotion();
  if (reduced) return <p className="scroll-reveal-text">{children}</p>;
  return (
    <ScrollReveal baseOpacity={0.12} enableBlur baseRotation={2} blurStrength={6}>
      {children}
    </ScrollReveal>
  );
}
