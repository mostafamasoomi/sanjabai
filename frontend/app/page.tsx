import type { Metadata } from 'next'

import { LandingHeader } from '@/components/landing/LandingHeader'
import { Hero } from '@/components/landing/Hero'
import { ProviderMarquee } from '@/components/landing/ProviderMarquee'
import { StatsBand } from '@/components/landing/StatsBand'
import { FeatureBento } from '@/components/landing/FeatureBento'
import { HowItWorks } from '@/components/landing/HowItWorks'
import { ApiSection } from '@/components/landing/ApiSection'
import { PricingSection } from '@/components/landing/PricingSection'
import { FaqSection } from '@/components/landing/FaqSection'
import { ClosingCta } from '@/components/landing/ClosingCta'
import { SiteFooter } from '@/components/landing/SiteFooter'
import { FAQ } from '@/components/landing/content'

import './landing.css'

export const metadata: Metadata = {
  title: 'Multiai — دسترسی به همه‌ی مدل‌های هوش مصنوعی با یک اشتراک',
  description:
    'با GPT-4o، Claude، Gemini، DeepSeek و بیش از ۲۰ مدل دیگر چت کنید، عامل هوش مصنوعی بسازید و همه را با یک API سازگار با OpenAI به محصولتان وصل کنید. پرداخت ریالی، بدون نیاز به فیلترشکن.',
  alternates: { canonical: '/' },
}

/**
 * Structured data for the FAQ. Generated from the same array the section
 * renders, so the two can never drift apart.
 */
const faqJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: FAQ.map((item) => ({
    '@type': 'Question',
    name: item.q,
    acceptedAnswer: { '@type': 'Answer', text: item.a },
  })),
}

/**
 * The marketing page.
 *
 * Everything below is a server component except the four sections that need
 * state (header, hero preview, API tabs, pricing toggle, FAQ accordion), so
 * the bulk of the page ships as HTML with no JavaScript attached.
 */
export default function LandingPage() {
  return (
    <div className="lp">
      <LandingHeader />

      <main>
        <Hero />

        <div className="lp-section--soft">
          <ProviderMarquee />
        </div>

        <section className="lp-section">
          <div className="lp-container">
            <StatsBand />
          </div>
        </section>

        <FeatureBento />
        <HowItWorks />
        <ApiSection />
        <PricingSection />
        <FaqSection />
        <ClosingCta />
      </main>

      <SiteFooter />

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />
    </div>
  )
}
