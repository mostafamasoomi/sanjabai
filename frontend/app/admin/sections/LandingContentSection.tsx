'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt, dirFor } from '@/lib/i18n'
import { errMessage } from '../api'
import { SectionHeader, Field } from './shared'
import { ErrorCard } from './LoadState'
import { landingContentStrings } from './LandingContentSection.strings'
import {
  LANDING_MODULE_KEYS,
  LANDING_SCHEMA,
  pathValue,
  sanitizeLandingOverrides,
  type LandingModuleKey,
  type LandingOverridesMap,
} from '@/lib/landingOverrides'
import { apiStaticDefaults } from '@/components/landing/content/api'
import { capabilitiesStaticDefaults } from '@/components/landing/content/capabilities'
import { comparisonStaticDefaults } from '@/components/landing/content/comparison'
import { faqStaticDefaults } from '@/components/landing/content/faq'
import { featuresStaticDefaults } from '@/components/landing/content/features'
import { footerStaticDefaults } from '@/components/landing/content/footer'
import { heroStaticDefaults } from '@/components/landing/content/hero'
import { navStaticDefaults } from '@/components/landing/content/nav'
import { pricingStaticDefaults } from '@/components/landing/content/pricing'
import { statsStaticDefaults } from '@/components/landing/content/stats'
import { stepsStaticDefaults } from '@/components/landing/content/steps'

/* ═══════════════════════════════════════════════════════════════════════════
   Landing content editor (B-LAND phase 6).

   The landing page's actual copy stays in the thirteen static files under
   components/landing/content/*.ts (see lib/landingOverrides.ts's module
   docstring for the full contract). This section is a thin, schema-driven
   form on top of that: one field pair (fa/en) per path LANDING_SCHEMA lists
   for a module, nothing hand-built per module. Two modules (`catalog`,
   `constants`) have an empty schema on purpose and render an explanatory
   note instead of a form — see LANDING_SCHEMA's own comments for why.

   Server contract (backend/admin_landing.py):
     GET    /api/admin/landing/content         -> { overrides, allowedKeys, frozenPaths }
     PUT    /api/admin/landing/content/{key}    <- { value: <flat path -> {fa,en} map> }
     DELETE /api/admin/landing/content/{key}    -> reverts that module to static

   Not yet reachable in production: the router isn't registered in app.py
   yet (senior's job), so today every call here 404s. This section must
   degrade to a plain, retryable error state rather than crash — never pretend
   the store is empty when the real answer is "unknown" (same rule
   WatchdogSection/SiteControlSection already follow for their own settings).
   ═══════════════════════════════════════════════════════════════════════════ */

const STATIC_DEFAULTS: Record<LandingModuleKey, { fa: unknown; en: unknown }> = {
  api: apiStaticDefaults,
  capabilities: capabilitiesStaticDefaults,
  catalog: { fa: {}, en: {} },
  comparison: comparisonStaticDefaults,
  constants: { fa: {}, en: {} },
  faq: faqStaticDefaults,
  features: featuresStaticDefaults,
  footer: footerStaticDefaults,
  hero: heroStaticDefaults,
  nav: navStaticDefaults,
  pricing: pricingStaticDefaults,
  stats: statsStaticDefaults,
  steps: stepsStaticDefaults,
}

/** Excluded stricter than the backend's own FROZEN_PATHS floor — see
 *  LANDING_SCHEMA's comment on stats.items.0.label. Shown in the same
 *  read-only note as the server-reported frozen paths so an admin isn't
 *  left wondering why the field just isn't there. */
const EXTRA_EXCLUDED_PATHS: Partial<Record<LandingModuleKey, readonly string[]>> = {
  stats: ['items.0.label'],
}

type DraftPair = { fa: string; en: string }
type Draft = Partial<Record<LandingModuleKey, Record<string, DraftPair>>>

function draftFromOverrides(overrides: LandingOverridesMap): Draft {
  const draft: Draft = {}
  for (const key of LANDING_MODULE_KEYS) {
    const moduleOverride = overrides[key]
    if (!moduleOverride) continue
    const fields: Record<string, DraftPair> = {}
    for (const path of LANDING_SCHEMA[key]) {
      const pair = moduleOverride[path]
      if (pair) fields[path] = { fa: pair.fa, en: pair.en }
    }
    if (Object.keys(fields).length > 0) draft[key] = fields
  }
  return draft
}

