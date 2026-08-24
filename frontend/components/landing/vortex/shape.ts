// Vortex — the strand/dot/comet radius-height-angle profile.
// Moved out of Vortex.tsx verbatim (pure move refactor, no behaviour change).

import { TAU, FORM_HEIGHT } from "./constants";
import { clamp, monotone, bake, sample } from "./math";

/* ============================================================ shape */

export type Shape = ReturnType<typeof makeShape>;

/**
 * The vortex as three curves against distance along a strand: how far out it is,
 * how high, and how far round.
 *
 * The intermediate radius points are placed as fractions of wherever the waist
 * sits rather than at fixed heights. At the middle they land exactly on the
 * numbers the effect was authored with, and anywhere else the profile keeps its
 * shape instead of the control points crossing over each other — which the
 * spline above cannot be built from at all.
 */
export function makeShape(cfg: any) {
  const w = clamp(cfg.waistAt, 0.08, 0.92);
  const floor = cfg.floorRadius;
  const crown = cfg.crownRadius;
  const turn = cfg.twist * TAU;

  const radius = bake(
    monotone([
      [0, floor],
      [0.24 * w, floor * 0.667],
      [0.5 * w, floor * 0.3],
      [0.76 * w, floor * 0.08],
      [w, cfg.waistRadius],
      [w + 0.3 * (1 - w), crown * 0.2],
      [w + 0.6 * (1 - w), crown * 0.44],
      [1, crown],
    ])
  );
  const height = bake(
    monotone([
      [0, 0],
      [0.1, 0.2],
      [0.2, 0.8],
      [0.35, 2],
      [0.5, FORM_HEIGHT * 0.38],
      [0.75, FORM_HEIGHT * 0.7],
      [1, FORM_HEIGHT],
    ])
  );
  const angle = bake(
    monotone([
      [0, 0],
      [0.15, 0.15 * turn],
      [0.25, 0.25 * turn],
      [0.45, 0.55 * turn],
      [0.6, 0.7 * turn],
      [0.8, 0.88 * turn],
      [1, turn],
    ])
  );

  return {
    /** Write one point of a strand into `out` at `at`. */
    writePoint(
      out: Float32Array,
      at: number,
      s: number,
      lane: number,
      flow: number,
      wobble: number,
      phase: number,
      time: number
    ) {
      const r = sample(radius, s);
      const y = sample(height, s);
      const a = sample(angle, s) + lane + flow;
      // The sway is a share of the local radius, not a fixed distance: a
      // fixed one is nothing against the floor plate and violent at the
      // waist, which is exactly where every strand converges.
      const rr = r + Math.sin(s * 25 + phase + time * 0.3) * wobble * r;
      out[at] = Math.cos(a) * rr;
      out[at + 1] = y;
      out[at + 2] = Math.sin(a) * rr;
    },
    lane: (i: number, total: number) => (i / total) * TAU,
  };
}
