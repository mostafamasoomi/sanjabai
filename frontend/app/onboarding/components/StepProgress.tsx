'use client'

import { useLang } from '@/components/LanguageToggle'
import { STEP_LABELS_FA, STEP_LABELS_EN } from '../constants'

export function StepProgress({ step }: { step: number }) {
  const lang = useLang()
  const labels = lang === 'fa' ? STEP_LABELS_FA : STEP_LABELS_EN

  return (
    <div className="max-w-3xl w-full mx-auto px-5 sm:px-8 pb-2">
      <div className="flex items-center gap-2">
        {labels.map((label, i) => {
          const done = i < step
          const current = i === step
          return (
            <div key={label} className="flex-1">
              <div className="h-1 rounded-full overflow-hidden bg-[var(--bg-elevated)]">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: done || current ? '100%' : '0%',
                    background: current
                      ? 'linear-gradient(90deg, var(--accent), var(--accent-2))'
                      : 'var(--accent)',
                  }}
                />
              </div>
              <div
                className={`text-[11px] mt-1.5 ${
                  current
                    ? 'text-[var(--accent)] font-medium'
                    : done
                    ? 'text-[var(--text-secondary)]'
                    : 'text-[var(--text-muted)]'
                }`}
              >
                {label}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
