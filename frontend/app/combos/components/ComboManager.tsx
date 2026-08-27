'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiFetch } from '@/lib/apiFetch'
import { toast, EmptyState } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt, detailFor } from '@/lib/i18n'
import { useCatalog } from '@/lib/useCatalog'
import ComboEditor, {
  indexModels, MAX_COMBOS, MAX_ITEMS, MIN_ITEMS,
  type Combo, type ComboDraft,
} from './ComboEditor'
import { comboStrings } from './ComboManager.strings'

/* ═══════════════════════════════════════════════════════════════════════
   Combo manager — the list, and every call to /api/me/combos.

   Routing note: `next.config.js` rewrites `/api/:path*` to the backend with
   the `/api` prefix STRIPPED, so `/api/me/combos` here arrives as
   `/me/combos` there. No proxy route under app/api/ is needed or wanted.

   Every failure shows the server's own Persian `detail` (via `detailFor`)
   rather than a message invented here — the backend already explains
   duplicate names, unservable models and the 2–5/10 limits precisely.
   ═══════════════════════════════════════════════════════════════════════ */

type Dialog = { mode: 'create' } | { mode: 'edit'; combo: Combo }

export default function ComboManager({ token }: { token: string | null }) {
  const lang = useLang()
  const s = comboStrings(lang)
  const f = fmt(lang)
  const router = useRouter()
  const { models, loading: catalogLoading, error: catalogError } = useCatalog()

  const [combos, setCombos] = useState<Combo[]>([])
  const [loading, setLoading] = useState(true)
  const [loadFailed, setLoadFailed] = useState(false)
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [saving, setSaving] = useState(false)
  const [editorError, setEditorError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  const authHeaders = useMemo(
    () => (token ? { Authorization: `Bearer ${token}` } : undefined),
    [token],
  )

  const byId = useMemo(() => indexModels(models), [models])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/me/combos', { headers: authHeaders })
      if (res.status === 401) { router.push('/login'); return }
      if (!res.ok) { setLoadFailed(true); return }
      const body = await res.json()
      setCombos(Array.isArray(body?.combos) ? body.combos : [])
      setLoadFailed(false)
    } catch {
      setLoadFailed(true)
    } finally {
      setLoading(false)
    }
  }, [authHeaders, router])

  useEffect(() => { load() }, [load])

  /** One place for POST/PUT/DELETE: same auth headers, same 401 redirect,
   *  same Persian-detail extraction. Returns the parsed body on success. */
  const call = useCallback(
    async (path: string, method: string, body?: unknown): Promise<unknown | null> => {
      const res = await apiFetch(path, {
        method,
        headers: { ...(authHeaders || {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      })
      if (res.status === 401) { router.push('/login'); return null }
      const parsed = await res.json().catch(() => null)
      if (!res.ok) throw new Error(detailFor(parsed, lang) || s.genericError)
      return parsed
    },
    [authHeaders, router, lang, s.genericError],
  )

  const submit = async (draft: ComboDraft) => {
    if (!dialog) return
    setSaving(true)
    setEditorError(null)
    const payload = {
      name: draft.name,
      policy: draft.policy,
      enabled: draft.enabled,
      // Public ids, in the order the user arranged them. The server assigns
      // `position` from this order and ignores any client-sent position.
      items: draft.items.map((model_public_id) => ({ model_public_id })),
    }
    try {
      if (dialog.mode === 'create') {
        await call('/api/me/combos', 'POST', payload)
        toast(s.createdToast, 'success')
      } else {
        await call(`/api/me/combos/${dialog.combo.id}`, 'PUT', payload)
        toast(s.updatedToast, 'success')
      }
      setDialog(null)
      await load()
    } catch (err) {
      setEditorError(err instanceof Error ? err.message : s.connectionError)
    } finally {
      setSaving(false)
    }
  }

  const toggleEnabled = async (combo: Combo) => {
    setBusyId(combo.id)
    try {
      await call(`/api/me/combos/${combo.id}`, 'PUT', { enabled: !combo.enabled })
      await load()
    } catch (err) {
      toast(err instanceof Error ? err.message : s.connectionError, 'error')
    } finally {
      setBusyId(null)
    }
  }

  const remove = async (combo: Combo) => {
    if (!confirm(s.deleteConfirm(combo.name))) return
    setBusyId(combo.id)
    try {
      await call(`/api/me/combos/${combo.id}`, 'DELETE')
      toast(s.deletedToast, 'success')
      await load()
    } catch (err) {
      toast(err instanceof Error ? err.message : s.connectionError, 'error')
    } finally {
      setBusyId(null)
    }
  }

  const atMaxCombos = combos.length >= MAX_COMBOS

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16 }}>
        <span className="badge badge-accent">{s.comboCount(f.num(combos.length), f.num(MAX_COMBOS))}</span>
        <button
          className="btn btn-primary"
          disabled={atMaxCombos || loading}
          title={atMaxCombos ? s.comboLimitReached(f.num(MAX_COMBOS)) : undefined}
          onClick={() => { setEditorError(null); setDialog({ mode: 'create' }) }}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <Icon name="plus" size={14} />
          {s.newCombo}
        </button>
      </div>

      {/* The limit is explained before it bites, not after a 400. */}
      {atMaxCombos && (
        <p style={{ fontSize: 12, color: 'var(--warning)', marginBottom: 12 }}>
          {s.comboLimitReached(f.num(MAX_COMBOS))}
        </p>
      )}

      {loading ? (
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>{s.loading}</p>
      ) : loadFailed ? (
        <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <span style={{ fontSize: 13, color: 'var(--danger)' }}>{s.loadError}</span>
          <button className="btn btn-sm" onClick={load}>{s.retry}</button>
        </div>
      ) : combos.length === 0 ? (
        <EmptyState icon="models" title={s.emptyTitle} description={s.emptyDesc}>
          <button className="btn btn-primary" onClick={() => { setEditorError(null); setDialog({ mode: 'create' }) }}>
            {s.emptyCta}
          </button>
        </EmptyState>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {combos.map((combo) => (
            <div key={combo.id} className="card" style={{ opacity: combo.enabled ? 1 : 0.65 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 14 }}>{combo.name}</span>
                    <span className={`badge ${combo.enabled ? 'badge-positive' : 'badge-danger'}`}>
                      {combo.enabled ? s.enabled : s.disabled}
                    </span>
                    <span className="badge badge-accent">
                      {combo.policy === 'round_robin' ? s.policyRoundRobin : s.policySequential}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                      {s.modelsCount(f.num(combo.items.length))}
                    </span>
                  </div>

                  <p style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.7, marginBottom: 8 }}>
                    {combo.policy === 'round_robin' ? s.policyRoundRobinDesc : s.policySequentialDesc}
                  </p>

                  {/* Order is the product here, so it is numbered rather than
                      rendered as an unordered pile of chips. */}
                  <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {combo.items.map((item, idx) => {
                      const model = byId.get(item.model_public_id)
                      return (
                        <li
                          key={`${combo.id}-${item.model_public_id}`}
                          className="badge"
                          title={model ? undefined : s.unavailableModel}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                        >
                          <span style={{ color: 'var(--text-dim)' }}>{f.num(idx + 1)}</span>
                          <span dir="ltr">{model?.displayName || item.model_public_id}</span>
                          {!model && <Icon name="warning" size={11} />}
                        </li>
                      )
                    })}
                  </ol>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <button
                    className={`profile-toggle ${combo.enabled ? 'active' : ''}`}
                    role="switch"
                    aria-checked={combo.enabled}
                    aria-label={s.toggleAria(combo.name)}
                    disabled={busyId === combo.id}
                    onClick={() => toggleEnabled(combo)}
                  >
                    <span className="profile-toggle-knob" />
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    aria-label={s.editAria(combo.name)}
                    title={s.edit}
                    disabled={busyId === combo.id}
                    onClick={() => { setEditorError(null); setDialog({ mode: 'edit', combo }) }}
                  >
                    <Icon name="settings" size={14} />
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    aria-label={s.removeAria(combo.name)}
                    title={s.remove}
                    disabled={busyId === combo.id}
                    onClick={() => remove(combo)}
                  >
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <p style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 16 }}>
        {s.itemsRangeHint(f.num(MIN_ITEMS), f.num(MAX_ITEMS))}
      </p>

      <ComboEditor
        open={dialog !== null}
        initial={dialog?.mode === 'edit' ? dialog.combo : null}
        models={models}
        catalogLoading={catalogLoading}
        catalogError={catalogError}
        saving={saving}
        errorMessage={editorError}
        onCancel={() => { if (!saving) { setDialog(null); setEditorError(null) } }}
        onSubmit={submit}
      />
    </>
  )
}
