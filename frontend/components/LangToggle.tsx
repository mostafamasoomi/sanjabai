'use client'

import { useI18n } from '@/lib/i18n'

export function LangToggle() {
  const { lang, setLang } = useI18n()

  return (
    <button
      onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}
      className="btn btn-ghost btn-icon text-sm font-bold"
      aria-label="Change language"
      title={lang === 'fa' ? 'English' : 'فارسی'}
    >
      {lang === 'fa' ? 'EN' : 'FA'}
    </button>
  )
}