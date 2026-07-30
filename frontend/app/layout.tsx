import type { Metadata, Viewport } from 'next'
import './globals.css'
import '../styles-chat-sidebar.css'

export const metadata: Metadata = {
  metadataBase: new URL('https://multiai.ir'),
  title: {
    default: 'Multiai — پلتفرم هوش مصنوعی فارسی',
    template: '%s | Multiai',
  },
  description:
    'دسترسی به بهترین مدل‌های هوش مصنوعی جهان با یک اشتراک: چت چندمدلی، ساخت عامل، و API سازگار با OpenAI — با پرداخت ریالی و پشتیبانی فارسی.',
  applicationName: 'Multiai',
  keywords: ['هوش مصنوعی', 'چت جی پی تی', 'GPT-4o', 'Claude', 'Gemini', 'API هوش مصنوعی'],
  openGraph: {
    type: 'website',
    locale: 'fa_IR',
    siteName: 'Multiai',
    title: 'Multiai — پلتفرم هوش مصنوعی فارسی',
    description:
      'چت با بیش از ۲۰ مدل هوش مصنوعی، ساخت عامل، و یک API سازگار با OpenAI. پرداخت ریالی، بدون فیلترشکن.',
  },
  robots: { index: true, follow: true },
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#07070e' },
    { media: '(prefers-color-scheme: light)', color: '#fbfbfe' },
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
      <body className="antialiased">{children}</body>
    </html>
  )
}
