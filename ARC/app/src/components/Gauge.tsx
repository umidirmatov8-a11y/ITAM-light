/** Analog 240° dial with a needle; value in percent or null (N/A). */
export function Gauge({ label, value, detail }: { label: string; value: number | null; detail?: string }) {
  const v = value === null ? 0 : Math.max(0, Math.min(100, value));
  const start = -210;
  const sweep = 240;
  const angle = start + (v / 100) * sweep;
  const rad = (deg: number) => (deg * Math.PI) / 180;
  const arc = (r: number, from: number, to: number) => {
    const x1 = 50 + r * Math.cos(rad(from));
    const y1 = 50 + r * Math.sin(rad(from));
    const x2 = 50 + r * Math.cos(rad(to));
    const y2 = 50 + r * Math.sin(rad(to));
    return `M ${x1} ${y1} A ${r} ${r} 0 ${to - from > 180 ? 1 : 0} 1 ${x2} ${y2}`;
  };
  const level = v >= 90 ? "danger" : v >= 75 ? "warn" : "ok";
  return (
    <div className={`gauge gauge--${value === null ? "na" : level}`} role="meter" aria-label={label}
         aria-valuenow={value ?? undefined} aria-valuemin={0} aria-valuemax={100}>
      <svg viewBox="0 0 100 78">
        <path d={arc(38, start, start + sweep)} className="gauge__track" />
        {value !== null && <path d={arc(38, start, angle)} className="gauge__value" />}
        {Array.from({ length: 11 }, (_, i) => {
          const a = rad(start + (i / 10) * sweep);
          return <line key={i} x1={50 + 31 * Math.cos(a)} y1={50 + 31 * Math.sin(a)} x2={50 + 34 * Math.cos(a)}
                       y2={50 + 34 * Math.sin(a)} className="gauge__tick" />;
        })}
        <line x1="50" y1="50" x2={50 + 28 * Math.cos(rad(angle))} y2={50 + 28 * Math.sin(rad(angle))}
              className="gauge__needle" />
        <circle cx="50" cy="50" r="3" className="gauge__pivot" />
        <text x="50" y="72" textAnchor="middle" className="gauge__value-text">
          {value === null ? "N/A" : `${Math.round(v)}%`}
        </text>
      </svg>
      <div className="gauge__label mono-label">{label}</div>
      {detail && <div className="gauge__detail faint">{detail}</div>}
    </div>
  );
}
