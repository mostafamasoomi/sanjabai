import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { faNum } from '@/lib/format'
import { useCatalog } from '@/lib/useCatalog'
import { modelCount } from '@/lib/claims'
import { useLandingOverrides, applyModuleOverride } from '@/lib/landingOverrides'
import {
  API_BASE_URL,
  MIN_TOPUP_LABEL_FA,
  MIN_TOPUP_LABEL_EN,
} from './constants'

/* ── FAQ ──────────────────────────────────────────────────────────────────── */

/* The first answer used to hardcode a fixed model count (docs/product-contract.md
   §4: model-count claims require a live catalog query). That one answer's
   `a` is now a function of the live count; every other item stays a plain
   string. `count` is `null` while the catalog is loading or on fetch
   failure (see `FAQ()` below for the Server Component / JSON-LD path, and
   `faqContent()` for the client-rendered accordion), in which case the
   answer omits the number rather than flashing "0". */
const FA = {
  items: [
    {
      q: 'چه مدل‌هایی در دسترس است؟',
      a: (count: number | null) =>
        count != null
          ? `در حال حاضر ${faNum(count)} مدل گفتگو، از جمله DeepSeek V4، Mistral Large، Gemini Flash، Llama 3.3، GPT-OSS، Gemma، MiMo، Kimi و Tencent Hy3. فهرست کامل به همراه تعرفه و اندازه‌ی زمینه‌ی هر مدل در صفحه‌ی مدل‌ها آمده است.`
          : 'در حال حاضر چند مدل گفتگو، از جمله DeepSeek V4، Mistral Large، Gemini Flash، Llama 3.3، GPT-OSS، Gemma، MiMo، Kimi و Tencent Hy3. فهرست کامل به همراه تعرفه و اندازه‌ی زمینه‌ی هر مدل در صفحه‌ی مدل‌ها آمده است.',
    },
    {
      q: 'چطور هزینه محاسبه می‌شود؟',
      a: 'به‌ازای توکن. هر مدل قیمت ورودی و خروجی جداگانه‌ای به تومان به ازای هر یک میلیون توکن دارد. کیف پولتان را شارژ می‌کنید و هزینه‌ی هر درخواست از همان کسر می‌شود؛ خبری از اشتراک ماهانه نیست.',
    },
    {
      q: 'برای شروع باید هزینه بدهم؟',
      a: `ساخت حساب رایگان است و برای دیدن پنل، فهرست مدل‌ها و مستندات هیچ پرداختی لازم نیست. برای ارسال درخواست به مدل‌ها باید کیف پول را شارژ کنید؛ حداقل مبلغ شارژ ${MIN_TOPUP_LABEL_FA} است.`,
    },
    {
      q: 'پرداخت چطور انجام می‌شود؟',
      a: 'با کارت‌های بانکی ایران و به تومان. مبالغ پیشنهادی شارژ ۱۰۰ هزار، ۵۰۰ هزار، ۱ میلیون و ۵ میلیون تومان است، ولی می‌توانید هر مبلغ دلخواهی وارد کنید. برای مشتریان سازمانی فاکتور رسمی صادر می‌شود.',
    },
    {
      q: 'API چطور کار می‌کند؟',
      a: `API ما با OpenAI سازگار است. کافی است آدرس پایه را روی ${API_BASE_URL} بگذارید و کلید Sanjabai خودتان را جایگزین کنید؛ بقیه‌ی کد دست‌نخورده باقی می‌ماند. استریم و embeddings هم پشتیبانی می‌شوند.`,
    },
    {
      q: 'به فیلترشکن نیاز دارم؟',
      a: 'خیر. درخواست‌ها از زیرساخت ما به مدل‌ها می‌رود، پس از داخل ایران و بدون هیچ ابزار جانبی کار می‌کند — چه در مرورگر و چه از طریق API.',
    },
  ],
}

const EN: typeof FA = {
  items: [
    {
      q: 'Which models are available?',
      a: (count) =>
        count != null
          ? `${count} chat model${count === 1 ? '' : 's'} today, including DeepSeek V4, Mistral Large, Gemini Flash, Llama 3.3, GPT-OSS, Gemma, MiMo, Kimi, and Tencent Hy3. The full list, with pricing and context size for each model, is on the models page.`
          : 'Multiple chat models are available today, including DeepSeek V4, Mistral Large, Gemini Flash, Llama 3.3, GPT-OSS, Gemma, MiMo, Kimi, and Tencent Hy3. The full list, with pricing and context size for each model, is on the models page.',
    },
    {
      q: 'How is cost calculated?',
      a: "Per token. Each model has separate input and output prices in Toman per one million tokens. You top up your wallet and each request is billed from that balance — there's no monthly subscription.",
    },
    {
      q: 'Do I have to pay to get started?',
      a: `Creating an account is free, and viewing the dashboard, model list, and docs costs nothing. You need to top up your wallet to send requests to models; the minimum top-up is ${MIN_TOPUP_LABEL_EN}.`,
    },
    {
      q: 'How does payment work?',
      a: 'With Iranian bank cards, in Toman. Suggested top-up amounts are 100,000, 500,000, 1,000,000, and 5,000,000 Toman, but you can enter any amount you want. A formal invoice is issued for business customers.',
    },
    {
      q: 'How does the API work?',
      a: `Our API is OpenAI-compatible. Just point the base URL to ${API_BASE_URL} and swap in your own Sanjabai key; the rest of your code stays unchanged. Streaming and embeddings are supported too.`,
    },
    {
      q: 'Do I need a VPN?',
      a: "No. Requests go from our infrastructure to the models, so it works from inside Iran without any extra tool — in the browser or through the API.",
    },
  ],
}

const faqContentFor = dict(FA, EN)

/** Resolves the FAQ items for a language, filling in the live model count in
 *  the first answer — see the hook-inside-a-plain-name note in
 *  Hero.strings.ts. */
function useFaqContent(lang: Lang) {
  const { models, loading } = useCatalog()
  const overrides = useLandingOverrides()
  const count = !loading && modelCount(models) > 0 ? modelCount(models) : null
  const base = faqContentFor(lang)
  const resolved = { items: base.items.map((item) => ({ q: item.q, a: typeof item.a === 'function' ? item.a(count) : item.a })) }
  return applyModuleOverride('faq', lang, resolved, overrides)
}

export const faqContent = useFaqContent

/** Today's static FA/EN values with the live-count leaf resolved against
 *  `count = null` — admin editor placeholders only, see the matching
 *  comment in comparison.ts's comparisonStaticDefaults. */
function resolveFaqItems(base: typeof FA) {
  return { items: base.items.map((item) => ({ q: item.q, a: typeof item.a === 'function' ? item.a(null) : item.a })) }
}
export const faqStaticDefaults = {
  fa: resolveFaqItems(FA),
  en: resolveFaqItems(EN),
}

/** Backward-compatible flat array for the JSON-LD FAQ schema in app/page.tsx
 *  (a Server Component outside this scope). Structured data isn't rendered
 *  through the language toggle, so it stays Persian — the same array the
 *  Persian UI already showed, just re-derived from FA.items instead of
 *  duplicated.
 *
 *  Now a function of the live model count instead of a flat array: a Server
 *  Component can't call the `useCatalog()` hook the client-rendered accordion
 *  above uses, so app/page.tsx fetches the count itself
 *  (`fetchLiveModelCount()`) and passes it in here. `count` is `null` when
 *  that fetch fails, in which case the first answer omits the number. */
export function FAQ(count: number | null) {
  return FA.items.map((item) => ({ q: item.q, a: typeof item.a === 'function' ? item.a(count) : item.a }))
}
