export default function Loading() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-center justify-between">
        <div className="h-8 w-48 rounded-lg bg-[var(--bg-hover)]" />
        <div className="h-8 w-24 rounded-lg bg-[var(--bg-hover)]" />
      </div>
      {/* Content skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] p-6 space-y-3">
            <div className="h-4 w-20 rounded bg-[var(--bg-hover)]" />
            <div className="h-8 w-32 rounded bg-[var(--bg-hover)]" />
            <div className="h-3 w-40 rounded bg-[var(--bg-hover)]" />
          </div>
        ))}
      </div>
      {/* Table skeleton */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] p-4 space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex gap-4">
            <div className="h-4 flex-1 rounded bg-[var(--bg-hover)]" />
            <div className="h-4 w-24 rounded bg-[var(--bg-hover)]" />
            <div className="h-4 w-16 rounded bg-[var(--bg-hover)]" />
          </div>
        ))}
      </div>
    </div>
  )
}