'use client'

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'

type Lang = 'fa' | 'en'

const translations: Record<Lang, Record<string, string>> = {
  fa: {
    chat: 'چت',
    compare: 'مقایسه',
    models: 'مدل‌ها',
    dashboard: 'داشبورد',
    pricing: 'تعرفه‌ها',
    wallet: 'کیف پول',
    profile: 'پروفایل',
    admin: 'ادمین',
    api: 'API',
    login: 'ورود',
    signup: 'ثبت‌نام',
    logout: 'خروج',
    start_chat: 'شروع چت',
    free_start: 'شروع رایگان',
    view_models: 'مشاهده مدل‌ها',
    hero_title: 'هوش مصنوعی برای همه، به زبان فارسی',
    hero_desc: 'یک پنل، تمام مدل‌های هوش مصنوعی دنیا',
    why_multiai: 'چرا Multiai؟',
    how_start: 'چطور شروع کنم؟',
    faq: 'سوالات متداول',
    ready_start: 'آماده شروع هستید؟',
    signup_gift: 'ثبتنام کنید و شروع کنید — بدون هزینه اولیه',
    change_password: 'تغییر رمز عبور',
    wallet_balance: 'موجودی کیف پول',
    topup: 'شارژ حساب',
    payment_history: 'تاریخچه پرداخت‌ها',
    api_keys: 'کلیدهای API',
    referral: 'دعوت دوستان',
    dark_mode: 'حالت تاریک',
    light_mode: 'حالت روشن',
    language: 'زبان',
  },
  en: {
    chat: 'Chat',
    compare: 'Compare',
    models: 'Models',
    dashboard: 'Dashboard',
    pricing: 'Pricing',
    wallet: 'Wallet',
    profile: 'Profile',
    admin: 'Admin',
    api: 'API',
    login: 'Login',
    signup: 'Sign Up',
    logout: 'Logout',
    start_chat: 'Start Chat',
    free_start: 'Start Free',
    view_models: 'View Models',
    hero_title: 'AI for Everyone',
    hero_desc: 'One panel, all AI models',
    why_multiai: 'Why Multiai?',
    how_start: 'How to Start?',
    faq: 'FAQ',
    ready_start: 'Ready to Start?',
    signup_gift: 'Sign up and get started — no upfront cost',
    change_password: 'Change Password',
    wallet_balance: 'Wallet Balance',
    topup: 'Top Up',
    payment_history: 'Payment History',
    api_keys: 'API Keys',
    referral: 'Refer Friends',
    dark_mode: 'Dark Mode',
    light_mode: 'Light Mode',
    language: 'Language',
  },
}

type I18nCtx = {
  lang: Lang
  t: (key: string) => string
  setLang: (l: Lang) => void
}

const I18nContext = createContext<I18nCtx>({
  lang: 'fa',
  t: (k: string) => k,
  setLang: () => {},
})

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>('fa')

  useEffect(() => {
    const saved = localStorage.getItem('lang')
    if (saved === 'en' || saved === 'fa') setLangState(saved)
  }, [])

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    localStorage.setItem('lang', l)
    document.documentElement.setAttribute('lang', l)
    document.documentElement.setAttribute('dir', l === 'fa' ? 'rtl' : 'ltr')
  }, [])

  const t = useCallback((key: string) => {
    return translations[lang]?.[key] || translations['fa']?.[key] || key
  }, [lang])

  return (
    <I18nContext.Provider value={{ lang, t, setLang }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() { return useContext(I18nContext) }