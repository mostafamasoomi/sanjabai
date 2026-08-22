'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum } from '@/lib/format'
import { SectionHeader, StatCard } from './shared'

/* ═══════════════════════════════════════════════════════════════════════════
   Site Control — runtime, admin-editable site-wide switches. Closes the gap
   recorded in docs/ROADMAP.md Phase B ("ادمین بخش خاموش می‌کند"): before
   this, every real kill switch (TASK_SCHEDULER_ENABLED, OPENROUTER_ENABLED)
   was an environment variable an admin could not touch without SSH + a
   container restart.

   Self-contained (fetches its own data via the `api` prop), same pattern as
   ./MarkupSection.tsx and ./PackagesSection.tsx.

   Server contract (backend/site_settings.py):
     GET  /api/admin/site-settings  -> { flags: [{ key, value, default,
                                          label_fa, description_fa, wired,
                                          wire_note, row_missing }] }
     POST /api/admin/site-settings  <- { [flag_key]: boolean, ... }

   ── Honesty rules this component exists to enforce ──────────────────────
   1. A failed GET must render as a full-page error with a retry button --
      never as a list of switches silently shown "off", which the owner
      could mistake for the real state and act on.
   2. A flag whose `wired` is false must always show a visible "not yet
      wired" notice, both in the row and in the confirm dialog -- flipping
      it only changes a stored value today, not real behaviour, and this
      panel must never imply otherwise.
   3. Every toggle goes through an explicit confirm step that names the
      flag and what flipping it does, in Persian, before the request is
      sent -- these are site-wide effects, not a casual form field.
   ═══════════════════════════════════════════════════════════════════════════ */

interface SiteFlag {
  key: string
  value: boolean
  default: boolean
  label_fa: string
  description_fa: string
  wired: boolean
  wire_note: string
  row_missing: boolean
}

interface SiteControlSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

const FLAG_ICON: Record<string, React.ComponentProps<typeof Icon>['name']> = {
  maintenance_mode: 'security',
  signups_enabled: 'user',
  chat_enabled: 'chat',
  image_generation_enabled: 'camera',
  task_scheduler_enabled: 'clock',
  openrouter_enabled: 'globe',
}

