/* ═══════════════════════════════════════════════════════════════════════════
   Card wrapper with fade-in animation
   Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function FadeInCard({
  children,
  style,
  delay = 0,
  className,
}: {
  children: React.ReactNode
  style?: React.CSSProperties
  delay?: number
  className?: string
}) {
  return (
    <div
      className={`fade-in ${className || ''}`}
      style={{ animationDelay: `${delay}ms`, ...style }}
    >
      {children}
    </div>
  )
}
