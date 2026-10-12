/** Hand skeleton drawn from the 21 landmarks the backend reports (no camera image needed). */
const CONNECTIONS: Array<[number, number]> = [
  [0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17],
];

export function HandView({ landmarks, zone, size = 160 }: { landmarks: number[][] | null; zone?: number[]; size?: number }) {
  const h = (size * 3) / 4;
  return (
    <svg className="hand-view" viewBox={`0 0 ${size} ${h}`} width="100%" role="img"
         aria-label={landmarks ? "Рука в кадре" : "Рука не обнаружена"}>
      <rect x="0.5" y="0.5" width={size - 1} height={h - 1} className="hand-view__frame" />
      {zone && zone.length === 4 && (
        <rect x={zone[0] * size} y={zone[1] * h} width={(zone[2] - zone[0]) * size} height={(zone[3] - zone[1]) * h}
              className="hand-view__zone" />
      )}
      {landmarks ? (
        <g>
          {CONNECTIONS.map(([a, b]) => (
            <line key={`${a}-${b}`} x1={landmarks[a][0] * size} y1={landmarks[a][1] * h} x2={landmarks[b][0] * size}
                  y2={landmarks[b][1] * h} className="hand-view__bone" />
          ))}
          {landmarks.map(([x, y], i) => (
            <circle key={i} cx={x * size} cy={y * h} r={i % 4 === 0 ? 2.6 : 1.8} className="hand-view__joint" />
          ))}
        </g>
      ) : (
        <text x={size / 2} y={h / 2} textAnchor="middle" className="hand-view__empty">НЕТ РУКИ</text>
      )}
    </svg>
  );
}
