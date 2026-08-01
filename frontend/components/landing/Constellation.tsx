/**
 * A hub-and-spoke node graph layered into the hero aura — the one part of
 * the page's 3D/motion language that's actually *about* the product
 * (many models converging into one workspace) rather than a generic
 * tilt/glow trend applied to whatever section needed filling. Pure SVG +
 * CSS: no canvas, no per-frame JS, nodes pulse via a CSS keyframe.
 */

// Two independent clusters, one per side, each with its own local hub —
// not one hub with spokes running to both sides. A single center-left hub
// with lines reaching across to the right-side nodes would cross straight
// through the headline column (roughly x: 190–610 in this 800-wide
// viewBox), which is exactly what the first version of this did. Keeping
// each cluster's lines within its own outer margin means nothing ever
// crosses the text at all, regardless of opacity.
const LEFT_HUB = { x: 40, y: 210 }
const LEFT_NODES = [
  { x: 90, y: 60 },
  { x: 150, y: 340 },
  { x: 60, y: 430 },
] as const

const RIGHT_HUB = { x: 760, y: 210 }
const RIGHT_NODES = [
  { x: 700, y: 55 },
  { x: 730, y: 260 },
  { x: 660, y: 420 },
] as const

function Cluster({ hub, nodes, keyOffset }: { hub: { x: number; y: number }; nodes: readonly { x: number; y: number }[]; keyOffset: number }) {
  return (
    <>
      <g className="lp-constellation__lines">
        {nodes.map((n, i) => (
          <line key={i} x1={hub.x} y1={hub.y} x2={n.x} y2={n.y} />
        ))}
      </g>
      <g className="lp-constellation__nodes">
        {nodes.map((n, i) => (
          <circle
            key={i}
            className="lp-constellation__node"
            style={{ '--i': i + keyOffset } as React.CSSProperties}
            cx={n.x}
            cy={n.y}
            r={3.5}
          />
        ))}
        <circle className="lp-constellation__hub" cx={hub.x} cy={hub.y} r={6} />
      </g>
    </>
  )
}

export function Constellation() {
  return (
    <svg
      className="lp-constellation"
      viewBox="0 0 800 500"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <Cluster hub={LEFT_HUB} nodes={LEFT_NODES} keyOffset={0} />
      <Cluster hub={RIGHT_HUB} nodes={RIGHT_NODES} keyOffset={LEFT_NODES.length} />
    </svg>
  )
}
