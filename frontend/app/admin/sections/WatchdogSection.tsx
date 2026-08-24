'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { SectionHeader, Field } from './shared'

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

const SOURCE_LABEL: Record<string, string> = {
  db: 'از پنل (پایگاه داده)',
  env: 'از متغیر محیطی سرور',
  none: 'تنظیم نشده',
}

function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] || source
}

function SourceBadge({ source }: { source: string }) {
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
      {sourceLabel(source)}
    </span>
  )
}

export default function WatchdogSection({ api }: WatchdogSectionProps) {
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
        throw new Error(body.detail || `خطای سرور (${res.status})`)
      }
      const body: WatchdogSettings = await res.json()
      setData(body)
      setBotToken('')
      setClearToken(false)
      setChatId(body.chat_id || '')
    } catch (e) {
      // Never fall back to a blank "not configured" form -- see rule 2.
      setError(e instanceof Error && e.message !== 'unauthorized' ? e.message : 'خطا در دریافت تنظیمات هشدار')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [api])

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
        toast(body.detail || 'ذخیره ناموفق بود', 'error')
        return
      }
      toast('تنظیمات هشدار ذخیره شد', 'success')
      await load()
    } catch {
      toast('ذخیره ناموفق بود', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (error) {
    return (
      <div className="space-y-6">
        <SectionHeader title="هشدارهای تلگرام" subtitle="اعتبارنامهٔ رباتی که هشدارهای امنیتی، مالی و پالایش محتوا با آن ارسال می‌شود" />
        <div className="admin-card" style={{ borderRight: '3px solid var(--danger, #ef4444)' }}>
          <div className="flex items-center gap-2 mb-2">
            <Icon name="warning" size={18} style={{ color: 'var(--danger, #ef4444)' }} />
            <h3 className="font-semibold text-sm text-primary">دریافت تنظیمات ناموفق بود</h3>
          </div>
          <p className="text-xs text-muted mb-4">{error}</p>
          <p className="text-xs mb-4" style={{ color: 'var(--warning, #f59e0b)' }}>
            وضعیت واقعی هشدارها نامشخص است — تا رفع خطا فرم نمایش داده نمی‌شود، چون نمایش «تنظیم نشده»
            وقتی حقیقت معلوم نیست می‌تواند باعث تصمیم اشتباه شود.
          </p>
          <button className="btn btn-sm" onClick={load}>
            <Icon name="refresh" size={14} />
            <span>تلاش دوباره</span>
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="هشدارهای تلگرام"
        subtitle="اعتبارنامهٔ رباتی که هشدارهای قفل‌شدن حساب، ناهنجاری مالی و پالایش محتوا با آن ارسال می‌شود — بدون نیاز به ری‌استارت"
      />

      {loading ? (
        <div className="admin-card p-6 text-center text-sm text-muted">در حال بارگذاری…</div>
      ) : !data ? (
        <div className="admin-card p-6 text-center text-sm text-muted">اطلاعاتی یافت نشد</div>
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
                {data.active ? 'هشدارها فعال است' : 'هشدارها ارسال نمی‌شود'}
              </h3>
            </div>
            {data.active ? (
              <p className="text-xs text-muted">
                توکن ربات {sourceLabel(data.bot_token_source)} و شناسهٔ گفتگو {sourceLabel(data.chat_id_source)} خوانده می‌شود.
                هر سه مسیر هشدار (قفل حساب، دیده‌بان مالی، پالایش محتوا) از همین جفت استفاده می‌کنند.
              </p>
            ) : (
              <p className="text-xs" style={{ color: 'var(--warning, #f59e0b)' }}>
                {!data.bot_token_set && !data.chat_id_set
                  ? 'هیچ‌کدام از دو مقدار تنظیم نشده است — هر سه مسیر هشدار بی‌صدا رد می‌شوند.'
                  : !data.bot_token_set
                    ? 'توکن ربات تنظیم نشده است — تا وقتی هر دو مقدار پر نشوند هیچ هشداری ارسال نمی‌شود.'
                    : 'شناسهٔ گفتگو تنظیم نشده است — تا وقتی هر دو مقدار پر نشوند هیچ هشداری ارسال نمی‌شود.'}
              </p>
            )}
          </div>

          {/* ── فرم ──────────────────────────────────────────────────── */}
          <div className="admin-card space-y-4">
            <Field label="توکن ربات تلگرام">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                {data.bot_token_set ? (
                  <span className="text-xs flex items-center gap-1" style={{ color: '#22c55e' }}>
                    <Icon name="check" size={12} />
                    <span>تنظیم شده</span>
                    {data.bot_token_hint && (
                      <span className="font-mono text-muted">••••{data.bot_token_hint}</span>
                    )}
                  </span>
                ) : (
                  <span className="text-xs text-muted">تنظیم نشده</span>
                )}
                <SourceBadge source={data.bot_token_source} />
              </div>
              <input
                type="password"
                className="input w-full"
                dir="ltr"
                autoComplete="new-password"
                placeholder={data.bot_token_set ? 'برای جایگزینی، توکن جدید را وارد کنید' : '123456789:AA...'}
                value={botToken}
                disabled={clearToken || saving}
                onChange={(e) => setBotToken(e.target.value)}
              />
              <p className="text-xs text-muted mt-1">
                مقدار فعلی هرگز از سرور برگردانده نمی‌شود؛ این فیلد فقط برای نوشتن است. ذخیره‌کردن، مقدار
                قبلی را جایگزین می‌کند.
              </p>
              <label className="flex items-center gap-2 mt-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={clearToken}
                  disabled={saving}
                  onChange={(e) => { setClearToken(e.target.checked); if (e.target.checked) setBotToken('') }}
                />
                <span className="text-xs text-muted">
                  پاک‌کردن توکن ذخیره‌شده
                  {data.env_available.bot_token
                    ? ' — پس از پاک‌کردن، مقدار متغیر محیطی سرور دوباره به‌کار می‌رود.'
                    : ' — متغیر محیطی هم تنظیم نیست، پس هشدارها خاموش می‌شوند.'}
                </span>
              </label>
            </Field>

            <Field label="شناسهٔ گفتگو (chat id)">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <SourceBadge source={data.chat_id_source} />
              </div>
              <input
                type="text"
                className="input w-full"
                dir="ltr"
                placeholder="-1001234567890"
                value={chatId}
                disabled={saving}
                onChange={(e) => setChatId(e.target.value)}
              />
              <p className="text-xs text-muted mt-1">
                شناسهٔ گفتگو رمز نیست، پس کامل نمایش داده می‌شود تا بتوانید درستی‌اش را بررسی کنید.
                خالی گذاشتن یعنی برگشتن به متغیر محیطی سرور
                {data.env_available.chat_id ? '.' : ' (که آن هم تنظیم نیست).'}
              </p>
            </Field>

            <div className="flex items-center gap-3 flex-wrap">
              <button className="btn btn-sm" onClick={save} disabled={!dirty || saving}>
                {saving ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (
                  <>
                    <Icon name="check" size={14} />
                    <span>ذخیره</span>
                  </>
                )}
              </button>
              {dirty && !saving && (
                <button
                  className="btn btn-sm"
                  style={{ background: 'var(--bg-elevated)' }}
                  onClick={() => { setBotToken(''); setClearToken(false); setChatId(data.chat_id || '') }}
                >
                  انصراف
                </button>
              )}
              {!dirty && <span className="text-xs text-muted">تغییری برای ذخیره وجود ندارد</span>}
            </div>

            {data.rows_missing.length > 0 && (
              <p className="text-xs text-muted">
                ردیف‌های ذخیره‌سازی هنوز در پایگاه داده ساخته نشده‌اند ({data.rows_missing.join('، ')}) — مهاجرت
                0044 هنوز اعمال نشده است. اولین ذخیره خودش ردیف را می‌سازد.
              </p>
            )}
          </div>

          {/* ── جایی که این اعتبارنامه استفاده می‌شود ─────────────────── */}
          <div className="admin-card">
            <h3 className="font-semibold text-sm text-primary mb-2">این اعتبارنامه کجا خوانده می‌شود</h3>
            <ul className="text-xs text-muted space-y-1">
              <li>• قفل‌شدن حساب پس از تلاش‌های ناموفق ورود — backend/security.py</li>
              <li>• دیده‌بان مالی (۱۳ قاعدهٔ CRITICAL/HIGH) — backend/watchdog.py، کانتینر جدا</li>
              <li>• پالایش محتوا (block/flag و خطای آشکارساز) — backend/services/moderation_store.py</li>
            </ul>
            <p className="text-xs text-muted mt-2">
              مقدار پنل بر متغیر محیطی اولویت دارد؛ اگر پنل خالی باشد متغیر محیطی سرور به‌کار می‌رود. اگر
              پایگاه داده در دسترس نباشد، هر سه مسیر به متغیر محیطی برمی‌گردند تا خطای تنظیمات هرگز مسیر
              گفتگو را نشکند.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
