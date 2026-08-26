import { dict } from '@/lib/i18n'
import {
  API_BASE_URL,
  MIN_TOPUP_LABEL_FA,
  MIN_TOPUP_LABEL_EN,
} from './constants'

/* ── FAQ ──────────────────────────────────────────────────────────────────── */

const FA = {
  items: [
    {
      q: 'چه مدل‌هایی در دسترس است؟',
      a: 'در حال حاضر ۲۳ مدل گفتگو، از جمله DeepSeek V4، Mistral Large، Gemini Flash، Llama 3.3، GPT-OSS، Gemma، MiMo، Kimi و Tencent Hy3. فهرست کامل به همراه تعرفه و اندازه‌ی زمینه‌ی هر مدل در صفحه‌ی مدل‌ها آمده است.',
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
      a: '23 chat models today, including DeepSeek V4, Mistral Large, Gemini Flash, Llama 3.3, GPT-OSS, Gemma, MiMo, Kimi, and Tencent Hy3. The full list, with pricing and context size for each model, is on the models page.',
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

export const faqContent = dict(FA, EN)

/** Backward-compatible flat array for the JSON-LD FAQ schema in app/page.tsx
 *  (a Server Component outside this scope). Structured data isn't rendered
 *  through the language toggle, so it stays Persian — the same array the
 *  Persian UI already showed, just re-derived from FA.items instead of
 *  duplicated. */
export const FAQ = FA.items
