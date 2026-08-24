import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
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
  return (
    <div className="card dash-span-4">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <span className="text-[var(--accent)]">
          <Icon name="dashboard" size={18} />
        </span>
        <h2 className="card-title">دسترسی سریع</h2>
      </div>
      <div className="flex flex-col gap-3">
        <QuickAction
          icon="chat"
          label="شروع مکالمه"
          description="گفتگو با هوش مصنوعی"
          onClick={onChat}
        />
        <QuickAction
          icon="wallet"
          label="کیف پول"
          description="شارژ و مدیریت حساب"
          onClick={onWallet}
        />
        <QuickAction
          icon="models"
          label="مدل‌ها"
          description={`${faNum(modelCount)} مدل در دسترس`}
          onClick={onModels}
        />
        <QuickAction
          icon="payment"
          label="خرید بسته اعتباری"
          description="خرید بسته اعتباری ویژه"
          onClick={onCreditPackages}
        />
        <QuickAction
          icon="settings"
          label="تنظیمات صورتحساب"
          description="مدیریت پرداخت به ازای مصرف"
          onClick={onBillingSettings}
        />
      </div>
    </div>
  )
}
