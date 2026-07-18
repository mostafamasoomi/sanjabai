import type { Metadata } from 'next'
import './globals.css'
import { AppShell } from '@/components/AppShell'

export const metadata: Metadata = {
  title: 'Multiai — پلتفرم هوش مصنوعی فارسی',
  description: 'دسترسی به بهترین مدل‌های هوش مصنوعی با API فارسی، قیمت‌گذاری شفاف و پشتیبانی محلی',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" data-theme="dark">
      <body className="antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  )
}
