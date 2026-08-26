'use client'

import Link from 'next/link'
import { useLang } from '@/components/LanguageToggle'
import { notFoundStrings } from './NotFoundView.strings'

/* The visible half of the 404.
 *
 * Split out because `app/not-found.tsx` exports `metadata` — the custom title
 * and the `noindex` directive — and a file that exports metadata must stay a
 * Server Component, where `useLang()` cannot run. Rather than trade the
 * noindex away for a translation, the page keeps its metadata and delegates
 * everything a visitor actually sees to this client component. */
export function NotFoundView() {
  const s = notFoundStrings(useLang())

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center px-4">
      {/* Latin numerals in both languages: "404" is an HTTP status, the same
          three characters everywhere, not a quantity to localise. */}
      <div className="text-8xl font-bold text-gradient mb-4" dir="ltr">404</div>
      <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-2">{s.heading}</h1>
      <p className="text-[var(--text-muted)] mb-8 max-w-md">{s.body}</p>
      <div className="flex gap-4">
        <Link href="/" className="btn btn-primary">{s.home}</Link>
        <Link href="/chat" className="btn btn-ghost">{s.chat}</Link>
      </div>
    </div>
  )
}
