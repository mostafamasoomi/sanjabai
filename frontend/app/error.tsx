'use client'

import { useEffect } from 'react'
import Link from 'next/link'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('Page error:', error)
  }, [error])

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center px-4">
      <div className="text-7xl font-bold text-[var(--danger)] mb-4">⚠️</div>
      <h1 className="text-2xl font-bold text-[var(--text)] mb-2">خطای سیستمی</h1>
      <p className="text-[var(--text-dim)] mb-2 max-w-md">
        مشکلی در بارگذاری صفحه پیش آمده است.
      </p>
      {error.digest && (
        <p className="text-xs text-[var(--text-muted)] mb-6 font-mono">
          Error ID: {error.digest}
        </p>
      )}
      <div className="flex gap-4">
        <button onClick={reset} className="btn btn-primary">
          تلاش مجدد
        </button>
        <Link href="/" className="btn btn-ghost">
          بازگشت به خانه
        </Link>
      </div>
    </div>
  )
}