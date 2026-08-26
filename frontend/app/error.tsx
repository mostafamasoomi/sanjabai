'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { useLang } from '@/components/LanguageToggle'
import { errorPageStrings } from './error.strings'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const lang = useLang()
  const s = errorPageStrings(lang)

  useEffect(() => {
    console.error('Page error:', error)
  }, [error])

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center px-4">
      <div className="text-7xl font-bold text-[var(--danger)] mb-4">⚠️</div>
      <h1 className="text-2xl font-bold text-[var(--text)] mb-2">{s.title}</h1>
      <p className="text-[var(--text-dim)] mb-2 max-w-md">{s.body}</p>
      {error.digest && (
        <p className="text-xs text-[var(--text-muted)] mb-6 font-mono">{s.errorId(error.digest)}</p>
      )}
      <div className="flex gap-4">
        <button onClick={reset} className="btn btn-primary">
          {s.retry}
        </button>
        <Link href="/" className="btn btn-ghost">
          {s.home}
        </Link>
      </div>
    </div>
  )
}