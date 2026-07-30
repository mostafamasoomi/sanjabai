import type { Metadata } from 'next'
import localFont from 'next/font/local'
import './globals.css'
import '../styles-chat-sidebar.css'
import { Suspense } from 'react'

const freigeist = localFont({
  src: [
    { path: '../public/fonts/freigeist/Freigeist-Medium.woff2', weight: '500', style: 'normal' },
    { path: '../public/fonts/freigeist/Freigeist-Bold.woff2', weight: '700', style: 'normal' },
    { path: '../public/fonts/freigeist/Freigeist-RegularItalic.woff2', weight: '400', style: 'italic' },
    { path: '../public/fonts/freigeist/Freigeist-LightItalic.woff2', weight: '300', style: 'italic' },
  ],
  variable: '--font-freigeist',
})

const cirka = localFont({
  src: [
    { path: '../public/fonts/cirka/PPCirka-Light.woff2', weight: '300', style: 'normal' },
    { path: '../public/fonts/cirka/PPCirka-Regular.woff2', weight: '400', style: 'normal' },
    { path: '../public/fonts/cirka/PPCirka-Bold.woff2', weight: '700', style: 'normal' },
  ],
  variable: '--font-cirka',
})

const jetbrains = localFont({
  src: [
    { path: '../public/fonts/jetbrains-mono/JetBrainsMono-Regular.woff2', weight: '400', style: 'normal' },
    { path: '../public/fonts/jetbrains-mono/JetBrainsMono-Medium.woff2', weight: '500', style: 'normal' },
  ],
  variable: '--font-mono',
})

export const metadata: Metadata = {
  title: 'MultiAI — One Platform, Every AI Model',
  description: 'Chat with GPT, Claude, DeepSeek, Gemini and 20+ AI models in one place. Upload documents, build skills, generate API keys.',
}

// Inline script to set dir based on lang on initial load (before React mounts)
const layoutScript = `
  (function() {
    try {
      const lang = localStorage.getItem('lang') || navigator.language || 'fa';
      const isFa = lang === 'fa' || lang.startsWith('fa');
      document.documentElement.dir = isFa ? 'rtl' : 'ltr';
      document.documentElement.lang = isFa ? 'fa' : 'en';
    } catch(e) {}
  })();
`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={`${freigeist.variable} ${cirka.variable} ${jetbrains.variable}`} suppressHydrationWarning>
      <script dangerouslySetInnerHTML={{__html: layoutScript}} />
      <body className="antialiased">{children}</body>
    </html>
  )
}
