'use client'

import { useState, useEffect } from 'react'

export type Lang = 'fa' | 'en'

export function getLang(): Lang {
  if (typeof window === 'undefined') return 'fa'
  try {
    const v = (localStorage.getItem('lang') || '') as Lang
    if (v === 'fa' || v === 'en') return v
  } catch {}
  return 'fa'
}

export function setLang(l: Lang) {
  try { localStorage.setItem('lang', l) } catch {}
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('lang', l)
    document.documentElement.setAttribute('dir', l === 'fa' ? 'rtl' : 'ltr')
  }
}

export function LanguageToggle() {
  const [lang, setLangState] = useState<Lang>('fa')

  useEffect(() => {
    setLangState(getLang())
    setLang(getLang())
  }, [])

  const toggle = () => {
    const next: Lang = lang === 'fa' ? 'en' : 'fa'
    setLangState(next)
    setLang(next)
    // optional: reload to apply dir globally fast
    window.location.reload()
  }

  return (
    <button
      onClick={toggle}
      className="btn btn-ghost btn-icon"
      aria-label={lang === 'fa' ? 'Switch to English' : 'تغییر به فارسی'}
      title={lang === 'fa' ? 'EN' : 'FA'}
    >
      {lang === 'fa' ? 'EN' : 'فا'}
    </button>
  )
}
