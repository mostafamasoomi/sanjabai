// Vortex — pure numeric helpers used by the shape profile and the render loop.
// Moved out of Vortex.tsx verbatim (pure move refactor, no behaviour change).

/* ============================================================ maths */

export const clamp = (x: number, a: number, b: number) => Math.min(Math.max(x, a), b);

/** Ease used by the entrance fades — quick off the mark, long tail. */
export function ramp(now: number, from: number, to: number) {
  if (now <= from) return 0;
  if (now >= to) return 1;
  const t = (now - from) / (to - from);
  return 1 - (1 - t) * (1 - t) * (1 - t);
}

/**
 * Monotone cubic interpolation through a set of points.
 *
 * Monotone specifically, not a plain spline: the radius profile has a hard pinch
 * at the waist, and an ordinary cubic overshoots either side of a corner like
 * that — the strands would bulge back OUT just before the neck and cross each
 * other doing it. The Fritsch-Carlson limiter below is what stops that.
 */
export function monotone(points: [number, number][]) {
  const n = points.length;
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    slope[i] =
      (points[i + 1][1] - points[i][1]) / (points[i + 1][0] - points[i][0]);
  }
  const m: number[] = [slope[0]];
  for (let i = 1; i < n - 1; i++) {
    m[i] = slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2;
  }
  m[n - 1] = slope[n - 2];
  for (let i = 0; i < n - 1; i++) {
    if (Math.abs(slope[i]) < 1e-12) {
      m[i] = m[i + 1] = 0;
      continue;
    }
    const a = m[i] / slope[i];
    const b = m[i + 1] / slope[i];
    const s = a * a + b * b;
    if (s > 9) {
      const k = 3 / Math.sqrt(s);
      m[i] = k * a * slope[i];
      m[i + 1] = k * b * slope[i];
    }
  }
  return (x: number) => {
    if (x <= points[0][0]) return points[0][1];
    if (x >= points[n - 1][0]) return points[n - 1][1];
    let i = 0;
    while (i < n - 2 && points[i + 1][0] < x) i++;
    const h = points[i + 1][0] - points[i][0];
    const t = (x - points[i][0]) / h;
    const t2 = t * t;
    const t3 = t2 * t;
    return (
      (2 * t3 - 3 * t2 + 1) * points[i][1] +
      (t3 - 2 * t2 + t) * h * m[i] +
      (-2 * t3 + 3 * t2) * points[i + 1][1] +
      (t3 - t2) * h * m[i + 1]
    );
  };
}

// Samples in each baked curve. Not worth a control: it only ever trades
// smoothness for memory, and there is no reason to ship anything but the
// smooth end.
const CURVE_SAMPLES = 1024;

/** Bake a curve to a lookup table — it is read millions of times a second. */
export function bake(fn: (x: number) => number) {
  const table = new Float32Array(CURVE_SAMPLES);
  for (let i = 0; i < CURVE_SAMPLES; i++) table[i] = fn(i / (CURVE_SAMPLES - 1));
  return table;
}

export function sample(table: Float32Array, t: number) {
  if (t <= 0) return table[0];
  const last = table.length - 1;
  if (t >= 1) return table[last];
  const x = t * last;
  const i = x | 0;
  return table[i] + (table[i + 1] - table[i]) * (x - i);
}
