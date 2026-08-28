'use client'

/* ═══════════════════════════════════════════════════════════════════════════
   Landing page content overrides — schema + loader + merge (B-LAND phase 6).

   Contract (locked by the senior, see the phase-6 decision note): the landing
   page's actual copy stays exactly where it is today — thirteen static
   TypeScript modules under components/landing/content/*.ts, each a pair of
   FA/EN objects whose leaves are functions (even the ones that just close
   over a constant string), not JSON. `backend/landing_content.py` never
   holds that content; it holds, per module, a FLAT map of dot-path ->
   {fa, en}, e.g. `{"items.1.value": {"fa": "تومان", "en": "Toman"}}`.

   This file is the only place that knows which dot-paths are allowed to be
   edited at all (LANDING_SCHEMA) — the admin editor renders a field only for
   a path listed here, and the public merge (applyModuleOverride) applies an
   override only for a path listed here. A path that is not here cannot
   reach the page no matter what ends up in the database — this is the
   primary guard; `backend/landing_content.py`'s FROZEN_PATHS is the second
   belt, not the first.

   ── How a path was chosen or rejected (see the handoff report for the
      full per-module accounting) ───────────────────────────────────────────
   Two kinds of leaf were left out on purpose, beyond the literal "the value
   is a function of the live model count" rule from the contract:

   1. Live-count-derived text (the contract's own rule). Every leaf whose
      function body reads its `count` parameter to embed the number itself
      (stats.items.0.value, comparison.rows.0.sanjabai, pricing.columns.1.
      features.3, faq.items.0.a) is excluded — these are exactly
      `backend/landing_content.py`'s FROZEN_PATHS, one-to-one. stats.items.0.
      label's English half also branches on `count` (singular/plural only,
      never the number) — backend does NOT freeze it, but it is left out of
      this schema too: the safe stricter reading of "depends on count" errs
      toward not letting an admin's static override desync from the live
      catalog's plural form. Schema is allowed to be narrower than the
      backend floor; this is that case.

   2. Structural/functional fields that are not prose at all: `href`
      (internal route), `icon` (must be a member of the `IconName` union or
      rendering breaks), `id` (used as a React key / tab-switch discriminant
      in CapabilityShowcase), `logo` (an asset path under /public/ai), `ext`
      (a document-type badge code), and the entire `catalog` module (model
      name + logo pairs sourced from `backend/litellm_config.yaml` — letting
      an admin retype a model's marquee name divorces it from the real
      catalog, adjacent to the "a model is offered only after a live probe"
      product rule). None of these are named by the contract's exclusion
      rule, which only discusses live counts — this is a second, narrower
      scope drawn deliberately so a copy-editing feature cannot double as an
      "edit internal navigation / break an icon / mislabel a real model"
      feature. Flagged prominently for the senior; expanding the schema
      later is a one-line, low-risk change if this reading is too strict.

   `constants` ends up with an empty path list for a different reason: its
   two exports (API_BASE_URL, MIN_TOPUP_LABEL_FA/EN) are plain top-level
   constants interpolated into OTHER modules' template strings at import
   time, not rendered as their own module anywhere — there is no resolved
   object for this key to merge into. Its consumers (faq.items.2.a, pricing.
   columns.*.headlineNote, steps.items.1.desc) already carry the interpolated
   text as their own schema paths, which is where an admin edits it.
   `catalog` ends up empty for the product-identity reason above.

   ── Merge semantics ─────────────────────────────────────────────────────
   `applyModuleOverride` runs AFTER each content module has already resolved
   its language and (for the four modules that read the live model count)
   its count-dependent functions down to plain strings — i.e. on the exact
   object shape the component is about to render. It only ever touches a
   path that is in `LANDING_SCHEMA[key]` AND present (as a same-shaped
   `{fa, en}` pair) in the fetched override AND already exists at that path
   in the resolved static object. Anything else is left completely alone.
   With no override for a module (the default — an empty `landing_content`
   table), it returns the exact same object reference it was given.

   Fail-safe: `loadLandingOverrides()` never rejects. A network error, a 404
   (today's reality — the router isn't wired into app.py yet), malformed
   JSON, or a response with the wrong shape all resolve to `{}`, which makes
   every `applyModuleOverride` call a no-op. The landing page is a public,
   unauthenticated product surface; it must render today's static content
   even when this entire feature is unreachable.
   ═══════════════════════════════════════════════════════════════════════════ */

import { useEffect, useState } from 'react'
import type { Lang } from '@/components/LanguageToggle'

