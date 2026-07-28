'use client'

import { useEffect, useRef } from 'react'

// Water trail — raw WebGL2 fragment shader (no WebGPU/TSL dependency).
// Two animated gradient orbs drifting across a dark field.
// ponytail: simplified from 6 orbs to 3 for perf; add more by extending ORBS array.

const ORBS = [
  { pos: [0.60, 0.35], r: 0.45, a: 0.72, cA: [0.000, 0.486, 0.820], cB: [0.310, 0.698, 0.965], px: 1.1, py: 0.8 },
  { pos: [0.35, 0.50], r: 0.40, a: 0.60, cA: [0.686, 0.278, 1.000], cB: [1.000, 0.357, 0.824], px: 0.9, py: 0.7 },
  { pos: [0.50, 0.65], r: 0.35, a: 0.54, cA: [0.055, 0.514, 0.518], cB: [0.188, 0.855, 0.871], px: 0.7, py: 1.1 },
]

const FRAGMENT_SHADER = `#version 300 es
  precision highp float;
  uniform float uTime;
  uniform vec2 uResolution;
  out vec4 fragColor;

  void main() {
    vec2 uv = gl_FragCoord.xy / uResolution;
    vec3 base = vec3(1.0/255.0, 3.0/255.0, 20.0/255.0);
    vec3 accum = base;
    float t = uTime;

    // Orb 1
    vec2 p1 = vec2(0.60 + sin(t*1.1)*0.08, 0.35 + cos(t*0.8)*0.08);
    float d1 = length(uv - p1);
    float e1 = smoothstep(0.45, 0.0, d1);
    vec3 c1 = mix(vec3(0.0,0.486,0.820), vec3(0.310,0.698,0.965), smoothstep(0.0,0.27, d1));
    accum = mix(accum, c1, e1*0.72);

    // Orb 2
    vec2 p2 = vec2(0.35 + sin(t*0.9)*0.08, 0.50 + cos(t*0.7)*0.08);
    float d2 = length(uv - p2);
    float e2 = smoothstep(0.40, 0.0, d2);
    vec3 c2 = mix(vec3(0.686,0.278,1.0), vec3(1.0,0.357,0.824), smoothstep(0.0,0.24, d2));
    accum = mix(accum, c2, e2*0.60);

    // Orb 3
    vec2 p3 = vec2(0.50 + sin(t*0.7)*0.08, 0.65 + cos(t*1.1)*0.08);
    float d3 = length(uv - p3);
    float e3 = smoothstep(0.35, 0.0, d3);
    vec3 c3 = mix(vec3(0.055,0.514,0.518), vec3(0.188,0.855,0.871), smoothstep(0.0,0.21, d3));
    accum = mix(accum, c3, e3*0.54);

    // Reinhard tone mapping + sRGB
    accum = accum / (vec3(1.0) + accum);
    accum = pow(max(accum, vec3(0.0)), vec3(1.0/2.2));

    fragColor = vec4(accum, 0.35);
  }
`

const VERTEX_SHADER = `#version 300 es
  void main() {
    const vec2[4] pos = vec2[4](
      vec2(-1.0, -1.0), vec2(1.0, -1.0), vec2(-1.0, 1.0), vec2(1.0, 1.0)
    );
    const vec2[4] uv = vec2[4](
      vec2(0.0, 0.0), vec2(1.0, 0.0), vec2(0.0, 1.0), vec2(1.0, 1.0)
    );
    gl_Position = vec4(pos[gl_VertexID], 0.0, 1.0);
  }
`

export default function WaterTrailBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: false })
    if (!gl) return

    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches

    const createShader = (src: string, type: number) => {
      const sh = gl.createShader(type)!
      gl.shaderSource(sh, src)
      gl.compileShader(sh)
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        throw new Error(gl.getShaderInfoLog(sh) || 'shader compile failed')
      }
      return sh
    }

    const program = gl.createProgram()!
    gl.attachShader(program, createShader(VERTEX_SHADER, gl.VERTEX_SHADER))
    gl.attachShader(program, createShader(FRAGMENT_SHADER, gl.FRAGMENT_SHADER))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || 'link failed')
    }
    gl.useProgram(program)

    const uTime = gl.getUniformLocation(program, 'uTime')
    const uResolution = gl.getUniformLocation(program, 'uResolution')

    const resize = () => {
      const dpr = Math.min(devicePixelRatio, 2)
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      gl.viewport(0, 0, canvas.width, canvas.height)
      gl.uniform2f(uResolution, canvas.width, canvas.height)
    }
    resize()
    addEventListener('resize', resize)

    let start = performance.now()
    let animId = 0

    const draw = () => {
      const elapsed = (performance.now() - start) / 1000
      gl.uniform1f(uTime, elapsed)

      gl.enable(gl.BLEND)
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)

      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)

      if (!reduced) animId = requestAnimationFrame(draw)
    }
    if (!reduced) animId = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(animId)
      removeEventListener('resize', resize)
      gl.deleteProgram(program)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      id="water-trail-canvas"
      style={{
        position: 'absolute', inset: 0, width: '100%', height: '100%',
        pointerEvents: 'none', zIndex: 0, opacity: 0.35, display: 'block',
      }}
    />
  )
}
