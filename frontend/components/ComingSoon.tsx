'use client'

import { Icon } from '@/components/ui/Icon'
import Link from 'next/link'

export function ComingSoon({ title = 'به‌زودی' }: { title?: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <div className="w-16 h-16 bg-brand-soft text-brand rounded-2xl flex items-center justify-center mb-4">
        <Icon name="sparkles" className="w-8 h-8" />
      </div>
      <h1 className="text-2xl font-bold text-ink mb-2">{title}</h1>
      <p className="text-ink-2 max-w-md mb-6 leading-relaxed">
        این قابلیت در نسخه MVP غیرفعال است و به زودی در بروزرسانی‌های بعدی فعال خواهد شد.
      </p>
      <Link href="/chat" className="btn btn-primary">
        بازگشت به چت
      </Link>
    </div>
  )
}