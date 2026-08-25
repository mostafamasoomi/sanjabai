'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { SectionHeader, Field } from './shared'
import { watchdogSectionStrings } from './WatchdogSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   هشدارهای تلگرام — اعتبارنامهٔ رباتی که هر سه مسیر هشدار این پلتفرم از آن
   استفاده می‌کنند (قفل‌شدن حساب در security.py، دیده‌بان مالی در watchdog.py،
   و پالایش محتوا در services/moderation_store.py).

   تا پیش از مهاجرت 0044 این دو مقدار فقط متغیر محیطی بودند؛ عوض‌کردنشان یعنی
   SSH و ری‌استارت کانتینر. حالا ردیف app_setting هستند و از همین‌جا ویرایش
   می‌شوند.

   Self-contained (fetches its own data via the `api` prop), same pattern as
   ./SiteControlSection.tsx and ./ExchangeRateSection.tsx.

   Server contract (backend/admin_watchdog.py):
     GET  /api/admin/watchdog-settings -> {
       bot_token_set, bot_token_hint, bot_token_source,
       chat_id, chat_id_set, chat_id_source,
       active, env_available: { bot_token, chat_id }, rows_missing
     }
     POST /api/admin/watchdog-settings <- { bot_token?, chat_id? }
       رشتهٔ خالی = پاک‌کردن و برگشتن به متغیر محیطی.

   ── قواعدی که این کامپوننت برای رعایتشان نوشته شده ──────────────────────
   1. توکن هرگز از سرور برنمی‌گردد و این فرم هم هرگز آن را نشان نمی‌دهد —
      فقط «تنظیم شده» و ۴ کاراکتر آخر. فیلد write-only است.
   2. خطای GET باید مثل خطا دیده شود، نه مثل «تنظیم نشده». نمایش «خاموش»
      وقتی حقیقت نامعلوم است، دروغی است که مالک ممکن است بر اساسش تصمیم
      بگیرد — دقیقاً همان قاعدهٔ SiteControlSection.
   3. خط وضعیت باید بگوید هشدار «فعال» است یا نه، و منبع هر مقدار (پایگاه
      داده / متغیر محیطی) — «روشن است» و «روشن است به‌خاطر مقداری که
      می‌بینی» دو ادعای متفاوت‌اند و فقط دومی قابل اقدام است.
   ═══════════════════════════════════════════════════════════════════════════ */

interface WatchdogSettings {
  bot_token_set: boolean
  bot_token_hint: string
  bot_token_source: 'db' | 'env' | 'none' | string
  chat_id: string
  chat_id_set: boolean
  chat_id_source: 'db' | 'env' | 'none' | string
  active: boolean
  env_available: { bot_token: boolean; chat_id: boolean }
  rows_missing: string[]
}

interface WatchdogSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

function sourceLabel(source: string, s: ReturnType<typeof watchdogSectionStrings>): string {
  if (source === 'db') return s.sourceDb
  if (source === 'env') return s.sourceEnv
  if (source === 'none') return s.sourceNone
  return source
}

function SourceBadge({ source, s }: { source: string; s: ReturnType<typeof watchdogSectionStrings> }) {
  const ok = source === 'db' || source === 'env'
  return (
    <span
      className="text-xs px-1.5 py-0.5 rounded"
      style={{
        color: ok ? 'var(--text-muted)' : 'var(--warning, #f59e0b)',
        background: ok
          ? 'var(--bg-base)'
          : 'color-mix(in srgb, var(--warning, #f59e0b) 12%, transparent)',
      }}
    >
      {sourceLabel(source, s)}
    </span>
  )
}

