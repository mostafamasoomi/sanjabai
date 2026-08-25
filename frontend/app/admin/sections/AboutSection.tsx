'use client'

import { useCallback, useEffect, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { SectionHeader, Field } from './shared'
import { ErrorCard, RefreshButton } from './LoadState'
import { api, errMessage } from '../api'
import { aboutStrings } from './AboutSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   About — GET/POST /admin/about (backend/admin_content.py).

   The destructive bug this closes: the panel had no working load at all.
   AdminPanel's loadAll() called GET /admin/about, which did not exist and
   405'd, and Promise.allSettled dropped the rejection — so the two inputs
   rendered empty, and the first «ذخیره» POSTed those empty strings over the
   live درباره‌ما page. Hence: the form is only rendered once a load has
   actually succeeded. A failed load shows the failure and a retry, never an
   editable blank form, because an empty textarea here is indistinguishable
   from "the page is supposed to be empty" and one click makes it true.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function AboutSection() {
  const lang = useLang()
  const s = aboutStrings(lang)
  const [status, setStatus] = useState<'loading' | 'error' | 'ready'>('loading')
  const [loadError, setLoadError] = useState('')
  const [abTitle, setAbTitle] = useState('')
  const [abBody, setAbBody] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setStatus('loading')
    setLoadError('')
    try {
      const res = await api('/api/admin/about')
      const d = await res.json()
      setAbTitle(typeof d?.title === 'string' ? d.title : '')
      setAbBody(typeof d?.body === 'string' ? d.body : '')
      setStatus('ready')
    } catch (err) {
      setLoadError(errMessage(err, s.loadError))
      setStatus('error')
    }
  }, [s.loadError])

  useEffect(() => { load() }, [load])

  const saveAbout = async () => {
    // Guard, not just a disabled button: never POST content that was never
    // read back from the server.
    if (status !== 'ready') return
    setSaving(true)
    try {
      await api('/api/admin/about', { method: 'POST', body: JSON.stringify({ title: abTitle, body: abBody }) })
      toast(s.saveSuccess, 'success')
      await load()
    } catch (err) {
      toast(errMessage(err, s.saveError), 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title={s.title} subtitle={s.subtitle} />
        <RefreshButton onClick={load} busy={status === 'loading'} />
      </div>

      {status === 'error' && <ErrorCard message={loadError} onRetry={load} />}

      {status === 'loading' && (
        <div className="admin-card">
          <div className="skeleton h-3 w-24 mb-3 rounded" />
          <div className="skeleton h-9 w-full mb-5 rounded" />
          <div className="skeleton h-3 w-16 mb-3 rounded" />
          <div className="skeleton h-40 w-full rounded" />
        </div>
      )}

      {status === 'ready' && (
        <div className="admin-card">
          {/* abTitle/abBody are the live درباره‌ما page copy, fetched from and
              saved back to the server — content, not UI chrome, so it is
              deliberately not translated by this component. The placeholder
              hints below are example content in Persian for the same reason. */}
          <div className="space-y-4">
            <Field label={s.titleLabel}>
              <input className="input w-full" value={abTitle} onChange={(e) => setAbTitle(e.target.value)} placeholder={s.titlePlaceholder} />
            </Field>
            <Field label={s.bodyLabel}>
              <textarea
                className="input w-full min-h-[200px] resize-y leading-relaxed"
                value={abBody}
                onChange={(e) => setAbBody(e.target.value)}
                placeholder={s.bodyPlaceholder}
              />
            </Field>
          </div>
          <button className="btn mt-4" onClick={saveAbout} disabled={saving}>
            {saving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>{s.save}</span></>)}
          </button>
        </div>
      )}
    </div>
  )
}
