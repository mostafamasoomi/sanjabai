import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { useLandingOverrides, applyModuleOverride } from '@/lib/landingOverrides'

/* ── Navigation ───────────────────────────────────────────────────────────── */

const FA = {
  links: [
    { label: 'امکانات', href: '#features' },
    { label: 'مدل‌ها', href: '/models' },
    { label: 'تعرفه‌ها', href: '/pricing' },
    { label: 'مستندات', href: '/developer' },
  ],
}

const EN: typeof FA = {
  links: [
    { label: 'Features', href: '#features' },
    { label: 'Models', href: '/models' },
    { label: 'Pricing', href: '/pricing' },
    { label: 'Docs', href: '/developer' },
  ],
}

const navContentFor = dict(FA, EN)

/** Resolves nav links for a language, applying any admin-stored override. */
function useNavContent(lang: Lang) {
  const overrides = useLandingOverrides()
  return applyModuleOverride('nav', lang, navContentFor(lang), overrides)
}

export const navContent = useNavContent

/** Today's static FA/EN values — admin editor placeholders only, see the
 *  matching comment in hero.ts. */
export const navStaticDefaults = { fa: FA, en: EN }