export default function WatchdogSection({ api }: WatchdogSectionProps) {
  const lang = useLang()
  const s = watchdogSectionStrings(lang)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<WatchdogSettings | null>(null)
  const [saving, setSaving] = useState(false)

  // Draft state. `botToken` starts empty on every load and stays empty
  // unless the admin types: the real value is never sent to the browser,
  // so pre-filling it with anything (bullets included) would be a lie the
  // save handler could then submit verbatim.
  const [botToken, setBotToken] = useState('')
  const [clearToken, setClearToken] = useState(false)
  const [chatId, setChatId] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api('/api/admin/watchdog-settings')
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || s.serverError(String(res.status)))
      }
      const body: WatchdogSettings = await res.json()
      setData(body)
      setBotToken('')
      setClearToken(false)
      setChatId(body.chat_id || '')
    } catch (e) {
      // Never fall back to a blank "not configured" form -- see rule 2.
      setError(e instanceof Error && e.message !== 'unauthorized' ? e.message : s.loadFailedGeneric)
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [api, s])

  useEffect(() => { load() }, [load])

  const chatChanged = !!data && chatId.trim() !== (data.chat_id || '')
  const tokenChanged = botToken.trim().length > 0 || clearToken
  const dirty = chatChanged || tokenChanged

  const save = async () => {
    if (!data || !dirty) return
    const payload: { bot_token?: string; chat_id?: string } = {}
    if (clearToken) payload.bot_token = ''
    else if (botToken.trim()) payload.bot_token = botToken.trim()
    if (chatChanged) payload.chat_id = chatId.trim()

    setSaving(true)
    try {
      const res = await api('/api/admin/watchdog-settings', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        toast(body.detail || s.saveFailed, 'error')
        return
      }
      toast(s.saveOk, 'success')
      await load()
    } catch {
      toast(s.saveFailed, 'error')
    } finally {
      setSaving(false)
    }
  }

  if (error) {
    return (
      <div className="space-y-6">
        <SectionHeader title={s.title} subtitle={s.errorSubtitle} />
        <div className="admin-card" style={{ borderRight: '3px solid var(--danger, #ef4444)' }}>
          <div className="flex items-center gap-2 mb-2">
            <Icon name="warning" size={18} style={{ color: 'var(--danger, #ef4444)' }} />
            <h3 className="font-semibold text-sm text-primary">{s.loadFailedTitle}</h3>
          </div>
          <p className="text-xs text-muted mb-4">{error}</p>
          <p className="text-xs mb-4" style={{ color: 'var(--warning, #f59e0b)' }}>
            {s.loadFailedNote}
          </p>
          <button className="btn btn-sm" onClick={load}>
            <Icon name="refresh" size={14} />
            <span>{s.retry}</span>
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title={s.title}
        subtitle={s.subtitle}
      />

      {loading ? (
        <div className="admin-card p-6 text-center text-sm text-muted">{s.loading}</div>
      ) : !data ? (
        <div className="admin-card p-6 text-center text-sm text-muted">{s.noData}</div>
      ) : (
        <>
          {/* ── خط وضعیت ─────────────────────────────────────────────── */}
          <div
            className="admin-card"
            style={{ borderRight: `3px solid ${data.active ? '#22c55e' : 'var(--warning, #f59e0b)'}` }}
          >
            <div className="flex items-center gap-2 mb-2">
              <Icon
                name={data.active ? 'check' : 'warning'}
                size={18}
                style={{ color: data.active ? '#22c55e' : 'var(--warning, #f59e0b)' }}
              />
              <h3 className="font-semibold text-sm text-primary">
                {data.active ? s.statusActiveTitle : s.statusInactiveTitle}
              </h3>
            </div>
            {data.active ? (
              <p className="text-xs text-muted">
                {s.statusActiveBody(sourceLabel(data.bot_token_source, s), sourceLabel(data.chat_id_source, s))}
              </p>
            ) : (
              <p className="text-xs" style={{ color: 'var(--warning, #f59e0b)' }}>
                {!data.bot_token_set && !data.chat_id_set
                  ? s.statusInactiveNone
                  : !data.bot_token_set
                    ? s.statusInactiveNoToken
                    : s.statusInactiveNoChat}
              </p>
            )}
          </div>

          {/* ── فرم ──────────────────────────────────────────────────── */}
          <div className="admin-card space-y-4">
            <Field label={s.tokenFieldLabel}>
              <div className="flex items-center gap-2 flex-wrap mb-2">
                {data.bot_token_set ? (
                  <span className="text-xs flex items-center gap-1" style={{ color: '#22c55e' }}>
                    <Icon name="check" size={12} />
                    <span>{s.tokenSet}</span>
                    {data.bot_token_hint && (
                      <span className="font-mono text-muted">••••{data.bot_token_hint}</span>
                    )}
                  </span>
                ) : (
                  <span className="text-xs text-muted">{s.tokenNotSet}</span>
                )}
                <SourceBadge source={data.bot_token_source} s={s} />
              </div>
              <input
                type="password"
                className="input w-full"
                dir="ltr"
                autoComplete="new-password"
                placeholder={data.bot_token_set ? s.tokenPlaceholderReplace : s.tokenPlaceholderNew}
                value={botToken}
                disabled={clearToken || saving}
                onChange={(e) => setBotToken(e.target.value)}
              />
              <p className="text-xs text-muted mt-1">
                {s.tokenHelp}
              </p>
              <label className="flex items-center gap-2 mt-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={clearToken}
                  disabled={saving}
                  onChange={(e) => { setClearToken(e.target.checked); if (e.target.checked) setBotToken('') }}
                />
                <span className="text-xs text-muted">
                  {s.clearTokenLabel}
                  {data.env_available.bot_token ? s.clearTokenWithEnv : s.clearTokenNoEnv}
                </span>
              </label>
            </Field>

            <Field label={s.chatFieldLabel}>
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <SourceBadge source={data.chat_id_source} s={s} />
              </div>
              <input
                type="text"
                className="input w-full"
                dir="ltr"
                placeholder={s.chatPlaceholder}
                value={chatId}
                disabled={saving}
                onChange={(e) => setChatId(e.target.value)}
              />
              <p className="text-xs text-muted mt-1">
                {s.chatHelp}
                {data.env_available.chat_id ? s.chatHelpEnvSet : s.chatHelpEnvUnset}
              </p>
            </Field>

            <div className="flex items-center gap-3 flex-wrap">
              <button className="btn btn-sm" onClick={save} disabled={!dirty || saving}>
                {saving ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (
                  <>
                    <Icon name="check" size={14} />
                    <span>{s.save}</span>
                  </>
                )}
              </button>
              {dirty && !saving && (
                <button
                  className="btn btn-sm"
                  style={{ background: 'var(--bg-elevated)' }}
                  onClick={() => { setBotToken(''); setClearToken(false); setChatId(data.chat_id || '') }}
                >
                  {s.cancel}
                </button>
              )}
              {!dirty && <span className="text-xs text-muted">{s.noChanges}</span>}
            </div>

            {data.rows_missing.length > 0 && (
              <p className="text-xs text-muted">
                {s.rowsMissing(data.rows_missing.join(s.listSeparator))}
              </p>
            )}
          </div>

          {/* ── جایی که این اعتبارنامه استفاده می‌شود ─────────────────── */}
          <div className="admin-card">
            <h3 className="font-semibold text-sm text-primary mb-2">{s.usedWhereTitle}</h3>
            <ul className="text-xs text-muted space-y-1">
              <li>• {s.usedWhereLockout}</li>
              <li>• {s.usedWhereWatchdog}</li>
              <li>• {s.usedWhereModeration}</li>
            </ul>
            <p className="text-xs text-muted mt-2">
              {s.usedWherePriority}
            </p>
          </div>
        </>
      )}
    </div>
  )
}
