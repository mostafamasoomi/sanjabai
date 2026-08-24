import { Icon } from '@/components/ui/Icon'

type DangerZoneSectionProps = {
  isFa: boolean
}

export default function DangerZoneSection({ isFa }: DangerZoneSectionProps) {
  return (
    <div className="card profile-danger-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon name="warning" size={16} className="text-danger" />
        <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--danger)' }}>
          {isFa ? 'منطقه خطر' : 'Danger Zone'}
        </h2>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
        {isFa
          ? 'حذف حساب کاربری غیرقابل بازگشت است. تمام دادهها و تاریخچه شما حذف خواهد شد.'
          : 'Account deletion is permanent. All your data and history will be removed.'}
      </p>
      <button className="btn btn-danger" disabled style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <Icon name="trash" size={14} />
        {isFa ? 'حذف حساب (به‌زودی)' : 'Delete Account (coming soon)'}
      </button>
    </div>
  )
}
