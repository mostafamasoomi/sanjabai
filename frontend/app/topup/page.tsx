'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Spinner } from '@/components/ui'

// The topup functionality is fully implemented in the wallet page.
// This page redirects users there to avoid a dead-end stub.
export default function TopUpPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/wallet')
  }, [router])

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="flex items-center gap-3 text-[var(--text-muted)]">
        <Spinner size="sm" />
        <span className="text-sm">در حال انتقال به کیف پول...</span>
      </div>
    </div>
  )
}
