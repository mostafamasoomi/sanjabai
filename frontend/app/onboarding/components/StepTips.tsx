'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { navIcon } from '@/lib/i18n'
import { stepTipsStrings } from './StepTips.strings'

export function StepTips({
  redirecting,
  onBack,
  onFinish,
}: {
  redirecting: boolean
  onBack: () => void
  onFinish: () => void
}) {
  const lang = useLang()
  const s = stepTipsStrings(lang)

  return (
    <div className="fade-in slide-up">
      <h2 className="text-2xl sm:text-3xl font-bold text-center mb-2">{s.title}</h2>
      <p className="text-center text-[var(--text-secondary)] mb-6">
        {s.subtitle}
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="card p-5">
          <div className="w-11 h-11 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
            <Icon name="search" size={22} className="text-[var(--accent)]" />
          </div>
          <div className="font-semibold mb-1">{s.quickMenuTitle}</div>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            {s.quickMenuPrefix}
            <kbd className="text-[11px] bg-[var(--bg-surface)] px-1.5 py-0.5 rounded border border-[var(--border)]">
              ⌘K
            </kbd>
            {s.quickMenuSuffix}
          </p>
        </div>

        <div className="card p-5">
          <div className="w-11 h-11 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
            <Icon name="models" size={22} className="text-[var(--accent)]" />
          </div>
          <div className="font-semibold mb-1">{s.switchModelTitle}</div>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            {s.switchModelBody}
          </p>
        </div>

        <div className="card p-5">
          <div className="w-11 h-11 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
            <Icon name="wallet" size={22} className="text-[var(--accent)]" />
          </div>
          <div className="font-semibold mb-1">{s.balanceTitle}</div>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            {s.balanceBody}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between mt-8 gap-3">
        <button className="btn btn-ghost" onClick={onBack}>
          <Icon name={navIcon(lang, 'back')} size={16} />
          {s.back}
        </button>
        <button className="btn btn-primary btn-lg" onClick={onFinish} disabled={redirecting}>
          {redirecting ? s.redirecting : s.startChat}
          <Icon name="send" size={18} />
        </button>
      </div>
    </div>
  )
}
