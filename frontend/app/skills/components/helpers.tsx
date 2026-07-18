import { Icon } from '@/components/ui/Icon'

export function renderStars(rating: number, size = 14) {
  const stars = []
  for (let i = 1; i <= 5; i++) {
    stars.push(
      <Icon
        key={i}
        name="sparkles"
        size={size}
        className={i <= Math.round(rating) ? 'text-[var(--warning)]' : 'text-[var(--text-muted)]'}
        style={{ opacity: i <= Math.round(rating) ? 1 : 0.3 }}
      />
    )
  }
  return stars
}