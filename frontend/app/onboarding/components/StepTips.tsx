import { Icon } from '@/components/ui/Icon'

export function StepTips({
  redirecting,
  onBack,
  onFinish,
}: {
  redirecting: boolean
  onBack: () => void
  onFinish: () => void
}) {
  return (
    <div className="fade-in slide-up">
      <h2 className="text-2xl sm:text-3xl font-bold text-center mb-2">سه نکته که کار را راه میاندازد</h2>
      <p className="text-center text-[var(--text-secondary)] mb-6">
        چند ثانیه دیگر و آماده میکارید.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="card p-5">
          <div className="w-11 h-11 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
            <Icon name="search" size={22} className="text-[var(--accent)]" />
          </div>
          <div className="font-semibold mb-1">منوی سریع</div>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            با زدن{' '}
            <kbd className="text-[11px] bg-[var(--bg-surface)] px-1.5 py-0.5 rounded border border-[var(--border)]">
              ⌘K
            </kbd>{' '}
            (یا Ctrl+K) به همه بخشها سریع بروید.
          </p>
        </div>

        <div className="card p-5">
          <div className="w-11 h-11 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
            <Icon name="models" size={22} className="text-[var(--accent)]" />
          </div>
          <div className="font-semibold mb-1">تعویض مدل</div>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            مدل فعال را از نوار بالای صفحه چت با یک کلیک عوض کنید.
          </p>
        </div>

        <div className="card p-5">
          <div className="w-11 h-11 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
            <Icon name="wallet" size={22} className="text-[var(--accent)]" />
          </div>
          <div className="font-semibold mb-1">موجودی حساب</div>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            هزینه هر چت و موجودی خود را از بخش «کیف پول» دنبال کنید.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between mt-8 gap-3">
        <button className="btn btn-ghost" onClick={onBack}>
          <Icon name="arrowRight" size={16} />
          قبلی
        </button>
        <button className="btn btn-primary btn-lg" onClick={onFinish} disabled={redirecting}>
          {redirecting ? 'در حال انتقال...' : 'شروع چت'}
          <Icon name="send" size={18} />
        </button>
      </div>
    </div>
  )
}
