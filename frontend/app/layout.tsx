'use client'
import Script from 'next/script'
import './globals.css'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" data-theme="dark" suppressHydrationWarning>
      <body className="antialiased">
        {children}
        <Script src="/js/matter.min.js" strategy="beforeInteractive" />
      </body>
    </html>
  )
}