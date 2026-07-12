'use client'

export default function TopUpPage() {
  const amounts = [50000, 100000, 200000, 500000]
  return (
    <main className="min-h-screen bg-[var(--bg)] p-6">
      <div className="mx-auto max-w-xl rounded-2xl border border-[var(--border)] bg-[var(--bg-elev)] p-6">
        <h1 className="text-2xl font-bold mb-2 text-[var(--text-primary)]">شارژ کیف پول</h1>
        <p className="text-sm text-[var(--text-secondary)] mb-6">مبلغ مورد نظر را انتخاب کنید:</p>
        <div className="grid grid-cols-2 gap-3">
          {amounts.map((amount) => (
            <div key={amount} className="rounded-2xl border border-[var(--border)] bg-[var(--bg)] p-4 flex items-center justify-between">
              <div>
                <div className="font-bold text-[var(--text-primary)]">{amount.toLocaleString('fa-IR')}</div>
                <div className="text-xs text-[var(--text-muted)]">تومان</div>
              </div>
              <button className="rounded-xl bg-[var(--accent)] text-white px-3 py-2 text-sm hover:opacity-90 transition-opacity">انتخاب</button>
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
