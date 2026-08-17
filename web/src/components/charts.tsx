import { colourFor, money, moneyShort } from "../lib/format";
import { t } from "../lib/i18n";

/**
 * Hand-rolled SVG rather than a charting library.
 *
 * Recharts or Chart.js would be the normal answer and is what most teams use. Two
 * shapes and a legend do not justify 60kB of dependency, a second rendering model to
 * reason about, and a wrapper to make it agree with this stylesheet. The technique is
 * one line of SVG: each arc is a `stroke-dasharray` as long as its share of the
 * circumference, offset past the arcs before it.
 */

export interface Slice {
  label: string;
  value: number;
}

export function Donut({
  slices,
  centreValue,
  centreLabel,
}: {
  slices: Slice[];
  centreValue: string;
  centreLabel: string;
}) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (total <= 0) return <div className="empty-note">{t("no_data")}</div>;

  const R = 62;
  const C = 2 * Math.PI * R;
  let offset = 0;
  const arcs = slices.map((s, i) => {
    const len = (s.value / total) * C;
    const arc = (
      <circle
        key={s.label}
        cx="90"
        cy="90"
        r={R}
        fill="none"
        stroke={colourFor(i)}
        strokeWidth="26"
        strokeDasharray={`${len} ${C - len}`}
        strokeDashoffset={-offset}
        transform="rotate(-90 90 90)"
      >
        <title>{`${s.label}: ${money(s.value)}`}</title>
      </circle>
    );
    offset += len;
    return arc;
  });

  return (
    <>
      <div className="chart-box" style={{ maxWidth: 280, margin: "14px auto 0" }}>
        <svg viewBox="0 0 180 180">
          {arcs}
          <text x="90" y="84" textAnchor="middle" fontSize="11" fill="var(--muted)">
            {centreLabel}
          </text>
          <text
            x="90"
            y="102"
            textAnchor="middle"
            fontSize="15"
            fontWeight="700"
            fill="var(--ink)"
          >
            {centreValue}
          </text>
        </svg>
      </div>
      <div className="legend">
        {slices.map((s, i) => (
          <div className="legend-row" key={s.label}>
            <span className="dot" style={{ background: colourFor(i) }} />
            <span className="lbl">{s.label}</span>
            <span className="val">{money(s.value)}</span>
            <span className="pct">{((s.value / total) * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </>
  );
}

export interface Point {
  label: string;
  value: number;
}

export function TrendLine({ points }: { points: Point[] }) {
  if (points.length < 2) return <div className="empty-note">{t("need_two_months")}</div>;

  const W = 720;
  const H = 240;
  const L = 58; // room for the value labels
  const R = 24;
  const TOP = 28;
  const BOT = 34;

  const values = points.map((p) => p.value);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  // Pad the range so the line does not sit on the frame, and give a flat series a span
  // of its own rather than dividing by zero.
  const pad = (rawMax - rawMin || rawMax || 1) * 0.25;
  const min = Math.max(0, rawMin - pad);
  const max = rawMax + pad;
  const span = max - min || 1;

  const x = (i: number) => L + (i * (W - L - R)) / (points.length - 1);
  const y = (v: number) => TOP + (1 - (v - min) / span) * (H - TOP - BOT);

  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.value)}`).join(" ");
  const last = points[points.length - 1];

  return (
    <div className="chart-box">
      <svg viewBox={`0 0 ${W} ${H}`}>
        {[min, min + span / 2, max].map((v) => (
          <g key={v}>
            <line x1={L} y1={y(v)} x2={W - R} y2={y(v)} stroke="var(--grid)" strokeWidth="1" />
            <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">
              {moneyShort(v)}
            </text>
          </g>
        ))}

        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinejoin="round" />

        {points.map((p, i) => (
          <g key={p.label}>
            <circle cx={x(i)} cy={y(p.value)} r="4" fill="var(--accent)">
              <title>{`${p.label}: ${money(p.value, 2)}`}</title>
            </circle>
            <text x={x(i)} y={H - 8} fontSize="11" fill="var(--muted)" textAnchor="middle">
              {p.label}
            </text>
          </g>
        ))}

        {last && (
          <text
            x={x(points.length - 1)}
            y={y(last.value) - 12}
            textAnchor="end"
            fontSize="13"
            fontWeight="700"
            fill="var(--ink)"
          >
            {money(last.value, 2)}
          </text>
        )}
      </svg>
    </div>
  );
}
