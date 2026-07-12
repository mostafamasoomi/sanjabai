'use client'

import dynamic from 'next/dynamic'

// Phase 10: the playground is an interactive, client-only tool (auth + live
// catalog + streaming). Rendering it with ssr:false keeps its logic out of the
// server bundle and defers it to the client. RTL is unaffected because the
// root layout still emits <html dir="rtl"> server-side.
const Playground = dynamic(() => import('./Playground'), {
  ssr: false,
  loading: () => (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: 'var(--bg-base)' }}
    >
      <span
        className="w-6 h-6 border-2 border-white/20 rounded-full animate-spin"
        style={{ borderTopColor: 'var(--accent)' }}
      />
    </div>
  ),
})

export default function Page() {
  return <Playground />
}
