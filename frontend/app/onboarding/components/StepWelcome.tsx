import { Icon } from '@/components/ui/Icon'

export function StepWelcome({ userName, onNext }: { userName: string; onNext: () => void }) {
  return (
    <div className="text-center fade-in slide-up">
      <div className="mx-auto w-16 h-16 rounded-2xl bg-[var(--accent-dim)] flex items-center justify-center mb-6">
        <Icon name="sparkles" size={32} className="text-[var(--accent)]" />
      </div>
      <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
        {userName ? (
          <>
            خوش آمدید، <span className="text-gradient">{userName}</span>
          </>
        ) : (
          <>
            به <span className="text-gradient">Sanjabai</span> خوش آمدید
          </>
        )}
      </h1>
      <p className="text-[var(--text-secondary)] mt-3 max-w-md mx-auto leading-relaxed">
        چند ثانیه وقت بدهید تا همهچیز را برای شما آماده کنیم. فقط چند قدم ساده تا شروع چت با
        بهترین مدل‌های هوش مصنوعی دنیا.
      </p>
      <button className="btn btn-primary btn-lg mt-8" onClick={onNext}>
        بیا شروع کنیم
        <Icon name="arrowLeft" size={18} />
      </button>
    </div>
  )
}
