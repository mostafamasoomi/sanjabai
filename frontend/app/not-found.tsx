import Link from 'next/link'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'صفحه پیدا نشد',
  robots: { index: false, follow: false },
}

export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center px-4">
      <div className="text-8xl font-bold text-gradient mb-4">404</div>
      <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-2">صفحه مورد نظر پیدا نشد</h1>
      <p className="text-[var(--text-muted)] mb-8 max-w-md">
        متأسفانه صفحه‌ای که دنبالش هستید وجود ندارد یا منتقل شده است.
      </p>
      <div className="flex gap-4">
        <Link href="/" className="btn btn-primary">
          بازگشت به خانه
        </Link>
        <Link href="/chat" className="btn btn-ghost">
          شروع چت
        </Link>
      </div>
    </div>
  )
}