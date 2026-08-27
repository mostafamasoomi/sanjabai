'use client'

import { useCallback, useEffect, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { SectionHeader, Field } from './shared'
import { ErrorCard, RefreshButton } from './LoadState'
import { api, errMessage } from '../api'
import { proxyStrings } from './ProxySection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Proxy — GET/POST /admin/proxy (backend/admin_content.py).

   The form is only rendered after a successful
   load. Saving a form that was never populated would blank the tunnel URL
   the whole LiteLLM egress depends on.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function ProxySection() {
  const lang = useLang()
  const s = proxyStrings(lang)
  const [status, setStatus] = useState<'loading' | 'error' | 'ready'>('loading')
  const [loadError, setLoadError] = useState('')
  const [activeNow, setActiveNow] = useState(false)
  const [pxType, setPxType] = useState('socks5')
  const [pxUrl, setPxUrl] = useState('')
  const [pxActive, setPxActive] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setStatus('loading')
    setLoadError('')
    try {
      const res = await api('/api/admin/proxy')
      const d = await res.json()
      setActiveNow(d?.active === true)
      setPxType(d?.proxy_type || 'socks5')
      setPxUrl(d?.proxy_url || '')
      setPxActive(d?.active !== false)
      setStatus('ready')
    } catch (err) {
      setLoadError(errMessage(err, s.loadError))
      setStatus('error')
    }
  }, [s.loadError])

  useEffect(() => { load() }, [load])

  const saveProxy = async () => {
    if (status !== 'ready') return
    setSaving(true)
    try {
      await api('/api/admin/proxy', { method: 'POST', body: JSON.stringify({ proxy_type: pxType, proxy_url: pxUrl, active: pxActive }) })
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
          <div className="skeleton h-10 w-full mb-4 rounded" />
          <div className="skeleton h-9 w-full rounded" />
        </div>
      )}

      {status === 'ready' && (
        <div className="admin-card">
          <div className="flex items-center gap-3 mb-4 p-3 rounded-lg" style={{ background: activeNow ? 'var(--positive)' + '15' : 'var(--warning)' + '15' }}>
            <Icon name={activeNow ? 'check' : 'notification'} size={18} style={{ color: activeNow ? 'var(--positive)' : 'var(--warning)' }} />
            <span className="text-sm font-medium" style={{ color: activeNow ? 'var(--positive)' : 'var(--warning)' }}>
              {activeNow ? s.tunnelActive : s.tunnelInactive}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label={s.proxyType}>
              <select className="input w-full" value={pxType} onChange={(e) => setPxType(e.target.value)}>
                <option value="socks5">SOCKS5</option>
                <option value="http">HTTP</option>
              </select>
            </Field>
            <Field label={s.proxyUrl}>
              <input className="input w-full" dir="ltr" value={pxUrl} onChange={(e) => setPxUrl(e.target.value)} placeholder="socks5://user:pass@host:port" />
            </Field>
            <Field label={s.status}>
              <select className="input w-full" value={String(pxActive)} onChange={(e) => setPxActive(e.target.value === 'true')}>
                <option value="true">{s.active}</option>
                <option value="false">{s.disabled}</option>
              </select>
            </Field>
          </div>
          <button className="btn mt-4" onClick={saveProxy} disabled={saving}>
            {saving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>{s.saveApply}</span></>)}
          </button>
        </div>
      )}
    </div>
  )
}
