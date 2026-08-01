# Sanjhubai Design System

> Auto-generated from `:root` CSS variables in `app/globals.css`.
> Last updated: 2026-07-18
>
> **Scope:** this documents the *product* system — the tokens and component
> classes used by every signed-in page (dashboard, chat, models, wallet,
> admin). The marketing page has its own scoped system in `app/landing.css`,
> whose tokens are all prefixed `--lp-*` and whose classes are all prefixed
> `.lp-`. The two are deliberately independent; only the brand accent is
> shared. Regenerating this file will not pick up the landing tokens.

## Identity

- **Product**: Sanjhubai — Persian AI platform (پلتفرم هوش مصنوعی فارسی)
- **Direction**: RTL (`dir="rtl"`)
- **Language**: Farsi (`lang="fa"`)
- **Theme**: Dark-first
- **Font**: Vazirmatn (self-hosted, Persian/Arabic optimized)

## Color Palette

### Surface Hierarchy
| Token | Value | Usage |
|-------|-------|-------|
| `--bg-base` | `#05050a` | Background layer |
| `--bg-surface` | `#0c0c14` | Background layer |
| `--bg-elevated` | `#13131d` | Background layer |
| `--bg-overlay` | `#1a1a26` | Background layer |
| `--bg-hover` | `rgba(255, 255, 255, 0.05)` | Background layer |
| `--bg-active` | `rgba(255, 255, 255, 0.08)` | Background layer |
| `--bg-elev` | `var(--bg-elevated)` | Background layer |
| `--bg-elev2` | `var(--bg-overlay)` | Background layer |
| `--bg-base` | `#f7f7fb` | Background layer |
| `--bg-surface` | `#ffffff` | Background layer |
| `--bg-elevated` | `#f0f0f6` | Background layer |
| `--bg-overlay` | `#e8e8f0` | Background layer |
| `--bg-hover` | `rgba(0, 0, 0, 0.04)` | Background layer |
| `--bg-active` | `rgba(0, 0, 0, 0.07)` | Background layer |

### Text
| Token | Value | Usage |
|-------|-------|-------|
| `--text-primary` | `#f0f0f5` | Primary text |
| `--text-secondary` | `#a0a0b0` | Secondary text |
| `--text-muted` | `#606070` | Muted/disabled |
| `--text-on-accent` | `#ffffff` | Muted/disabled |
| `--text-dim` | `var(--text-muted)` | Muted/disabled |
| `--text-primary` | `#0d0d18` | Primary text |
| `--text-secondary` | `#555568` | Secondary text |
| `--text-muted` | `#8a8a9a` | Muted/disabled |
| `--text-on-accent` | `#ffffff` | Muted/disabled |

### Accent (Persian Indigo)
| Token | Value | Usage |
|-------|-------|-------|
| `--accent` | `#6366f1` | Accent color |
| `--accent-hover` | `#818cf8` | Accent color |
| `--accent-dim` | `rgba(99, 102, 241, 0.12)` | Accent color |
| `--accent-glow` | `rgba(99, 102, 241, 0.25)` | Accent color |
| `--accent-gradient` | `linear-gradient(135deg, #6366f1, #8b5cf6)` | Accent color |
| `--accent` | `#5457e8` | Accent color |
| `--accent-hover` | `#6366f1` | Accent color |
| `--accent-dim` | `rgba(84, 87, 232, 0.10)` | Accent color |
| `--accent-glow` | `rgba(84, 87, 232, 0.20)` | Accent color |
| `--accent-gradient` | `linear-gradient(135deg, #5457e8, #7c3aed)` | Accent color |

### Semantic
| Token | Value | Meaning |
|-------|-------|----------|
| `--positive` | `#34d399` | positive |
| `--warning` | `#fbbf24` | warning |
| `--danger` | `#f87171` | danger |
| `--info` | `#60a5fa` | info |
| `--positive` | `#059669` | positive |
| `--warning` | `#d97706` | warning |
| `--danger` | `#dc2626` | danger |
| `--info` | `#2563eb` | info |
| `--danger` | `hover {
  color: var(--danger)` | danger |

## Typography
| Token | Value |
|-------|-------|
| `--font-sans` | `'Vazirmatn', system-ui, -apple-system, sans-serif` |
| `--font-mono` | `'JetBrains Mono', 'Fira Code', monospace` |

## Spacing Scale
| Token | Pixels | Rem |
|-------|--------|-----|
| `--space-1` | 4px | 0.25rem |
| `--space-2` | 8px | 0.50rem |
| `--space-3` | 12px | 0.75rem |
| `--space-4` | 16px | 1.00rem |
| `--space-5` | 20px | 1.25rem |
| `--space-6` | 24px | 1.50rem |
| `--space-8` | 32px | 2.00rem |
| `--space-10` | 40px | 2.50rem |
| `--space-12` | 48px | 3.00rem |
| `--space-16` | 64px | 4.00rem |

## Border Radius
| Token | Value |
|-------|-------|
| `--radius-sm` | 6px |
| `--radius-md` | 10px |
| `--radius-lg` | 14px |
| `--radius-xl` | 20px |
| `--radius-full` | 9999px |

## Shadows
| Token | Value |
|-------|-------|
| `--shadow-sm` | 0 1px 2px rgba(0, 0, 0, 0.3) |
| `--shadow-md` | 0 4px 12px rgba(0, 0, 0, 0.4) |
| `--shadow-lg` | 0 8px 32px rgba(0, 0, 0, 0.5) |
| `--shadow-glow` | 0 0 20px var(--accent-glow) |
| `--shadow-sm` | 0 1px 2px rgba(0, 0, 0, 0.06) |
| `--shadow-md` | 0 4px 12px rgba(0, 0, 0, 0.08) |
| `--shadow-lg` | 0 8px 32px rgba(0, 0, 0, 0.12) |
| `--shadow-glow` | 0 0 20px var(--accent-glow) |

## Tailwind Usage

The Tailwind config (`tailwind.config.ts`) extends the default theme with these tokens.
Use semantic classes instead of arbitrary values:

```tsx
// ❌ Before (hard-coded)
<div style={{ color: 'var(--text-primary)', background: 'var(--bg-surface)' }}>

// ✅ After (Tailwind + design tokens)
<div className="text-primary bg-surface">
```

### Available Tailwind Classes
| Category | Classes |
|----------|---------|
| Colors | `text-primary`, `text-secondary`, `text-muted`, `text-accent`, `text-positive`, `text-danger`, `text-warning`, `text-info` |
| Backgrounds | `bg-base`, `bg-surface`, `bg-elevated`, `bg-overlay` |
| Borders | `border-border`, `border-border-strong` |
| Spacing | `gap-1` through `gap-16` (4px–64px) |
| Radius | `rounded-sm` (6px), `rounded-md` (10px), `rounded-lg` (14px), `rounded-xl` (20px) |
| Shadows | `shadow-sm`, `shadow-md`, `shadow-lg`, `shadow-glow` |
| Fonts | `font-sans` (Vazirmatn), `font-mono` (JetBrains Mono) |

## RTL Guidelines

- Use `text-end` / `text-start` instead of `text-right` / `text-left`
- Use `ms-*` / `me-*` (margin-start/end) instead of `ml-*` / `mr-*`
- Use `ps-*` / `pe-*` (padding-start/end) instead of `pl-*` / `pr-*`
- `flex-row` + `dir="rtl"` automatically flips layout
- Use CSS logical properties: `inset-inline-start` instead of `left`