/* ── Module keys ─────────────────────────────────────────────────────────
   Mirrors backend/landing_content.py's ALLOWED_KEYS exactly (thirteen
   frontend/components/landing/content/*.ts module names). Kept as a literal
   union + array here rather than importing anything from the backend (there
   is nothing to import across the language boundary) — if a fourteenth
   module is ever added, both this array and the backend's ALLOWED_KEYS need
   the same one-line addition, same as the backend module's own comment
   describes. */
export type LandingModuleKey =
  | 'api' | 'capabilities' | 'catalog' | 'comparison' | 'constants' | 'faq'
  | 'features' | 'footer' | 'hero' | 'nav' | 'pricing' | 'stats' | 'steps'

export const LANDING_MODULE_KEYS: readonly LandingModuleKey[] = [
  'api', 'capabilities', 'catalog', 'comparison', 'constants', 'faq',
  'features', 'footer', 'hero', 'nav', 'pricing', 'stats', 'steps',
]

/** One bilingual override value. Both languages travel together — editing
 *  only the Persian half must never blank out the English page (contract
 *  rule 3). */
export type OverridePair = { fa: string; en: string }

/** `{ "<dot.path>": { fa, en } }` — one module's stored override, already
 *  filtered to schema-known paths by `sanitizeLandingOverrides`. */
export type ModuleOverride = Record<string, OverridePair>

/** `{ "<module>": ModuleOverride }` — the shape of `GET /landing/content`'s
 *  `data` field, and of what `useLandingOverrides()` hands back. */
export type LandingOverridesMap = Partial<Record<LandingModuleKey, ModuleOverride>>

/* ── Schema: every dot-path an admin may edit, per module ────────────────
   Paths address the exact JSON shape of that module's language-resolved
   content object (numeric segment = array index, any other segment = object
   key) — see `pathValue` below, a straight port of
   backend/landing_content.py's `path_value`. */
export const LANDING_SCHEMA: Readonly<Record<LandingModuleKey, readonly string[]>> = {
  api: [
    'points.0', 'points.1', 'points.2',
    'codeSamples.Python', 'codeSamples.JavaScript', 'codeSamples.cURL',
  ],
  capabilities: [
    'tabs.0.tabLabel', 'tabs.0.title', 'tabs.0.desc', 'tabs.0.linkLabel',
    'tabs.1.tabLabel', 'tabs.1.title', 'tabs.1.desc', 'tabs.1.linkLabel',
    'tabs.2.tabLabel', 'tabs.2.title', 'tabs.2.desc', 'tabs.2.linkLabel',
    'memorySamples.0.category', 'memorySamples.0.text',
    'memorySamples.1.category', 'memorySamples.1.text',
    'memorySamples.2.category', 'memorySamples.2.text',
    'documentTypes.0.label', 'documentTypes.0.desc',
    'documentTypes.1.label', 'documentTypes.1.desc',
    'documentTypes.2.label', 'documentTypes.2.desc',
    'taskSamples.0.title', 'taskSamples.0.schedule', 'taskSamples.0.channel',
    'taskSamples.1.title', 'taskSamples.1.schedule', 'taskSamples.1.channel',
  ],
  // Real model/logo pairs sourced from backend/litellm_config.yaml — no
  // editable copy, see the module docstring above.
  catalog: [],
  comparison: [
    // rows.0.sanjabai is excluded: FROZEN_PATHS 'comparison' -> 'rows.0.sanjabai'.
    'rows.0.label', 'rows.0.subscription',
    'rows.1.label', 'rows.1.sanjabai', 'rows.1.subscription',
    'rows.2.label', 'rows.2.sanjabai', 'rows.2.subscription',
    'rows.3.label', 'rows.3.sanjabai', 'rows.3.subscription',
    'rows.4.label', 'rows.4.sanjabai', 'rows.4.subscription',
  ],
  // No rendered module to merge into — see the module docstring above.
  constants: [],
  faq: [
    // items.0.a is excluded: FROZEN_PATHS 'faq' -> 'items.0.a'.
    'items.0.q',
    'items.1.q', 'items.1.a',
    'items.2.q', 'items.2.a',
    'items.3.q', 'items.3.a',
    'items.4.q', 'items.4.a',
    'items.5.q', 'items.5.a',
  ],
  features: [
    'items.0.title', 'items.0.desc', 'items.0.linkLabel',
    'items.1.title', 'items.1.desc', 'items.1.linkLabel',
    'items.2.title', 'items.2.desc', 'items.2.linkLabel',
    'items.3.title', 'items.3.desc', 'items.3.linkLabel',
    'items.4.title', 'items.4.desc', 'items.4.linkLabel',
    'items.5.title', 'items.5.desc', 'items.5.linkLabel',
    'items.6.title', 'items.6.desc', 'items.6.linkLabel',
    'items.7.title', 'items.7.desc', 'items.7.linkLabel',
    'items.8.title', 'items.8.desc', 'items.8.linkLabel',
  ],
  footer: [
    'columns.0.title',
    'columns.0.links.0.label', 'columns.0.links.1.label', 'columns.0.links.2.label',
    'columns.0.links.3.label', 'columns.0.links.4.label',
    'columns.1.title',
    'columns.1.links.0.label', 'columns.1.links.1.label', 'columns.1.links.2.label',
    'columns.1.links.3.label',
    'columns.2.title',
    'columns.2.links.0.label', 'columns.2.links.1.label', 'columns.2.links.2.label',
    'columns.2.links.3.label',
  ],
  hero: [
    'rotation.0', 'rotation.1', 'rotation.2',
    'trust.0', 'trust.1', 'trust.2',
    'previewThreads.0.question', 'previewThreads.0.answer',
    'previewThreads.1.question', 'previewThreads.1.answer',
    'previewThreads.2.question', 'previewThreads.2.answer',
    'previewThreads.3.question', 'previewThreads.3.answer',
  ],
  nav: ['links.0.label', 'links.1.label', 'links.2.label', 'links.3.label'],
  pricing: [
    'columns.0.name', 'columns.0.desc', 'columns.0.headline', 'columns.0.headlineNote', 'columns.0.cta',
    'columns.0.features.0', 'columns.0.features.1', 'columns.0.features.2',
    'columns.1.name', 'columns.1.desc', 'columns.1.headline', 'columns.1.headlineNote', 'columns.1.cta',
    // columns.1.features.3 is excluded: FROZEN_PATHS 'pricing' -> 'columns.1.features.3'.
    'columns.1.features.0', 'columns.1.features.1', 'columns.1.features.2', 'columns.1.features.4',
    'columns.2.name', 'columns.2.desc', 'columns.2.headline', 'columns.2.cta',
    'columns.2.features.0', 'columns.2.features.1', 'columns.2.features.2', 'columns.2.features.3',
  ],
  stats: [
    // items.0.value is excluded: FROZEN_PATHS 'stats' -> 'items.0.value'.
    // items.0.label is excluded too, stricter than the backend floor — see
    // the module docstring above (its EN half branches on live `count`).
    'items.1.value', 'items.1.label',
    'items.2.value', 'items.2.label',
    'items.3.value', 'items.3.label',
  ],
  steps: [
    'items.0.title', 'items.0.desc',
    'items.1.title', 'items.1.desc',
    'items.2.title', 'items.2.desc',
  ],
}

