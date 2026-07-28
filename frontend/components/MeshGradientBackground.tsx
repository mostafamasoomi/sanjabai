'use client'

import { useEffect, useRef } from 'react'
import * as THREE from 'three'

// Two visual layers: mesh gradient displacement + atmospheric glow
// Reference: _meshGradientCanvas_i17l8_55 inside _meshGradientVisual_i17l8_45

export default function MeshGradientBackground({ variant = 0 }: { variant?: 0 | 1 }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current!
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches

    const vertexShader = `
      uniform float uTime;
      uniform vec2 uResolution;
      uniform float uVariant;
      varying vec2 vUv;
      varying vec3 vColor;

      void main() {
        vUv = uv;
        vec3 pos = position;

        // Mesh displacement
        float freq1 = 1.8 + uVariant * 0.4;
        float freq2 = 2.3 - uVariant * 0.3;
        pos.z += sin(pos.x * freq1 + uTime * 0.3) * cos(pos.y * freq2 + uTime * 0.25) * 0.45;

        // Color: warm gradient based on displacement
        float t = (pos.z + 0.45) / 0.9;
        vec3 a = vec3(0.01, 0.01, 0.08);
        vec3 b = uVariant < 0.5
          ? mix(vec3(0.15, 0.04, 0.28), vec3(0.6, 0.1, 0.5), t)
          : mix(vec3(0.0, 0.15, 0.25), vec3(0.0, 0.45, 0.55), t);
        vColor = a + b * smoothstep(0.0, 1.0, t);

        gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
      }
    `

    const fragmentShader = `
      varying vec2 vUv;
      varying vec3 vColor;

      void main() {
        float edgeFade = smoothstep(0.0, 0.15, vUv.x) * smoothstep(1.0, 0.85, vUv.x)
                        * smoothstep(0.0, 0.15, vUv.y) * smoothstep(1.0, 0.85, vUv.y);
        gl_FragColor = vec4(vColor, 0.25 * edgeFade);
      }
    `

    const scene = new THREE.Scene()
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)

    const material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: {
        uTime: { value: 0 },
        uResolution: { value: new THREE.Vector2(1, 1) },
        uVariant: { value: variant },
      },
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
    })

    const geometry = new THREE.PlaneGeometry(2.2, 2.2, 48, 48)
    const mesh = new THREE.Mesh(geometry, material)
    scene.add(mesh)

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true })
    renderer.setClearColor(0x000000, 0)

    function resize() {
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      const dpr = Math.min(devicePixelRatio, 2)
      renderer.setSize(w * dpr, h * dpr)
      material.uniforms.uResolution.value.set(w * dpr, h * dpr)
    }
    resize()
    addEventListener('resize', resize)

    let isVisible = true
    let animId: number
    const observer = new IntersectionObserver(([e]) => {
      isVisible = e.isIntersecting
      if (isVisible && !animId) animId = requestAnimationFrame(draw)
    }, { rootMargin: '200px' })
    observer.observe(canvas!)

    function draw() {
      if (!isVisible) { animId = 0; return }
      material.uniforms.uTime.value = performance.now() / 1000
      renderer.render(scene, camera)
      animId = requestAnimationFrame(draw)
    }

    if (!reduced) animId = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(animId)
      removeEventListener('resize', resize)
      observer.disconnect()
      renderer.dispose()
      geometry.dispose()
      material.dispose()
    }
  }, [variant])

  return <canvas ref={ref} className="mesh-gradient-canvas" aria-hidden="true"
    style={{
      position: 'absolute', inset: 0, width: '100%', height: '100%',
      pointerEvents: 'none', zIndex: variant === 0 ? 0 : 1, display: 'block',
      opacity: variant === 0 ? 0.6 : 0.4, mixBlendMode: 'screen',
    }} />
}