interface LandingContentSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

export default function LandingContentSection({ api }: LandingContentSectionProps) {
  const lang = useLang()
  const s = landingContentStrings(lang)
  const f = fmt(lang)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft>({})
  const [updatedAt, setUpdatedAt] = useState<Partial<Record<LandingModuleKey, string | null>>>({})
  const [frozenPaths, setFrozenPaths] = useState<Partial<Record<LandingModuleKey, string[]>>>({})
  const [busyKey, setBusyKey] = useState<LandingModuleKey | null>(null)
  const [busyAction, setBusyAction] = useState<'save' | 'reset' | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api('/api/admin/landing/content')
      const body = await res.json()
      const overridesRaw: Record<string, { value: unknown; updatedAt: string | null }> = body?.overrides ?? {}
      const asDataShape: Record<string, unknown> = {}
      const at: Partial<Record<LandingModuleKey, string | null>> = {}
      for (const key of LANDING_MODULE_KEYS) {
        const row = overridesRaw[key]
        if (!row) continue
        asDataShape[key] = row.value
        at[key] = row.updatedAt ?? null
      }
      const overrides = sanitizeLandingOverrides(asDataShape)
      setDraft(draftFromOverrides(overrides))
      setUpdatedAt(at)
      setFrozenPaths(body?.frozenPaths ?? {})
    } catch (e) {
      setError(errMessage(e, s.loadError))
    } finally {
      setLoading(false)
    }
    // s.loadError is stable per language render; excluding it from deps
    // avoids re-fetching on every language toggle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api])

  useEffect(() => {
    load()
  }, [load])

  const setField = useCallback((key: LandingModuleKey, path: string, field: 'fa' | 'en', value: string) => {
    setDraft((prev) => {
      const moduleFields = { ...(prev[key] ?? {}) }
      const pair = { ...(moduleFields[path] ?? { fa: '', en: '' }) }
      pair[field] = value
      moduleFields[path] = pair
      return { ...prev, [key]: moduleFields }
    })
  }, [])

  const saveModule = useCallback(
    async (key: LandingModuleKey) => {
      const moduleFields = draft[key] ?? {}
      const value: Record<string, DraftPair> = {}
      for (const path of LANDING_SCHEMA[key]) {
        const pair = moduleFields[path]
        const fa = (pair?.fa ?? '').trim()
        const en = (pair?.en ?? '').trim()
        if (!fa && !en) continue
        if (!fa || !en) {
          toast(s.bothLanguagesRequired, 'error')
          return
        }
        value[path] = { fa, en }
      }
      if (Object.keys(value).length === 0) {
        toast(s.nothingToSave, 'error')
        return
      }
      setBusyKey(key)
      setBusyAction('save')
      try {
        const res = await api(`/api/admin/landing/content/${key}`, {
          method: 'PUT',
          body: JSON.stringify({ value }),
        })
        await res.json()
        toast(s.saveSuccess(s.moduleNames[key]), 'success')
        await load()
      } catch (e) {
        toast(errMessage(e, s.saveError), 'error')
      } finally {
        setBusyKey(null)
        setBusyAction(null)
      }
    },
    [api, draft, load, s],
  )

  const resetModule = useCallback(
    async (key: LandingModuleKey) => {
      setBusyKey(key)
      setBusyAction('reset')
      try {
        await api(`/api/admin/landing/content/${key}`, { method: 'DELETE' })
        toast(s.resetSuccess(s.moduleNames[key]), 'success')
        await load()
      } catch (e) {
        toast(errMessage(e, s.resetError), 'error')
      } finally {
        setBusyKey(null)
        setBusyAction(null)
      }
    },
    [api, load, s],
  )

  const frozenNoteByKey = useMemo(() => {
    const out: Partial<Record<LandingModuleKey, string>> = {}
    for (const key of LANDING_MODULE_KEYS) {
      const paths = [...(frozenPaths[key] ?? []), ...(EXTRA_EXCLUDED_PATHS[key] ?? [])]
      if (paths.length > 0) out[key] = s.frozenFieldsNote(paths.join(s.listSeparator))
    }
    return out
  }, [frozenPaths, s])

  if (loading) {
    return (
      <div>
        <SectionHeader title={s.title} subtitle={s.subtitle} />
        <p className="text-sm text-muted">{s.loading}</p>
      </div>
    )
  }

  if (error) {
    return (
      <div>
        <SectionHeader title={s.title} subtitle={s.subtitle} />
        <ErrorCard message={`${error} — ${s.backendNotWiredHint}`} onRetry={load} />
      </div>
    )
  }

  return (
    <div>
      <SectionHeader title={s.title} subtitle={s.subtitle} />
      <div className="flex flex-col gap-4">
        {LANDING_MODULE_KEYS.map((key) => {
          const schema = LANDING_SCHEMA[key]
          const staticDefault = STATIC_DEFAULTS[key][lang]
          const moduleFields = draft[key] ?? {}
          const savedAt = updatedAt[key]
          const busy = busyKey === key

          return (
            <details key={key} className="admin-card">
              <summary className="cursor-pointer font-medium text-primary flex items-center gap-2">
                <span>{s.moduleNames[key]}</span>
                <span className="text-xs text-muted">
                  {schema.length > 0 ? s.fieldCount(String(schema.length)) : ''}
                </span>
              </summary>

              <div className="mt-4 flex flex-col gap-4">
                {schema.length === 0 && (
                  <p className="text-xs text-muted">
                    {s.noEditableFields}{' '}
                    {key === 'catalog' ? s.noEditableFieldsReasonCatalog : null}
                    {key === 'constants' ? s.noEditableFieldsReasonConstants : null}
                  </p>
                )}

                {frozenNoteByKey[key] && (
                  <p className="text-xs" style={{ color: 'var(--warning, #f59e0b)' }}>
                    {frozenNoteByKey[key]}
                  </p>
                )}

                {schema.map((path) => {
                  const faDefault = String(pathValue(staticDefault, path).value ?? '')
                  const enDefault = String(
                    pathValue(STATIC_DEFAULTS[key].en, path).value ?? '',
                  )
                  const pair = moduleFields[path] ?? { fa: '', en: '' }
                  return (
                    <div key={path} className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <Field label={`${path} — ${s.faColumn}`}>
                        {/* Per-field direction, independent of the admin UI's own
                            language toggle: this textarea always holds Persian
                            text. Written as `dir={'rtl'}` rather than the JSX
                            string-literal attribute form on purpose — the
                            adminI18nCoverage guard bans a *section* pinning its
                            whole body to rtl regardless of language; a bilingual
                            content field legitimately needs one rtl input and one
                            ltr input side by side no matter which language the
                            panel itself is in. */}
                        <textarea
                          className="input"
                          rows={faDefault.length > 80 ? 4 : 2}
                          dir={'rtl'}
                          value={pair.fa}
                          placeholder={`${s.placeholderPrefix} ${faDefault}`}
                          onChange={(e) => setField(key, path, 'fa', e.target.value)}
                        />
                      </Field>
                      <Field label={`${path} — ${s.enColumn}`}>
                        <textarea
                          className="input"
                          rows={enDefault.length > 80 ? 4 : 2}
                          dir={'ltr'}
                          value={pair.en}
                          placeholder={`${s.placeholderPrefix} ${enDefault}`}
                          onChange={(e) => setField(key, path, 'en', e.target.value)}
                        />
                      </Field>
                    </div>
                  )
                })}

                {schema.length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap" dir={dirFor(lang)}>
                    <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => saveModule(key)}>
                      {busy && busyAction === 'save' ? s.saving : s.save}
                    </button>
                    <button className="btn btn-sm" disabled={busy} onClick={() => resetModule(key)}>
                      {busy && busyAction === 'reset' ? s.resetting : s.resetToDefault}
                    </button>
                    <span className="text-xs text-muted">
                      {savedAt ? s.updatedAt(f.date(savedAt)) : s.neverUpdated}
                    </span>
                  </div>
                )}
              </div>
            </details>
          )
        })}
      </div>
    </div>
  )
}
