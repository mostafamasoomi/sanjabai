'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { stepWelcomeStrings } from './StepWelcome.strings'

export function StepWelcome({ userName, onNext }: { userName: string; onNext: () => void }) {
  const lang = useLang()
  const s = stepWelcomeStrings(lang)

  return (
    <div className="text-center fade-in slide-up">
      <div className="mx-auto w-16 h-16 rounded-2xl bg-[var(--accent-dim)] flex items-center justify-center mb-6">
        <Icon name="sparkles" size={32} className="text-[var(--accent)]" />
      </div>
      <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
        {userName ? (
          <>
            {s.welcomeBackPrefix}<span className="text-gradient">{userName}</span>
          </>
        ) : (
          <>
            {s.welcomeToPrefix}<span className="text-gradient">Sanjabai</span>{s.welcomeToSuffix}
          </>
        )}
      </h1>
      <p className="text-[var(--text-secondary)] mt-3 max-w-md mx-auto leading-relaxed">
        {s.intro}
      </p>
      <button className="btn btn-primary btn-lg mt-8" onClick={onNext}>
        {s.start}
        <Icon name="arrowLeft" size={18} />
      </button>
    </div>
  )
}