/* ── Path utilities — a straight port of backend/landing_content.py's
   path_value, plus an immutable setter with the same walking rules. Never
   throws; any shape mismatch is reported as "not found". ─────────────── */

export function pathValue(value: unknown, path: string): { found: boolean; value: unknown } {
  let cur: unknown = value
  for (const part of path.split('.')) {
    if (Array.isArray(cur)) {
      if (!/^\d+$/.test(part)) return { found: false, value: undefined }
      const idx = Number(part)
      if (idx < 0 || idx >= cur.length) return { found: false, value: undefined }
      cur = cur[idx]
    } else if (cur !== null && typeof cur === 'object') {
      if (!(part in (cur as Record<string, unknown>))) return { found: false, value: undefined }
      cur = (cur as Record<string, unknown>)[part]
    } else {
      return { found: false, value: undefined }
    }
  }
  return { found: true, value: cur }
}

/** Returns a new value with `next` written at `path`, cloning only the
 *  containers on the path (structural sharing for every untouched sibling
 *  branch). `root` itself is never mutated. */
export function setPath<T>(root: T, path: string, next: unknown): T {
  const parts = path.split('.')
  function walk(node: unknown, i: number): unknown {
    const part = parts[i]
    const isLast = i === parts.length - 1
    if (Array.isArray(node)) {
      const copy = node.slice()
      const idx = Number(part)
      copy[idx] = isLast ? next : walk(node[idx], i + 1)
      return copy
    }
    if (node !== null && typeof node === 'object') {
      const copy: Record<string, unknown> = { ...(node as Record<string, unknown>) }
      copy[part] = isLast ? next : walk((node as Record<string, unknown>)[part], i + 1)
      return copy
    }
    // Path doesn't actually reach into `node` — leave it alone. Callers are
    // expected to have checked `pathValue(...).found` first.
    return node
  }
  return walk(root, 0) as T
}

