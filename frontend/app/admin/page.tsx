'use client'

import dynamic from 'next/dynamic'

// Phase 10: load the heavy admin panel on the client only (ssr:false).
// It is a fully client-side, auth-gated dashboard, so server rendering adds
// no SEO/SSR value while forcing the whole component into the server bundle.
// RTL is preserved — <html dir="rtl"> lives in the root layout and is still
// emitted by the server; only the panel body is deferred to the client.
const AdminPanel = dynamic(() => import('./AdminPanel'), {
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
  return <AdminPanel />
}
