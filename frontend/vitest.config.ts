import { defineConfig } from 'vitest/config'

// The app's tsconfig.json sets "jsx": "preserve" (Next.js handles the JSX
// transform itself via SWC), but that setting also makes Vite/esbuild leave
// JSX untouched during `vitest run`, which then fails to parse as plain JS
// for any .tsx module actually imported into a test (e.g. real components,
// as opposed to hand-written .test.tsx files that avoid JSX syntax).
// Overriding esbuild's jsx mode here only affects the vitest/vite pipeline
// used by `npx vitest run` -- it has no effect on `next build` or `tsc`,
// which read tsconfig.json directly and are unaffected by this file.
export default defineConfig({
  // Vite 8 defaults to its oxc-based transformer instead of esbuild; disable
  // it so the `esbuild.jsx` override below actually takes effect (otherwise
  // oxc silently wins and still honors tsconfig's "preserve").
  oxc: false,
  esbuild: {
    // `esbuild` itself isn't an installed dependency in this vite version
    // (it ships its own vendored, slimmed-down type for the `esbuild`
    // option that doesn't declare `jsx`) -- the option is still honored at
    // runtime by vite's bundled esbuild-compatible transform, just untyped.
    // @ts-expect-error -- see comment above; `jsx` works at runtime.
    jsx: 'automatic',
  },
})
