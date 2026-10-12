/**
 * The central A.R.C. emblem: concentric instrument rings with a rotating sweep.
 * Its state is driven by real data (busy request, emergency stop, backend availability, mode).
 */
export type CoreState = "idle" | "busy" | "alert" | "offline" | "attention";

const TICKS = Array.from({ length: 72 }, (_, i) => i);

export function ArcCore({ state, mode, label }: { state: CoreState; mode: "LOCAL" | "ONLINE"; label: string }) {
  return (
    <div className={`core core--${state}`} data-testid="arc-core" data-state={state}>
      <svg viewBox="0 0 300 300" role="img" aria-label={`A.R.C.: ${label}`}>
        <defs>
          <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--core-color)" stopOpacity="0.35" />
            <stop offset="60%" stopColor="var(--core-color)" stopOpacity="0.06" />
            <stop offset="100%" stopColor="var(--core-color)" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle cx="150" cy="150" r="146" fill="url(#coreGlow)" />
        {/* outer dial with ticks */}
        <circle cx="150" cy="150" r="138" className="core__ring" />
        <g className="core__ticks">
          {TICKS.map((i) => {
            const long = i % 6 === 0;
            const a = (i / TICKS.length) * Math.PI * 2;
            const r1 = long ? 124 : 129;
            return (
              <line key={i} x1={150 + Math.cos(a) * r1} y1={150 + Math.sin(a) * r1} x2={150 + Math.cos(a) * 134}
                    y2={150 + Math.sin(a) * 134} className={long ? "core__tick core__tick--long" : "core__tick"} />
            );
          })}
        </g>
        {/* rotating segmented ring */}
        <g className="core__spin">
          <circle cx="150" cy="150" r="112" className="core__segments" />
        </g>
        <g className="core__spin core__spin--reverse">
          <circle cx="150" cy="150" r="98" className="core__dash" />
        </g>
        {/* sweep */}
        <g className="core__sweep">
          <path d="M150 150 L150 62 A88 88 0 0 1 212 88 Z" className="core__sweep-fill" />
        </g>
        <circle cx="150" cy="150" r="86" className="core__ring core__ring--inner" />
        <circle cx="150" cy="150" r="58" className="core__hub" />
        <text x="150" y="146" textAnchor="middle" className="core__title">A.R.C.</text>
        <text x="150" y="168" textAnchor="middle" className="core__sub">{label}</text>
        <text x="150" y="232" textAnchor="middle" className="core__mode">{mode}</text>
      </svg>
    </div>
  );
}