/* ── Merge ────────────────────────────────────────────────────────────── */

/** Applies one module's stored override onto its already language- and
 *  count-resolved static content. Returns `resolved` itself, unchanged, when
 *  there is nothing to apply — including the default "empty override store"
 *  case, so a caller can rely on referential equality when nothing changed. */
export function applyModuleOverride<T>(
  key: LandingModuleKey,
  lang: Lang,
  resolved: T,
  overrides: LandingOverridesMap | null | undefined,
): T {
  const moduleOverride = overrides ? overrides[key] : undefined
  if (!moduleOverride) return resolved

  let out: T = resolved
  for (const path of LANDING_SCHEMA[key]) {
    const pair = moduleOverride[path]
    if (!pair) continue
    const text = lang === 'en' ? pair.en : pair.fa
    // Contract rule 3: a language half missing from the stored override
    // leaves that language's static text exactly as it was.
    if (typeof text !== 'string') continue
    if (!pathValue(out, path).found) continue
    out = setPath(out, path, text)
  }
  return out
}

/* ── Response sanitation ─────────────────────────────────────────────── */

function isOverridePair(v: unknown): v is OverridePair {
  return (
    !!v && typeof v === 'object' && !Array.isArray(v) &&
    typeof (v as Record<string, unknown>).fa === 'string' &&
    typeof (v as Record<string, unknown>).en === 'string'
  )
}

/** Reduces an arbitrary parsed JSON value down to only what this schema
 *  recognises: known module keys, and within each, only paths this schema
 *  lists, and only when the stored value is a real `{fa, en}` pair. Never
 *  throws — an unrecognised shape simply contributes nothing. */
export function sanitizeLandingOverrides(raw: unknown): LandingOverridesMap {
  const out: LandingOverridesMap = {}
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return out
  const rawObj = raw as Record<string, unknown>
  for (const key of LANDING_MODULE_KEYS) {
    const moduleValue = rawObj[key]
    if (!moduleValue || typeof moduleValue !== 'object' || Array.isArray(moduleValue)) continue
    const moduleObj = moduleValue as Record<string, unknown>
    const clean: ModuleOverride = {}
    for (const path of LANDING_SCHEMA[key]) {
      const pair = moduleObj[path]
      if (isOverridePair(pair)) clean[path] = { fa: pair.fa, en: pair.en }
    }
    if (Object.keys(clean).length > 0) out[key] = clean
  }
  return out
}

/* ── Loader ───────────────────────────────────────────────────────────── */

async function fetchLandingOverridesRaw(): Promise<unknown> {
  const res = await fetch('/api/landing/content')
  if (!res.ok) throw new Error(`landing content ${res.status}`)
  const body: unknown = await res.json()
  return body && typeof body === 'object' ? (body as Record<string, unknown>).data : undefined
}

/* Module-level cache to dedupe concurrent requests across every landing
   section that calls useLandingOverrides() on the same page load — same
   idiom as lib/useCatalog.ts's fetchCatalog(). */
let cachedPromise: Promise<LandingOverridesMap> | null = null
let cachedData: LandingOverridesMap | null = null
const CACHE_TTL_MS = 60_000
let cacheTimestamp = 0

/** Fetch + sanitize + cache. Never rejects — any failure resolves to `{}`,
 *  which makes every `applyModuleOverride` call downstream a no-op. */
export function loadLandingOverrides(): Promise<LandingOverridesMap> {
  if (cachedData && Date.now() - cacheTimestamp < CACHE_TTL_MS) {
    return Promise.resolve(cachedData)
  }
  if (cachedPromise) return cachedPromise

  cachedPromise = fetchLandingOverridesRaw()
    .then((raw) => sanitizeLandingOverrides(raw))
    .catch(() => ({}) as LandingOverridesMap)
    .then((data) => {
      cachedData = data
      cacheTimestamp = Date.now()
      cachedPromise = null
      return data
    })

  return cachedPromise
}

/** Reads today's stored overrides, if any. Every landing content module
 *  that has at least one schema path calls this once and pipes its
 *  resolved object through `applyModuleOverride`. Starts from whatever is
 *  already cached (usually nothing on first paint) and updates once the
 *  fetch settles — never throws, matching `loadLandingOverrides`. */
export function useLandingOverrides(): LandingOverridesMap {
  const [state, setState] = useState<LandingOverridesMap>(cachedData ?? {})
  useEffect(() => {
    let cancelled = false
    loadLandingOverrides().then((data) => {
      if (!cancelled) setState(data)
    })
    return () => {
      cancelled = true
    }
  }, [])
  return state
}
