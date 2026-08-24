// Vortex — canvas-baked sprite textures.
// Moved out of Vortex.tsx verbatim (pure move refactor, no behaviour change).

import * as THREE from "three";

/** A soft round blob on a canvas, for the sprites. */
export function blob(size: number, stops: [number, string][]) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx2d = c.getContext("2d");
  if (ctx2d) {
    const g = ctx2d.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    for (const [at, color] of stops) g.addColorStop(at, color);
    ctx2d.fillStyle = g;
    ctx2d.fillRect(0, 0, size, size);
  }
  const tex = new THREE.Texture(c);
  tex.needsUpdate = true;
  return tex;
}
