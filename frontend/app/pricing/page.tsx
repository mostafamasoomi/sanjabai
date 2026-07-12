'use client'

export default function PricingPage() {
  const plans = [
    { name: 'رایگان', price: '۰', tokens: '۱۰۰K', features: ['دسترسی به مدلهای کوچک', 'هر روز ۱۰۰ هزار توکن'] },
    { name: 'پایه', price: '۱۹۹,۰۰۰', tokens: '۱M', features: ['دسترسی به مدلهای پیشرفته', 'هر ماه ۱ میلیون توکن', 'پشتیبانی ایمیلی'] },
    { name: 'حرفهای', price: '۵۹۹,۰۰۰', tokens: '۵M', features: ['اولویت در صف', 'هر ماه ۵ میلیون توکن', 'پشتیبانی اختصاصی'] }
  ]
  return (
    <main className="min-h-screen bg-[var(--bg)] p-6">
      <div className="mx-auto max-w-4xl">
        <h1 className="text-2xl font-bold mb-6 text-[var(--text-primary)]">پلنها و قیمتها</h1>
        <div className="grid gap-4 sm:grid-cols-3">
          {plans.map((p, i) => (
            <div key={p.name} className={`rounded-2xl border p-5 ${i === 1 ? 'border-[var(--accent)] bg-[var(--accent-dim)]' : 'border-[var(--border)] bg-[var(--bg-elev)]'}`}>
              <div className="text-sm text-[var(--text-secondary)]">پلن {p.name}</div>
              <div className="text-3xl font-bold mt-2 text-[var(--text-primary)]">{p.price} <span className="text-xs text-[var(--text-muted)]">تومان</span></div>
              <div className="text-xs text-[var(--accent)] mt-1">{p.tokens} توکن</div>
              <ul className="mt-4 space-y-2 text-sm text-[var(--text-secondary)]">
                {p.features.map((f) => (<li key={f}>• {f}</li>))}
              </ul>
              <button className={`mt-5 w-full rounded-xl py-2 text-sm font-medium transition-colors ${i === 1 ? 'bg-[var(--accent)] text-white hover:opacity-90' : 'bg-[var(--bg-hover)] text-[var(--text-primary)] hover:bg-[var(--border)]'}`}>
                انتخاب پلن
              </button>
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
