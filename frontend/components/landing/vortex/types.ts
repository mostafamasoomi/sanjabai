// Vortex — shared type declarations (engine API surface + public props).
// Moved out of Vortex.tsx verbatim (pure move refactor, no behaviour change).

import type * as React from "react";
import type { DEFAULTS } from "./constants";

export type VortexAPI = {
  rebuild: () => void;
  dispose: () => void;
};

export interface VortexProps {
  background?: string;
  topRadius?: number;
  waistRadius?: number;
  waistPosition?: number;
  bottomRadius?: number;
  twist?: number;
  zoom?: number;
  speed?: number;
  direction?: "right" | "left";
  lineOptions?: Partial<typeof DEFAULTS.lineOptions>;
  dots?: boolean;
  dotOptions?: Partial<typeof DEFAULTS.dotOptions>;
  comets?: boolean;
  cometOptions?: Partial<typeof DEFAULTS.cometOptions>;
  repel?: boolean;
  repelOptions?: Partial<typeof DEFAULTS.repelOptions>;
  style?: React.CSSProperties;
}
