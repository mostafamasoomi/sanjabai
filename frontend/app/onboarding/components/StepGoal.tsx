import { Icon } from '@/components/ui/Icon'
import { GOALS } from '../constants'

export function StepGoal({
  goalId,
  onSelect,
  onBack,
  onNext,
}: {
  goalId: string | null
  onSelect: (id: string) => void
  onBack: () => void
  onNext: () => void
}) {
  return (
    <div className="fade-in slide-up">
      <h2 className="text-2xl sm:text-3xl font-bold text-center mb-2">قصد دارید چه کاری کنید؟</h2>
      <p className="text-center text-[var(--text-secondary)] mb-6">
        بر اساس انتخاب شما، بهترین مدل را پیشنهاد می‌دهیم.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {GOALS.map((g) => {
          const selected = g.id === goalId
          return (
            <button
              key={g.id}
              onClick={() => onSelect(g.id)}
              className={`card card-interactive text-right flex items-center gap-4 p-4 cursor-pointer transition-all ${
                selected
                  ? 'border-[var(--accent)] bg-[var(--accent-dim)] shadow-[var(--shadow-glow)]'
                  : ''
              }`}
            >
              <div
                className={`shrink-0 w-12 h-12 rounded-xl flex items-center justify-center transition-colors ${
                  selected
                    ? 'bg-[var(--accent)] text-white'
                    : 'bg-[var(--bg-elevated)] text-[var(--accent)]'
                }`}
              >
                <Icon name={g.icon} size={24} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-base">{g.label}</div>
                <div className="text-xs text-[var(--text-muted)] mt-0.5">{g.hint}</div>
              </div>
              {selected && (
                <Icon name="check" size={20} className="text-[var(--accent)] shrink-0" />
              )}
            </button>
          )
        })}
      </div>
      <div className="flex items-center justify-between mt-8 gap-3">
        <button className="btn btn-ghost" onClick={onBack}>
          <Icon name="arrowRight" size={16} />
          قبلی
        </button>
        <button
          className="btn btn-primary btn-lg"
          disabled={!goalId}
          onClick={onNext}
        >
          ادامه
          <Icon name="arrowLeft" size={18} />
        </button>
      </div>
    </div>
  )
}
