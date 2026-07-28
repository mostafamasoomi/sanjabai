'use client'

import { useEffect, useRef } from 'react'

/**
 * Particle vortex shader for MultiAI hero canvas.
 * Uses raw WebGL2 — vertex transforms position through modelViewProjection,
 * fragment does tone mapping (reinhard) + sRGB OETF.
 */
export default function VortexWebGL() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return

    const gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: false })
    if (!gl) return

    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches

    const vertexShader = `#version 300 es
      in vec3 aPosition;
      in float aRandom;
      uniform float uTime;
      uniform vec2 uResolution;
      uniform vec2 uPointer;
      uniform float uScroll;
      out float vAlpha;
      out vec3 vColor;
      out float vRandom;

      void main() {
        float t = uTime;
        float dist = length(aPosition.xy);
        float angle = atan(aPosition.y, aPosition.x);

        // Vortex spiral motion
        angle += t * 0.45 * (1.0 + aRandom * 0.5);
        dist += sin(t * 0.6 + angle * 3.0) * 0.07;
        dist += uScroll * 0.05;

        // Pointer influence
        vec2 pos = vec2(
          cos(angle) * dist + uPointer.x * 0.08 * sin(angle * 3.0 + t),
          sin(angle) * dist + uPointer.y * 0.06 * cos(angle * 2.0 + t)
        );

        // Transform to clip space via modelViewProjection-like orthographic projection
        vec2 ndc = (pos / vec2(2.0)); // normalize to [-1,1] roughly
        vec4 clipPos = vec4(ndc, 0.0, 1.0);
        gl_Position = clipPos;

        // Point size with depth falloff
        float sizeAttenuation = (1.0 - abs(pos.y)) * 0.5 + 0.5;
        gl_PointSize = (1.5 + 2.5 * sizeAttenuation) * (uResolution.x / max(uResolution.y, 1.0));

        // Color: mix between blue and purple
        float mixFactor = 0.5 + 0.5 * sin(t + angle * 4.0);
        vColor = mix(vec3(0.22, 0.35, 1.0), vec3(0.85, 0.3, 1.0), mixFactor);

        // Alpha based on distance from center
        vAlpha = 0.22 + 0.32 * (1.0 - abs(pos.y));
        vAlpha *= (1.0 - smoothstep(0.8, 1.2, dist));
        vRandom = aRandom;
      }
    `

    const fragmentShader = `#version 300 es
      precision highp float;
      in float vAlpha;
      in vec3 vColor;
      in float vRandom;
      uniform float uTime;
      out vec4 fragColor;

      void main() {
        vec2 q = gl_PointCoord - vec2(0.5);
        float d = length(q);
        if (d > 0.5) discard;

        // Soft circular particle
        float alpha = smoothstep(0.5, 0.1, d);
        alpha *= vAlpha;

        // Tone mapping (Reinhard)
        vec3 c = vColor;
        c = c / (vec3(1.0) + c);

        // sRGB OETF approximation
        c = pow(max(c, vec3(0.0)), vec3(1.0 / 2.2));

        fragColor = vec4(c, alpha * (1.0 - d * 2.0));
      }
    `

    // ── Compile & link shaders ──────────────────────────────────────
    const createShader = (source: string, type: number) => {
      const shader = gl.createShader(type)!
      gl.shaderSource(shader, source)
      gl.compileShader(shader)
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        throw new Error(gl.getShaderInfoLog(shader) || 'shader compilation failed')
      }
      return shader
    }

    const program = gl.createProgram()!
    gl.attachShader(program, createShader(vertexShader, gl.VERTEX_SHADER))
    gl.attachShader(program, createShader(fragmentShader, gl.FRAGMENT_SHADER))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || 'program link failed')
    }
    gl.useProgram(program)

    // ── Create buffer attributes ────────────────────────────────────
    const PARTICLE_COUNT = 720
    const positions = new Float32Array(PARTICLE_COUNT * 3)
    const randoms = new Float32Array(PARTICLE_COUNT)
    const originalPositions = new Float32Array(PARTICLE_COUNT * 3) // Keep base positions

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const angle = Math.random() * Math.PI * 2
      const radius = Math.sqrt(Math.random())
      const px = Math.cos(angle) * radius
      const py = Math.sin(angle) * radius
      positions[i * 3] = px
      positions[i * 3 + 1] = py
      positions[i * 3 + 2] = 0
      originalPositions[i * 3] = px
      originalPositions[i * 3 + 1] = py
      originalPositions[i * 3 + 2] = 0
      randoms[i] = Math.random()
    }

    const positionBuffer = gl.createBuffer()!
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.DYNAMIC_DRAW)

    const positionLoc = gl.getAttribLocation(program, 'aPosition')
    gl.enableVertexAttribArray(positionLoc)
    gl.vertexAttribPointer(positionLoc, 3, gl.FLOAT, false, 0, 0)

    const randomBuffer = gl.createBuffer()!
    gl.bindBuffer(gl.ARRAY_BUFFER, randomBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, randoms, gl.STATIC_DRAW)
    const randomLoc = gl.getAttribLocation(program, 'aRandom')
    gl.enableVertexAttribArray(randomLoc)
    gl.vertexAttribPointer(randomLoc, 1, gl.FLOAT, false, 0, 0)

    // ── Uniform locations ───────────────────────────────────────────
    const uTime = gl.getUniformLocation(program, 'uTime')
    const uResolution = gl.getUniformLocation(program, 'uResolution')
    const uPointer = gl.getUniformLocation(program, 'uPointer')
    const uScroll = gl.getUniformLocation(program, 'uScroll')

    // ── Render setup ────────────────────────────────────────────────
    let mx = 0
    let my = 0
    let sy = 0
    let start = performance.now()

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio, 2)
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      gl.viewport(0, 0, canvas.width, canvas.height)
    }

    const mouse = (e: MouseEvent) => {
      mx = e.clientX / window.innerWidth * 2 - 1
      my = 1 - e.clientY / window.innerHeight * 2
    }

    const onScroll = () => {
      sy = Math.min(window.scrollY / window.innerHeight, 2)
    }

    let frameId: number | undefined
    const draw = (now: number) => {
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)
      gl.enable(gl.BLEND)
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE)

      const elapsed = (now - start) / 1000

      // Update positions each frame
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const origX = originalPositions[i * 3]
        const origY = originalPositions[i * 3 + 1]
        const radius = Math.sqrt(origX * origX + origY * origY)
        const angle = Math.atan2(origY, origX)

        const rot = elapsed * 0.45 * (1.0 + randoms[i] * 0.5)
        const pulse = Math.sin(elapsed * 0.6 + angle * 3.0) * 0.07
        const newDist = Math.min(radius + pulse, 1.0) * 0.95
        const newAngle = angle + rot

        positions[i * 3] = Math.cos(newAngle) * newDist
        positions[i * 3 + 1] = Math.sin(newAngle) * newDist
        positions[i * 3 + 2] = 0
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, positions)

      gl.uniform1f(uTime, elapsed)
      gl.uniform2f(uResolution, canvas.width, canvas.height)
      gl.uniform2f(uPointer, mx, my)
      gl.uniform1f(uScroll, sy)

      gl.drawArrays(gl.POINTS, 0, PARTICLE_COUNT)

      if (!reduced) {
        frameId = requestAnimationFrame(draw)
      }
    }

    resize()
    addEventListener('resize', resize)
    addEventListener('mousemove', mouse, { passive: true })
    addEventListener('scroll', onScroll, { passive: true })

    if (!reduced) {
      frameId = requestAnimationFrame(draw)
    }

    return () => {
      if (frameId !== undefined) cancelAnimationFrame(frameId)
      removeEventListener('resize', resize)
      removeEventListener('mousemove', mouse)
      removeEventListener('scroll', onScroll)
      gl.deleteBuffer(positionBuffer)
      gl.deleteBuffer(randomBuffer)
      gl.deleteProgram(program)
    }
  }, [])

  return <canvas ref={ref} className="motion-vortex" aria-hidden="true" />
}
