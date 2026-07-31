import type { Metadata, Viewport } from 'next'
import { AppShell } from '@/components/AppShell'
import './globals.css'
import '../styles-chat-sidebar.css'

export const metadata: Metadata = {
  metadataBase: new URL('https://multiai.ir'),
  title: {
    default: 'Sanjabai — پلتفرم هوش مصنوعی فارسی',
    template: '%s | Sanjabai',
  },
  description:
    'دسترسی به ۲۳ مدل هوش مصنوعی از یک پنل: چت چندمدلی، ساخت عامل، و API سازگار با OpenAI — با پرداخت به تومان به‌ازای مصرف و پشتیبانی فارسی.',
  applicationName: 'Sanjabai',
  // Only models the platform actually serves (backend/litellm_config.yaml).
  keywords: ['هوش مصنوعی', 'DeepSeek', 'Mistral', 'Gemini', 'Llama', 'API هوش مصنوعی'],
  openGraph: {
    type: 'website',
    locale: 'fa_IR',
    siteName: 'Sanjabai',
    title: 'Sanjabai — پلتفرم هوش مصنوعی فارسی',
    description:
      'چت با ۲۳ مدل هوش مصنوعی، ساخت عامل، و یک API سازگار با OpenAI. پرداخت به تومان به‌ازای مصرف، بدون فیلترشکن.',
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
