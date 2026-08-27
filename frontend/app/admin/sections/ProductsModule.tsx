'use client'

import { useEffect } from 'react'
import dynamic from 'next/dynamic'
import { useLang } from '@/components/LanguageToggle'
import { api } from '../api'
import { t as label } from '../adminLabels'
import { PRODUCTS_TABS, DEFAULT_PRODUCTS_TAB, isProductsTab, type ProductsTab } from './productsTabs'

/* ═══════════════════════════════════════════════════════════════════════════
   Products — one sidebar entry, three sub-tabs, replacing the split
   «بسته‌ها» (Packages) and «پلن‌ها و اشتراک» (Plans & Subscriptions) nav
   entries. The owner decided (session 23, recorded) to retire the
   plan/subscription concept entirely: `credit_packages` is the only
   product concept from here on, so there is nothing left for a standalone
   plans screen to show. PlansSection.tsx and PlansSection.strings.ts are
   deleted outright, not folded in here as a sub-tab.

   Deliberately a SHELL, not a merge, same as ModelsModule.tsx: each
   sub-tab still renders its own original section file, untouched. That
   keeps every file under the 500-line house cap and means only the
   visible sub-tab's endpoints are ever hit.

   Three sub-tabs, in the order the work happens in -- edit what a package
   sells and costs, then its rate-limit threshold, then what buyers
   actually paid for it:
     packages  (default) -- PackagesSection.tsx, unchanged except the four
                             now-dropped legacy money columns (migration
                             0049: name/price/credits/bonus_credits) and no
                             longer rendering PackagesPremiumThreshold
                             inline (moved to its own tab below).
     limits              -- PackagesPremiumThreshold.tsx, unchanged, now
                             mounted directly by this shell instead of by
                             PackagesSection.tsx.
     purchases           -- PurchasesSection.tsx, new: a paginated table of
                             completed credit-package purchases against a
                             new backend endpoint (GET /api/admin/purchases).
   ═══════════════════════════════════════════════════════════════════════════ */

const PackagesSection = dynamic(() => import('./PackagesSection'), { ssr: false })
const PackagesPremiumThreshold = dynamic(() => import('./PackagesPremiumThreshold'), { ssr: false })
const PurchasesSection = dynamic(() => import('./PurchasesSection'), { ssr: false })

type ProductsModuleProps = {
  tab: ProductsTab
  onTabChange: (tab: ProductsTab) => void
}

export default function ProductsModule({ tab, onTabChange }: ProductsModuleProps) {
  // A `?tab=` naming a sub-tab that no longer exists (or none at all) must
  // not leave the URL lying about what is on screen -- normalise it once.
  useEffect(() => {
    if (!isProductsTab(tab)) onTabChange(DEFAULT_PRODUCTS_TAB)
  }, [tab, onTabChange])

  const active: ProductsTab = isProductsTab(tab) ? tab : DEFAULT_PRODUCTS_TAB

  // Subscribed, like AdminPanel.tsx and ModelsModule.tsx -- see the note
  // there. The language flip no longer reloads the page, so reading it
  // once at mount would leave these three sub-tabs stuck in whichever
  // language they first rendered in.
  const lang = useLang()

  return (
    <div className="space-y-6">
      <div
        role="tablist"
        aria-label={lang === 'en' ? 'Products' : 'محصولات'}
        data-testid="products-tabs"
        className="flex gap-1 border-b overflow-x-auto"
        style={{ borderColor: 'var(--border)' }}
      >
        {/* `entry`, not `t`: `t` is the bilingual label helper imported above
            as `label`, and reusing the name for the map item is how the two
            get confused. */}
        {PRODUCTS_TABS.map((entry) => (
          <button
            key={entry.key}
            role="tab"
            aria-selected={active === entry.key}
            className={`px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors ${active === entry.key ? 'border-b-2' : 'opacity-60 hover:opacity-100'}`}
            style={active === entry.key ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : { color: 'var(--text-secondary)' }}
            onClick={() => onTabChange(entry.key)}
          >
            {label(entry, lang)}
          </button>
        ))}
      </div>

      {active === 'packages' && <PackagesSection api={api} />}
      {active === 'limits' && <PackagesPremiumThreshold api={api} />}
      {active === 'purchases' && <PurchasesSection api={api} />}
    </div>
  )
}