export default function SiteControlSection({ api }: SiteControlSectionProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [flags, setFlags] = useState<SiteFlag[]>([])
  const [pending, setPending] = useState<{ flag: SiteFlag; next: boolean } | null>(null)
  const [saving, setSaving] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api('/api/admin/site-settings')
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `خطای سرور (${res.status})`)
      }
      const body = await res.json()
      setFlags(Array.isArray(body.flags) ? body.flags : [])
    } catch (e) {
      // Never fall back to an empty/default switch list here -- an error
      // must be visibly an error, not a set of switches that look like
      // real (and possibly wrong) state.
      setError(e instanceof Error ? e.message : 'خطا در دریافت تنظیمات سایت')
      setFlags([])
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => { load() }, [load])

  const requestToggle = (flag: SiteFlag) => {
    setPending({ flag, next: !flag.value })
  }

  const confirmToggle = async () => {
    if (!pending) return
    const { flag, next } = pending
    setSaving(flag.key)
    try {
      const res = await api('/api/admin/site-settings', {
        method: 'POST',
        body: JSON.stringify({ [flag.key]: next }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        toast(body.detail || 'ذخیره ناموفق بود', 'error')
        return
      }
      toast(`«${flag.label_fa}» ${next ? 'فعال' : 'غیرفعال'} شد`, 'success')
      setPending(null)
      await load()
    } catch {
      toast('ذخیره ناموفق بود', 'error')
    } finally {
      setSaving(null)
    }
  }

  const onCount = flags.filter((f) => f.value).length
  const unwiredCount = flags.filter((f) => !f.wired).length

  if (error) {
    return (
      <div className="space-y-6">
        <SectionHeader title="کنترل سایت" subtitle="سوییچ‌های سراسری برای روشن/خاموش کردن بخش‌های سایت" />
        <div className="admin-card" style={{ borderRight: '3px solid var(--danger, #ef4444)' }}>
          <div className="flex items-center gap-2 mb-2">
            <Icon name="warning" size={18} style={{ color: 'var(--danger, #ef4444)' }} />
            <h3 className="font-semibold text-sm text-primary">دریافت تنظیمات ناموفق بود</h3>
          </div>
          <p className="text-xs text-muted mb-4">{error}</p>
          <p className="text-xs mb-4" style={{ color: 'var(--warning, #f59e0b)' }}>
            وضعیت واقعی سوییچ‌ها نامشخص است -- تا رفع خطا هیچ سوییچی در این صفحه نمایش داده نمی‌شود، چون
            نمایش نادرست می‌تواند باعث تصمیم اشتباه شود.
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
      <SectionHeader title="کنترل سایت" subtitle="سوییچ‌های سراسری برای روشن/خاموش کردن بخش‌های سایت، بدون نیاز به ری‌استارت" />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard icon="settings" label="مجموع سوییچ‌ها" value={loading ? '—' : faNum(flags.length)} color="var(--accent)" />
        <StatCard icon="check" label="فعال" value={loading ? '—' : faNum(onCount)} color="#22c55e" />
        <StatCard icon="warning" label="هنوز وصل‌نشده" value={loading ? '—' : faNum(unwiredCount)} color="var(--warning, #f59e0b)" />
      </div>

      <div className="admin-card">
        {loading ? (
          <p className="p-6 text-center text-sm text-muted">در حال بارگذاری…</p>
        ) : flags.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted">سوییچی تعریف نشده است</p>
        ) : (
          <div className="space-y-3">
            {flags.map((flag) => (
              <div
                key={flag.key}
                className="flex items-start justify-between gap-4 p-3 rounded-lg flex-wrap"
                style={{ background: 'var(--bg-elevated)' }}
              >
                <div className="flex items-start gap-3 flex-1" style={{ minWidth: 220 }}>
                  <div className="p-2 rounded-lg" style={{ background: flag.value ? '#22c55e15' : 'var(--bg-base)' }}>
                    <Icon name={FLAG_ICON[flag.key] || 'settings'} size={16} style={{ color: flag.value ? '#22c55e' : 'var(--text-muted)' }} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-primary">{flag.label_fa}</span>
                      <span className="text-xs font-mono text-muted">{flag.key}</span>
                      {!flag.wired && (
                        <span
                          className="text-xs flex items-center gap-1 px-1.5 py-0.5 rounded"
                          style={{ color: 'var(--warning, #f59e0b)', background: 'color-mix(in srgb, var(--warning, #f59e0b) 12%, transparent)' }}
                          title={flag.wire_note}
                        >
                          <Icon name="warning" size={11} />
                          <span>هنوز وصل نشده</span>
                        </span>
                      )}
                      {flag.row_missing && (
                        <span className="text-xs text-muted">(مقدار پیش‌فرض -- هنوز در پایگاه داده ذخیره نشده)</span>
                      )}
                    </div>
                    <p className="text-xs text-muted mt-1">{flag.description_fa}</p>
                    {!flag.wired && flag.wire_note && (
                      <p className="text-xs mt-1" style={{ color: 'var(--warning, #f59e0b)' }}>{flag.wire_note}</p>
                    )}
                  </div>
                </div>
                <label className="flex items-center gap-2 cursor-pointer shrink-0">
                  <span className="text-xs text-muted">{flag.value ? 'فعال' : 'غیرفعال'}</span>
                  <input
                    type="checkbox"
                    checked={flag.value}
                    disabled={saving === flag.key}
                    onChange={() => requestToggle(flag)}
                    aria-label={`تغییر وضعیت ${flag.label_fa}`}
                  />
                </label>
              </div>
            ))}
          </div>
        )}
      </div>

      {pending && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.5)' }}
        >
          <div className="admin-card max-w-md w-full">
            <div className="flex items-center gap-2 mb-3">
              <Icon name="warning" size={18} style={{ color: 'var(--warning, #f59e0b)' }} />
              <h3 className="font-semibold text-sm text-primary">
                {pending.next ? 'فعال کردن' : 'غیرفعال کردن'} «{pending.flag.label_fa}»
              </h3>
            </div>
            <p className="text-sm text-secondary mb-3">{pending.flag.description_fa}</p>
            {!pending.flag.wired && (
              <p className="text-xs mb-3 p-2 rounded" style={{ color: 'var(--warning, #f59e0b)', background: 'color-mix(in srgb, var(--warning, #f59e0b) 12%, transparent)' }}>
                توجه: این سوییچ هنوز به هیچ رفتاری وصل نشده -- فقط مقدار در پایگاه داده ذخیره می‌شود.
                {pending.flag.wire_note}
              </p>
            )}
            <p className="text-xs text-muted mb-4">
              این یک تغییر سراسری روی کل سایت است. مطمئن هستید که می‌خواهید ادامه دهید؟
            </p>
            <div className="flex items-center gap-2 justify-end">
              <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => setPending(null)} disabled={saving === pending.flag.key}>
                انصراف
              </button>
              <button className="btn btn-sm" onClick={confirmToggle} disabled={saving === pending.flag.key}>
                {saving === pending.flag.key ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (
                  <>
                    <Icon name="check" size={14} />
                    <span>تأیید و اعمال</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
