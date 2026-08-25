'use client'

import { useEffect } from 'react'
import dynamic from 'next/dynamic'
import { api } from '../api'
import { MODELS_TABS, DEFAULT_MODELS_TAB, isModelsTab, type ModelsTab } from './modelsTabs'

/* ═══════════════════════════════════════════════════════════════════════════
   Models & pricing — one sidebar entry, eight sub-tabs.

   These were eight separate top-level nav items, and every one of them
   opened with its own "which model?" list fetched from a different
   endpoint: /catalog/models (default-model card), /admin/catalog/models
   (catalog ops), /admin/logical-models, /admin/upstream-overhead,
   /admin/pricing, /admin/image-pricing. Deciding anything about a model
   meant walking the sidebar and re-reading a differently-shaped table each
   time. They are one subject, so they are now one screen.

   Two groups, separated by a divider in the bar: what a model IS (catalog,
   logical mapping, measured overhead, org default) and what it COSTS
   (tariffs, image pricing, FX rate, markup). The order inside each group is
   the order you actually work in — discover a model, map it, measure it,
   then price it.

   Deliberately a SHELL, not a merge: each sub-tab still renders its own
   original section file, untouched. That keeps every file under the
   500-line house cap, keeps each section's own load/error/refresh state
   where it already was, and means only the visible sub-tab's endpoints are
   ever hit — mounting all eight at once would fan ~10 admin calls out on
   every visit. `dynamic(..., {ssr:false})` matches how AdminPanel already
   loaded these; the chunk for a sub-tab is fetched the first time it is
   opened.
   ═══════════════════════════════════════════════════════════════════════════ */

const ModelOpsSection = dynamic(() => import('./ModelOpsSection'), { ssr: false })
const LogicalModelsSection = dynamic(() => import('./LogicalModelsSection'), { ssr: false })
const UpstreamOverheadSection = dynamic(() => import('./UpstreamOverheadSection'), { ssr: false })
const ModelsSection = dynamic(() => import('./ModelsSection'), { ssr: false })
const PricingSection = dynamic(() => import('./PricingSection'), { ssr: false })
const ImagePricingSection = dynamic(() => import('./ImagePricingSection'), { ssr: false })
const ExchangeRateSection = dynamic(() => import('./ExchangeRateSection'), { ssr: false })
const MarkupSection = dynamic(() => import('./MarkupSection'), { ssr: false })

type ModelsModuleProps = {
  tab: ModelsTab
  onTabChange: (tab: ModelsTab) => void
}

export default function ModelsModule({ tab, onTabChange }: ModelsModuleProps) {
  // A `?tab=` naming a sub-tab that no longer exists (or none at all) must
  // not leave the URL lying about what is on screen -- normalise it once.
  useEffect(() => {
    if (!isModelsTab(tab)) onTabChange(DEFAULT_MODELS_TAB)
  }, [tab, onTabChange])

  const active: ModelsTab = isModelsTab(tab) ? tab : DEFAULT_MODELS_TAB

  return (
    <div className="space-y-6">
      <div className="flex gap-1 border-b overflow-x-auto" style={{ borderColor: 'var(--border)' }}>
        {MODELS_TABS.map((t, i) => (
          <div key={t.key} className="flex items-center">
            {/* Divider between "what a model is" and "what it costs". */}
            {i > 0 && MODELS_TABS[i - 1].group !== t.group && (
              <span className="mx-2 h-4 w-px shrink-0" style={{ background: 'var(--border)' }} aria-hidden />
            )}
            <button
              className={`px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors ${active === t.key ? 'border-b-2' : 'opacity-60 hover:opacity-100'}`}
              style={active === t.key ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : { color: 'var(--text-secondary)' }}
              onClick={() => onTabChange(t.key)}
            >
              {t.label}
            </button>
          </div>
        ))}
      </div>

      {active === 'catalog' && <ModelOpsSection api={api} />}
      {active === 'logical' && <LogicalModelsSection api={api} />}
      {active === 'overhead' && <UpstreamOverheadSection api={api} />}
      {active === 'default' && <ModelsSection />}
      {active === 'pricing' && <PricingSection />}
      {active === 'image-pricing' && <ImagePricingSection api={api} />}
      {active === 'exchange-rate' && <ExchangeRateSection api={api} />}
      {active === 'markup' && <MarkupSection api={api} />}
    </div>
  )
}
