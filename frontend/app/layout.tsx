import type { Metadata } from 'next'
import localFont from 'next/font/local'
import './globals.css'

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
  title: 'MultiAI — The complete animation stack.',
  description: 'Point at your live site, animate it visually, and walk away with clean, zero-dependency code. Scroll, hover, text, cursors — all of it.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={`${freigeist.variable} ${cirka.variable} ${jetbrains.variable}`}>
      <body className="antialiased">
        {children}
      </body>
    </html>
  )
}
