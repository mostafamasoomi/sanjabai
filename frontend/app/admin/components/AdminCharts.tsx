"use client"

import { useLang } from '@/components/LanguageToggle'

/* recharts barrel optimization breaks the build — this is a stub until that
   is fixed, and recharts must not be reintroduced anywhere in the panel.
   Charts that do exist elsewhere in the admin are hand-written SVG. */

const COPY = {
  fa: { title: 'نمودار مصرف', body: 'نمودارها در آپدیت بعدی فعال می‌شوند' },
  en: { title: 'Usage chart', body: 'Charts arrive in a future update' },
}

export default function AdminCharts(_props: { data?: unknown }) {
  const c = COPY[useLang()] ?? COPY.fa
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] p-6">
      <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-4">{c.title}</h3>
      <div className="text-center text-[var(--text-muted)] py-8">{c.body}</div>
    </div>
  )
}
