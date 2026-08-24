// Vortex — static configuration, tuning constants and the Originkit preset.
// Moved out of Vortex.tsx verbatim (pure move refactor, no behaviour change).

import { clamp } from "./math";

// One DEFAULTS drives both the destructure fallbacks and the prop defaults.
// Every slider is a whole number where it can be. The values they actually mean
// live beside the engine as *_MAX constants and are mapped in one place, below.
export const DEFAULTS = {
  background: "#000000",
  topRadius: 380,
  waistRadius: 53,
  waistPosition: 50,
  bottomRadius: 1150,
  twist: 3,
  zoom: 75,
  speed: 10,
  direction: "right" as "right" | "left",
  lineOptions: {
    count: 240,
    color: "#ffffff",
    glow: 10,
  },
  dots: true,
  dotOptions: {
    count: 8000,
    size: 20,
    color: "#ffffff",
    glow: 10,
    flicker: 10,
  },
  comets: true,
  cometOptions: {
    count: 10,
    speed: 6,
    color: "#F9731A",
    glow: 6,
    tail: 19,
    delay: 8,
    collide: 6,
  },
  repel: false,
  repelOptions: {
    radius: 60,
    strength: 10,
  },
};

/* ============================================================ constants */

export const TAU = Math.PI * 2;

// The three radii and every other reach read in screen pixels on the panel and
// world units on the wire. The camera frames the form's full height to the
// component's height, so at the 600px intrinsic height ten world units span the
// frame — sixty pixels to the unit. Bottom 900px is the 15 the effect was
// authored with, waist 30px its 0.5, top 300px its 5.
export const PX_PER_WORLD = 60;

// Segments along each strand. Trades smoothness for memory; there is no
// reason to ship anything but the smooth end.
export const STRAND_SEGMENTS = 400;

// How far the strands sway off their ideal path, as a share of the local radius.
export const WOBBLE = 0.008;
// The share of each strand's length that fades out at either end, so the form
// dissolves rather than stopping on a cut edge.
export const FADE_ZONE = 0.15;

// The form's height in world units. The camera is solved to frame exactly this,
// so the component's own height is what sizes the vortex.
export const FORM_HEIGHT = 10;

// The zoom the framing is solved for, and the default. Above it we push
// in, below it the view widens.
export const BASE_ZOOM = 67;
// zoom prop -> camera FOV. The prop reads as a zoom (higher is closer), which
// is the inverse of what FOV does, so it is mirrored — around BASE_ZOOM rather
// than the slider's midpoint, which keeps the tuned default a fixed point.
export const fovForZoom = (zoom: number) => clamp(2 * BASE_ZOOM - zoom, 1, 175);

// 0..10 sliders onto the values their top ends mean.
export const LINE_GLOW_MAX = 1;
export const DOT_GLOW_MAX = 4.2;
export const COMET_SPEED_MAX = 0.15;
export const COMET_GLOW_MAX = 1;
export const DOT_SIZE_SCALE = 1000;

// The ripple. A burst shoves every dot inside its radius, and each dot is then
// sprung back to where it belongs — position and size on their own springs, so
// a dot swells as it is pushed and settles as it returns.
//
// Reach and force are constants rather than dials: a comet strike is the only
// thing that throws one now, and it wants the same ripple every time.
export const RIPPLE_RADIUS = 2;
export const RIPPLE_STRENGTH = 0.5;
export const RIPPLE_SPRING = 50;
export const RIPPLE_DAMPING = 9;
export const SCALE_SPRING = 65;
export const SCALE_DAMPING = 11;
export const SCALE_PEAK = 1.8;

// The shockwave that runs out from a burst: a ring travelling at WAVE_SPEED,
// this wide, fading over DECAY and gone by MAX_LIFE. It moves the STRANDS, not
// the dots — the dots have their springs.
export const WAVE_SPEED = 5;
export const WAVE_WIDTH = 1.2;
export const WAVE_DECAY = 0.8;
export const WAVE_LIFE = 2.5;
export const WAVE_STRENGTH = 0.04;
export const MAX_WAVES = 16;

// The stretch of a strand a comet runs, and how much of either end it fades
// over. Turning right it climbs from LOW to HIGH; turning left it starts at
// HIGH and comes back down, which is the same run read backwards.
export const RUN_LOW = 0.03;
export const RUN_HIGH = 0.95;
export const RUN_FADE = 0.1;

// A comet running into a dot: how close counts, how much faster it goes and for
// how long, how brightly the dot flashes and how long it stays gone.
export const HIT_RADIUS = 0.8;
export const HIT_BOOST = 1.6;
export const HIT_BOOST_TIME = 0.4;
export const HIT_FLASH = 6;
export const HIT_FADE = 0.6;
export const HIT_POP = 1.3;
export const HIT_RESPAWN = 8;

// Strands are rewritten at this rate rather than every frame. Four hundred
// points across eighty strands is thirty-two thousand vertices to lay out, and
// at a flow this slow nobody can tell it from sixty.
export const STRAND_HZ = 1 / 30;

// The layers do not all arrive at once. Seconds from the first frame.
export const ENTRANCE = {
  strandStart: 0,
  strandEnd: 2,
  dotStart: 1.2,
  dotEnd: 3,
  cometStart: 3,
  cometEnd: 5,
};

// What Repel Strength 100% comes to in NDC.
export const REPEL_MAX_NDC = 0.45;

// The Originkit preset — the default props layered under whatever a caller
// passes in.
export const __originkitPresetProps = {
  "background": "#000000",
  "topRadius": 230,
  "waistRadius": 25,
  "waistPosition": 48,
  "bottomRadius": 700,
  "twist": 2,
  "zoom": 75,
  "speed": 10,
  "direction": "right",
  "comets": true
};
