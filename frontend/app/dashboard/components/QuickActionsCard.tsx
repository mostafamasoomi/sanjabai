'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { quickActionsCardStrings } from './QuickActionsCard.strings'
import { QuickAction } from './QuickAction'

/* ═══════════════════════════════════════════════════════════════
   Quick Actions
   ═══════════════════════════════════════════════════════════════ */

export function QuickActionsCard({
  modelCount,
  onChat,
  onWallet,
  onModels,
  onCreditPackages,
  onBillingSettings,
}: {
  modelCount: number
  onChat: () => void
  onWallet: () => void
  onModels: () => void
  onCreditPackages: () => void
  onBillingSettings: () => void
}) {
  const lang = useLang()
  const s = quickActionsCardStrings(lang)
  const f = fmt(lang)

  return (
    <div className="card dash-span-4">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <span className="text-[var(--accent)]">
          <Icon name="dashboard" size={18} />
        </span>
        <h2 className="card-title">{s.title}</h2>
      </div>
      <div className="flex flex-col gap-3">
        <QuickAction
          icon="chat"
          label={s.chatLabel}
          description={s.chatDesc}
          onClick={onChat}
        />
        <QuickAction
          icon="wallet"
          label={s.walletLabel}
          description={s.walletDesc}
          onClick={onWallet}
        />
        <QuickAction
          icon="models"
          label={s.modelsLabel}
          description={s.modelsDesc(f.num(modelCount))}
          onClick={onModels}
        />
        <QuickAction
          icon="payment"
          label={s.creditLabel}
          description={s.creditDesc}
          onClick={onCreditPackages}
        />
        <QuickAction
          icon="settings"
          label={s.billingLabel}
          description={s.billingDesc}
          onClick={onBillingSettings}
        />
      </div>
    </div>
  )
}
