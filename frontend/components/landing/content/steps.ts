import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { useLandingOverrides, applyModuleOverride } from '@/lib/landingOverrides'
import { MIN_TOPUP_LABEL_FA, MIN_TOPUP_LABEL_EN } from './constants'

/* ── Steps ────────────────────────────────────────────────────────────────── */

const FA = {
  items: [
    {
      title: 'حساب بسازید',
      desc: 'با ایمیل ثبت‌نام کنید. ساخت حساب رایگان است و هیچ کارت اعتباری‌ای لازم ندارد.',
    },
    {
      title: 'کیف پول را شارژ کنید',
      desc: `از ${MIN_TOPUP_LABEL_FA} به بالا، با کارت بانکی ایرانی. هر مبلغی که شارژ کنید تا وقتی مصرف نشود سر جایش می‌ماند.`,
    },
    {
      title: 'وصل شوید یا شروع به چت کنید',
      desc: 'در مرورگر کار کنید، یا یک کلید API بسازید و همان مدل‌ها را به محصول خودتان وصل کنید.',
    },
  ],
}

const EN: typeof FA = {
  items: [
    {
      title: 'Create an account',
      desc: 'Sign up with your email. Creating an account is free and needs no credit card.',
    },
    {
      title: 'Top up your wallet',
      desc: `From ${MIN_TOPUP_LABEL_EN} up, with an Iranian bank card. Whatever you top up stays there until you use it.`,
    },
    {
      title: 'Connect, or start chatting',
      desc: 'Work in the browser, or create an API key and connect the same models to your own product.',
    },
  ],
}

const stepsContentFor = dict(FA, EN)

/** Resolves the "how it works" steps for a language, applying any
 *  admin-stored override. */
function useStepsContent(lang: Lang) {
  const overrides = useLandingOverrides()
  return applyModuleOverride('steps', lang, stepsContentFor(lang), overrides)
}

export const stepsContent = useStepsContent

/** Today's static FA/EN values — admin editor placeholders only, see the
 *  matching comment in hero.ts. */
export const stepsStaticDefaults = { fa: FA, en: EN }
