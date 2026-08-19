import type { Metadata } from 'next'

import { LandingHeader } from '@/components/landing/LandingHeader'
import { Hero } from '@/components/landing/Hero'
import { ProviderMarquee } from '@/components/landing/ProviderMarquee'
import { StatsBand } from '@/components/landing/StatsBand'
import { FeatureBento } from '@/components/landing/FeatureBento'
import { CapabilityShowcase } from '@/components/landing/CapabilityShowcase'
import { HowItWorks } from '@/components/landing/HowItWorks'
import { ApiSection } from '@/components/landing/ApiSection'
import { PricingSection } from '@/components/landing/PricingSection'
import { ComparisonSection } from '@/components/landing/ComparisonSection'
import { FaqSection } from '@/components/landing/FaqSection'
import { ClosingCta } from '@/components/landing/ClosingCta'
import { SiteFooter } from '@/components/landing/SiteFooter'
import { FAQ } from '@/components/landing/content'

import './landing.css'

export const metadata: Metadata = {
  title: 'Sanjabai — دسترسی به همه‌ی مدل‌های هوش مصنوعی با یک اشتراک',
  description:
    'با ۲۳ مدل هوش مصنوعی — DeepSeek، Mistral، Gemini، Llama و بیشتر — چت کنید، عامل بسازید و همه را با یک API سازگار با OpenAI به محصولتان وصل کنید. پرداخت به تومان به‌ازای مصرف، بدون اشتراک ماهانه و بدون نیاز به فیلترشکن.',
  alternates: { canonical: '/' },
}

const faqJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: FAQ.map((item) => ({
    '@type': 'Question',
    name: item.q,
    acceptedAnswer: { '@type': 'Answer', text: item.a },
  })),
}

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
        <CapabilityShowcase />
        <HowItWorks />
        <ApiSection />
        <PricingSection />
        <ComparisonSection />
        <FaqSection />
        <ClosingCta />
      </main>

      <SiteFooter />

      <noscript>
        <style dangerouslySetInnerHTML={{ __html: '.lp-reveal{opacity:1!important;transform:none!important}' }} />
      </noscript>

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />
    </div>
  )
}
