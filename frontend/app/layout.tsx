import type { Metadata, Viewport } from 'next'
import { AppShell } from '@/components/AppShell'
import { fetchLiveModelCount } from '@/lib/claims'
import { faNum } from '@/lib/format'
import './globals.css'
import '../styles-chat-sidebar.css'

/**
 * Model-count claims require a live catalog query (docs/product-contract.md
 * §4) — the number used to be hand-typed here and drifted from the real
 * catalog every time a model was added or pulled. `fetchLiveModelCount()`
 * hits the backend directly (this runs before any Next.js rewrite exists)
 * and returns `null` on any failure, in which case the copy below omits the
 * number entirely rather than showing a stale or fabricated one.
 */
export async function generateMetadata(): Promise<Metadata> {
  const count = await fetchLiveModelCount()
  const description =
    count != null
      ? `دسترسی به ${faNum(count)} مدل هوش مصنوعی از یک پنل: چت چندمدلی، ساخت عامل، و API سازگار با OpenAI — با پرداخت به تومان به‌ازای مصرف و پشتیبانی فارسی.`
      : 'دسترسی به مدل‌های متعدد هوش مصنوعی از یک پنل: چت چندمدلی، ساخت عامل، و API سازگار با OpenAI — با پرداخت به تومان به‌ازای مصرف و پشتیبانی فارسی.'
  const ogDescription =
    count != null
      ? `چت با ${faNum(count)} مدل هوش مصنوعی، ساخت عامل، و یک API سازگار با OpenAI. پرداخت به تومان به‌ازای مصرف، بدون فیلترشکن.`
      : 'چت با مدل‌های متعدد هوش مصنوعی، ساخت عامل، و یک API سازگار با OpenAI. پرداخت به تومان به‌ازای مصرف، بدون فیلترشکن.'

  return {
    metadataBase: new URL('https://sanjabai.com'),
    title: {
      default: 'Sanjabai — پلتفرم هوش مصنوعی فارسی',
      template: '%s | Sanjabai',
    },
    description,
    applicationName: 'Sanjabai',
    // Only models the platform actually serves (backend/litellm_config.yaml).
    keywords: ['هوش مصنوعی', 'DeepSeek', 'Mistral', 'Gemini', 'Llama', 'API هوش مصنوعی'],
    openGraph: {
      type: 'website',
      locale: 'fa_IR',
      siteName: 'Sanjabai',
      title: 'Sanjabai — پلتفرم هوش مصنوعی فارسی',
      description: ogDescription,
    },
    robots: { index: true, follow: true },
  }
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#0e0906' },
    { media: '(prefers-color-scheme: light)', color: '#fdfaf5' },
  ],
  width: 'device-width',
  initialScale: 1,
}

/**
 * Applies the saved theme and language before first paint.
 *
 * Both used to be applied from a `useEffect` in <ThemeToggle> / <LanguageToggle>,
 * which meant a light-mode user loaded the whole dark palette and then watched
 * it flip. Inlined and synchronous, so the correct palette is in place on the
 * very first frame. Defaults match the SSR markup (dark, Persian, RTL) so
 * hydration stays consistent for a first-time visitor.
 */
const themeBootstrap = `
(function () {
  try {
    var theme = localStorage.getItem('theme');
    if (theme !== 'light' && theme !== 'dark') theme = 'dark';
    document.documentElement.setAttribute('data-theme', theme);

    var lang = localStorage.getItem('lang');
    if (lang !== 'en') lang = 'fa';
    document.documentElement.setAttribute('lang', lang);
    document.documentElement.setAttribute('dir', lang === 'fa' ? 'rtl' : 'ltr');
  } catch (e) {}
})();
`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" data-theme="dark" suppressHydrationWarning>
      <head>
        {/* TEMPORARY — payment gateway asked for the verification code as the
            page <title> ("عنوان تایید"). Static JSX, not generateMetadata's
            `title`, for the same streaming reason as the enamad meta tag
            below. REMOVE this line after clicking "تایید عنوان" in the
            gateway panel — it overrides the real title while present. */}
        <title>22040799</title>
        {/* Payment gateway domain-verification tag. Must be a static JSX tag
            here, not part of generateMetadata's returned object — that path
            renders async and streams into <head> via client JS, which is
            invisible to a bot that doesn't execute JavaScript. */}
        <meta name="enamad" content="22040799" />
        {/* The two weights used above the fold. Everything else in the family
            loads normally via @font-face in globals.css. */}
        <link
          rel="preload"
          href="/fonts/Vazirmatn-Medium.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <link
          rel="preload"
          href="/fonts/Vazirmatn-Bold.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      {/* AppShell owns <AuthProvider>. It was previously imported by nothing,
          so every page fell back to the default auth context — whose login()
          and signup() are no-ops that resolve, making the auth forms appear to
          succeed while doing nothing. It also supplies the sidebar, topbar and
          the .layout-content container that pages rely on for their gutters. */}
      <body className="antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  )
}
