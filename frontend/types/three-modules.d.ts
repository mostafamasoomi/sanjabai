declare module 'three/webgpu' {
  export class WebGPURenderer {
    constructor(opts?: any)
    setClearColor(color: any, alpha?: number): void
    setSize(w: number, h: number): void
    render(scene: any, camera: any): void
    init(): Promise<void>
    dispose(): void
  }
  export class NodeMaterial {
    fragmentNode: any
    vertexNode: any
    needsUpdate: boolean
    transparent: boolean
    depthWrite: boolean
    dispose(): void
  }
  export function uniform(value: any): any
}

declare module 'three/tsl' {
  export function Fn(args: any): any
  export function vec2(...args: any[]): any
  export function vec3(...args: any[]): any
  export function float(...args: any[]): any
  export function uv(): any
  export function sin(...args: any[]): any
  export function cos(...args: any[]): any
  export function mix(...args: any[]): any
  export function length(...args: any[]): any
  export function smoothstep(...args: any[]): any
}
