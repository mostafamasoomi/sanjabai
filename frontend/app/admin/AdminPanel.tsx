'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon, type IconName } from '@/components/ui/Icon'
import { faNum, toFaDigits } from '@/lib/format'
import { toast } from '@/components/ui'
import dynamic from 'next/dynamic'

const AdminCharts = dynamic(() => import('./components/AdminCharts'), { ssr: false })

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjhubai Admin Panel — Aurora Design System
   RTL Persian, dark theme, Stripe/Linear inspired
   ═══════════════════════════════════════════════════════════════════════════ */

// ─── Types ───────────────────────────────────────────────────────────────────

type Page = 'dashboard' | 'pricing' | 'features' | 'discounts' | 'about' | 'proxy' | 'models' | 'users' | 'security'

interface Analytics {
  user_count: number
  active_users: number
  total_revenue: number
  total_tokens: number
  conv_count: number
  recent_ledger: { id: number; user_id: number; amount: number; reason: string; created_at: string }[]
}

interface PricingRow {
  model: string
  input_per_million: number
  output_per_million: number
  currency: string
  availability?: string
}

interface ModelTestResult {
  ok: boolean
  latency_ms: number
  error: string | null
  upstream?: string
}

interface CreditPackageRow {
  id: string
  name_fa: string
  name_en: string
  base_amount: number
  bonus_percent: number
  total_credits: number
  model_id: string | null
  active: boolean
  sort_order: number
}

interface FeatureRow {
  id: number
  title: string
  description: string
  icon: string
  order_idx: number
  active: boolean
}

interface DiscountRow {
  id: number
  code: string
  percent: number
  active: boolean
}

interface ProxyConfig {
  proxy_type: string
  proxy_url: string
  active: boolean
}

interface SecurityStats {
  threat_level: 'low' | 'medium' | 'high' | 'critical'
  failed_logins_24h: number
  active_sessions: number
  failed_login_chart: { hour: string; count: number }[]
  banned_users: { id: number; email: string; username: string; banned_at: string }[]
}

interface SecurityEvent {
  id: number
  event_type: string
  user_id: number | null
  user_email: string | null
  ip_address: string | null
  details: string | null
  created_at: string
}

interface AuditLog {
  id: number
  admin_id: number
  action: string
  target_type: string | null
  target_id: number | null
  details: string | null
  created_at: string
}

interface UserRow {
  id: number
  email: string
  username: string
  is_active: boolean
  plan: string
  wallet_balance: number
}

interface UserDetail {
  user: {
    id: number; email: string; phone: string; telegram_id: number;
    display_name: string; bio: string; avatar_url: string;
    timezone: string; language: string; banned: boolean;
    created_at: string; preferences: Record<string, unknown>;
  }
  balance: number
  wallet: { balance: number; reserved: number }
  quota: { daily_limit: number; used_today: number; reset_at: string } | null
  stats: {
    conversation_count: number; total_tokens: number;
    usage_events: number; total_cost: number;
    payment_count: number; total_payments: number;
  }
}

type UserDetailTab = 'overview' | 'conversations' | 'usage' | 'ledger' | 'payments'

// ─── Sidebar Navigation ──────────────────────────────────────────────────────

const NAV_ITEMS: { key: Page; label: string; icon: IconName }[] = [
  { key: 'dashboard', label: 'داشبورد', icon: 'dashboard' },
  { key: 'users', label: 'کاربران', icon: 'profile' },
  { key: 'pricing', label: 'تعرفه‌ها', icon: 'pricing' },
  { key: 'features', label: 'امکانات', icon: 'models' },
  { key: 'discounts', label: 'تخفیف‌ها', icon: 'wallet' },
  { key: 'about', label: 'درباره ما', icon: 'notification' },
  { key: 'proxy', label: 'پروکسی', icon: 'security' },
  { key: 'models', label: 'مدل‌ها', icon: 'code' },
  { key: 'security', label: 'امنیت', icon: 'lock' },
]

// Security dashboard threat-level colors — derived from design-token vars
// instead of raw hex so they follow the brand palette (and its light/dark
// swap) like everything else in the panel. 'high' has no dedicated token, so
// it's blended from the two nearest ones.
const THREAT_LEVEL_COLOR: Record<SecurityStats['threat_level'], string> = {
  critical: 'var(--danger)',
  high: 'color-mix(in srgb, var(--danger) 55%, var(--warning) 45%)',
  medium: 'var(--warning)',
  low: 'var(--positive)',
}

// ─── API Helper ──────────────────────────────────────────────────────────────

let TOKEN = ''

async function api(path: string, opts: RequestInit = {}) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (TOKEN) headers['Authorization'] = 'Bearer ' + TOKEN
  const res = await fetch(path, { ...opts, headers })
  if (res.status === 401) {
    TOKEN = ''
    throw new Error('unauthorized')
  }
  if (!res.ok) throw new Error(`خطای سرور (${res.status})`)
  return res
}

// ─── Stat Card ───────────────────────────────────────────────────────────────

function StatCard({ icon, label, value, color }: { icon: React.ComponentProps<typeof Icon>['name']; label: string; value: string | number; color: string }) {
  return (
    <div className="admin-card" style={{ borderRight: `3px solid ${color}` }}>
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 rounded-lg" style={{ background: `color-mix(in srgb, ${color} 15%, transparent)` }}>
          <Icon name={icon} size={18} className="opacity-80" style={{ color }} />
        </div>
        <span className="text-xs text-muted">{label}</span>
      </div>
      <p className="text-2xl font-bold text-primary">{value}</p>
    </div>
  )
}

// ─── Section Header ──────────────────────────────────────────────────────────

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-xl font-bold text-primary">{title}</h1>
      {subtitle && <p className="text-sm mt-1 text-muted">{subtitle}</p>}
    </div>
  )
}

// ─── Form Field ──────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium mb-1.5 text-secondary">{label}</label>
      {children}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════════════════

export default function AdminPage() {
  // ─── Auth State ──────────────────────────────────────────────────────────
  const [authed, setAuthed] = useState(false)
  const [tokenInput, setTokenInput] = useState('')
  const [loggingIn, setLoggingIn] = useState(false)
  const [page, setPage] = useState<Page>('dashboard')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // ─── Data State ──────────────────────────────────────────────────────────
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [prices, setPrices] = useState<PricingRow[]>([])
  const [creditPackages, setCreditPackages] = useState<CreditPackageRow[]>([])
  const [features, setFeatures] = useState<FeatureRow[]>([])
  const [discounts, setDiscounts] = useState<DiscountRow[]>([])
  const [proxyConfig, setProxyConfig] = useState<ProxyConfig>({ proxy_type: 'socks5', proxy_url: '', active: false })
  const [models, setModels] = useState<string[]>([])
  const [users, setUsers] = useState<UserRow[]>([])
  const [loading, setLoading] = useState(true)
  const [togglingModel, setTogglingModel] = useState<string | null>(null)
  const [testingModel, setTestingModel] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, ModelTestResult>>({})

  // ─── Pricing Form ────────────────────────────────────────────────────────
  const [pzModel, setPzModel] = useState('')
  const [pzIn, setPzIn] = useState('')
  const [pzOut, setPzOut] = useState('')
  const [pzCur, setPzCur] = useState('IRT')

  // ─── Credit / Token Package Form ─────────────────────────────────────────
  const [cpId, setCpId] = useState('')
  const [cpNameFa, setCpNameFa] = useState('')
  const [cpNameEn, setCpNameEn] = useState('')
  const [cpBaseAmount, setCpBaseAmount] = useState('')
  const [cpTotalCredits, setCpTotalCredits] = useState('')
  const [cpBonusPercent, setCpBonusPercent] = useState('0')
  const [cpModelId, setCpModelId] = useState('')
  const [cpSaving, setCpSaving] = useState(false)

  // ─── Features Form ───────────────────────────────────────────────────────
  const [ftId, setFtId] = useState('')
  const [ftTitle, setFtTitle] = useState('')
  const [ftDesc, setFtDesc] = useState('')
  const [ftIcon, setFtIcon] = useState('')
  const [ftOrder, setFtOrder] = useState('0')
  const [ftActive, setFtActive] = useState(true)

  // ─── Discounts Form ──────────────────────────────────────────────────────
  const [dcId, setDcId] = useState('')
  const [dcCode, setDcCode] = useState('')
  const [dcPercent, setDcPercent] = useState('10')
  const [dcActive, setDcActive] = useState(true)

  // ─── About Form ──────────────────────────────────────────────────────────
  const [abTitle, setAbTitle] = useState('')
  const [abBody, setAbBody] = useState('')

  // ─── Proxy Form ──────────────────────────────────────────────────────────
  const [pxType, setPxType] = useState('socks5')
  const [pxUrl, setPxUrl] = useState('')
  const [pxActive, setPxActive] = useState(true)

  // ─── Security State ─────────────────────────────────────────────
  const [securityStats, setSecurityStats] = useState<SecurityStats | null>(null)
  const [securityEvents, setSecurityEvents] = useState<SecurityEvent[]>([])
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
  const [auditPage, setAuditPage] = useState(1)
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditActionFilter, setAuditActionFilter] = useState('')
  const [securityLoading, setSecurityLoading] = useState(false)

  // ─── User Edit ────────────────────────────────────────────────────
  const [editingUser, setEditingUser] = useState<UserRow | null>(null)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [userDetail, setUserDetail] = useState<UserDetail | null>(null)
  const [userDetailTab, setUserDetailTab] = useState<UserDetailTab>('overview')
  const [userTabData, setUserTabData] = useState<any>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [userSearch, setUserSearch] = useState('')

  // ─── Org Default Model ─────────────────────────────────────────────
  const [orgDefaultModel, setOrgDefaultModel] = useState('')
  const [orgDefaultSaving, setOrgDefaultSaving] = useState(false)

  // ─── Load Data

  const loadAll = useCallback(async () => {
    setLoading(true)
    const tasks = [
      { fn: async () => { const r = await api('/api/admin/analytics'); setAnalytics(await r.json()) }, label: 'analytics' },
      { fn: async () => { const r = await api('/api/admin/pricing'); setPrices(await r.json()) }, label: 'pricing' },
      { fn: async () => { const r = await api('/api/admin/features'); setFeatures(await r.json()) }, label: 'features' },
      { fn: async () => { const r = await api('/api/admin/discounts'); setDiscounts(await r.json()) }, label: 'discounts' },
      { fn: async () => { const r = await api('/api/admin/credit-packages'); setCreditPackages(await r.json()) }, label: 'credit-packages' },
      { fn: async () => {
        const r = await api('/api/admin/about')
        const d = await r.json()
        setAbTitle(d.title || '')
        setAbBody(d.body || '')
      }, label: 'about' },
      { fn: async () => {
        const r = await api('/api/admin/proxy')
        const d = await r.json()
        setProxyConfig(d)
        setPxType(d.proxy_type || 'socks5')
        setPxUrl(d.proxy_url || '')
        setPxActive(d.active !== false)
      }, label: 'proxy' },
      { fn: async () => {
        const r = await fetch('/api/models')
        const d = await r.json()
        setModels((d.data || []).map((m: { id: string }) => m.id))
      }, label: 'models' },
      { fn: async () => { const r = await api('/api/admin/users'); const d = await r.json(); setUsers(d.users || d) }, label: 'users' },
      { fn: async () => {
        try {
          const r = await fetch('/api/org/default-model')
          const d = await r.json()
          setOrgDefaultModel(d.default_model || '')
        } catch {}
      }, label: 'org-default-model' },
    ]

    await Promise.allSettled(tasks.map((t) => t.fn()))
    setLoading(false)
  }, [])

  useEffect(() => {
    if (authed) loadAll()
  }, [authed, loadAll])

  // ─── Security Data Loading ───────────────────────────────────────
  const loadSecurityData = useCallback(async () => {
    setSecurityLoading(true)
    try {
      const [statsRes, eventsRes] = await Promise.allSettled([
        api('/api/admin/security/stats'),
        api('/api/admin/audit-logs?page=' + auditPage + (auditActionFilter ? '&action=' + auditActionFilter : '')),
      ])
      if (statsRes.status === 'fulfilled') {
        const stats = await statsRes.value.json()
        setSecurityStats(stats)
      }
      if (eventsRes.status === 'fulfilled') {
        const data = await eventsRes.value.json()
        setSecurityEvents(data.events || data.security_events || [])
        setAuditLogs(data.audit_logs || [])
        setAuditTotal(data.total || 0)
      }
    } catch {
      // Silently handle — stats may not be available yet
    } finally {
      setSecurityLoading(false)
    }
  }, [auditPage, auditActionFilter])

  useEffect(() => {
    if (authed && page === 'security') {
      loadSecurityData()
    }
  }, [authed, page, loadSecurityData])

  // ─── Auto-refresh every 30 seconds when on security page ─────────
  useEffect(() => {
    if (!authed || page !== 'security') return
    const interval = setInterval(() => {
      loadSecurityData()
    }, 30000)
    return () => clearInterval(interval)
  }, [authed, page, loadSecurityData])

  // ─── Unban User ──────────────────────────────────────────────────
  const unbanUser = async (uid: number) => {
    try {
      await api(`/api/admin/users/${uid}/ban`, { method: 'DELETE' })
      toast('کاربر رفع مسدودیت شد', 'success')
      loadSecurityData()
      loadAll()
    } catch { toast('خطا در رفع مسدودیت', 'error') }
  }

  // ─── Audit Log Filter ────────────────────────────────────────────
  const loadAuditWithFilter = async (action: string) => {
    setAuditActionFilter(action)
    setAuditPage(1)
  }

  // ─── Login ───────────────────────────────────────────────────────────────

  const login = async () => {
    const token = tokenInput.trim()
    if (!token) return
    setLoggingIn(true)
    try {
      const res = await fetch('/api/admin/analytics', { headers: { Authorization: 'Bearer ' + token } })
      if (res.ok) {
        TOKEN = token
        setAuthed(true)
        toast('ورود موفقیت‌آمیز بود', 'success')
      } else {
        toast('توکن نامعتبر است', 'error')
      }
    } catch {
      toast('خطا در اتصال به سرور', 'error')
    } finally {
      setLoggingIn(false)
    }
  }

  // ─── Pricing Actions ─────────────────────────────────────────────────────

  const savePricing = async () => {
    if (!pzModel.trim()) return
    try {
      await api('/api/admin/pricing', {
        method: 'POST',
        body: JSON.stringify({ model: pzModel, input_per_million: +pzIn || 0, output_per_million: +pzOut || 0, currency: pzCur }),
      })
      toast('تعرفه ذخیره شد', 'success')
      setPzModel(''); setPzIn(''); setPzOut(''); setPzCur('IRT')
      loadAll()
    } catch { toast('خطا در ذخیره تعرفه', 'error') }
  }

  const saveCreditPackage = async () => {
    if (!cpId.trim()) { toast('شناسه بسته الزامی است', 'error'); return }
    setCpSaving(true)
    try {
      await api('/api/admin/credit-packages', {
        method: 'POST',
        body: JSON.stringify({
          id: cpId,
          name_fa: cpNameFa,
          name_en: cpNameEn,
          base_amount: +cpBaseAmount || 0,
          bonus_percent: +cpBonusPercent || 0,
          total_credits: +cpTotalCredits || +cpBaseAmount || 0,
          model_id: cpModelId || null,
          active: true,
        }),
      })
      toast('بسته ذخیره شد', 'success')
      setCpId(''); setCpNameFa(''); setCpNameEn(''); setCpBaseAmount(''); setCpTotalCredits(''); setCpBonusPercent('0'); setCpModelId('')
      loadAll()
    } catch {
      toast('خطا در ذخیره بسته', 'error')
    } finally {
      setCpSaving(false)
    }
  }

  const toggleCreditPackageActive = async (pkg: CreditPackageRow) => {
    try {
      await api('/api/admin/credit-packages', {
        method: 'POST',
        body: JSON.stringify({ id: pkg.id, active: !pkg.active }),
      })
      setCreditPackages((prev) => prev.map((p) => (p.id === pkg.id ? { ...p, active: !p.active } : p)))
    } catch {
      toast('خطا در تغییر وضعیت بسته', 'error')
    }
  }

  const toggleModel = async (model: string, currentAvailability?: string) => {
    setTogglingModel(model)
    try {
      const r = await api(`/api/admin/models/${encodeURIComponent(model)}/toggle`, { method: 'POST' })
      const data = await r.json()
      toast(
        data.availability === 'available' ? `${model} فعال شد` : `${model} غیرفعال شد`,
        'success',
      )
      setPrices((prev) => prev.map((p) => (p.model === model ? { ...p, availability: data.availability } : p)))
    } catch {
      toast('خطا در تغییر وضعیت مدل', 'error')
    } finally {
      setTogglingModel(null)
    }
  }

  const testModel = async (model: string) => {
    setTestingModel(model)
    try {
      const r = await api(`/api/admin/models/${encodeURIComponent(model)}/test`, { method: 'POST' })
      const data = await r.json()
      setTestResults((prev) => ({ ...prev, [model]: data }))
      toast(data.ok ? `${model} پاسخ داد (${data.latency_ms}ms)` : `${model} پاسخ نداد: ${data.error || 'نامشخص'}`, data.ok ? 'success' : 'error')
    } catch {
      toast('خطا در تست مدل', 'error')
    } finally {
      setTestingModel(null)
    }
  }

  // ─── Features Actions ────────────────────────────────────────────────────

  const saveFeature = async () => {
    if (!ftTitle.trim()) return
    try {
      await api('/api/admin/features', {
        method: 'POST',
        body: JSON.stringify({ id: ftId ? +ftId : undefined, title: ftTitle, description: ftDesc, icon: ftIcon, order_idx: +ftOrder || 0, active: ftActive }),
      })
      toast(ftId ? 'ویژگی ویرایش شد' : 'ویژگی اضافه شد', 'success')
      resetFeatureForm()
      loadAll()
    } catch { toast('خطا در ذخیره ویژگی', 'error') }
  }

  const editFeature = (f: FeatureRow) => {
    setFtId(String(f.id)); setFtTitle(f.title); setFtDesc(f.description); setFtIcon(f.icon)
    setFtOrder(String(f.order_idx)); setFtActive(f.active)
  }

  const delFeature = async (id: number) => {
    try {
      await api('/api/admin/features/' + id, { method: 'DELETE' })
      toast('ویژگی حذف شد', 'success')
      loadAll()
    } catch { toast('خطا در حذف ویژگی', 'error') }
  }

  const resetFeatureForm = () => {
    setFtId(''); setFtTitle(''); setFtDesc(''); setFtIcon(''); setFtOrder('0'); setFtActive(true)
  }

  // ─── Discounts Actions ───────────────────────────────────────────────────

  const saveDiscount = async () => {
    if (!dcCode.trim()) return
    try {
      await api('/api/admin/discounts', {
        method: 'POST',
        body: JSON.stringify({ id: dcId ? +dcId : undefined, code: dcCode, percent: +dcPercent || 0, active: dcActive }),
      })
      toast(dcId ? 'تخفیف ویرایش شد' : 'تخفیف اضافه شد', 'success')
      resetDiscountForm()
      loadAll()
    } catch { toast('خطا در ذخیره تخفیف', 'error') }
  }

  const editDiscount = (d: DiscountRow) => {
    setDcId(String(d.id)); setDcCode(d.code); setDcPercent(String(d.percent)); setDcActive(d.active)
  }

  const delDiscount = async (id: number) => {
    try {
      await api('/api/admin/discounts/' + id, { method: 'DELETE' })
      toast('تخفیف حذف شد', 'success')
      loadAll()
    } catch { toast('خطا در حذف تخفیف', 'error') }
  }

  const resetDiscountForm = () => {
    setDcId(''); setDcCode(''); setDcPercent('10'); setDcActive(true)
  }

  // ─── About Actions ───────────────────────────────────────────────────────

  const saveAbout = async () => {
    try {
      await api('/api/admin/about', { method: 'POST', body: JSON.stringify({ title: abTitle, body: abBody }) })
      toast('درباره ما ذخیره شد', 'success')
    } catch { toast('خطا در ذخیره', 'error') }
  }

  // ─── Proxy Actions ───────────────────────────────────────────────────────

  const saveProxy = async () => {
    try {
      await api('/api/admin/proxy', { method: 'POST', body: JSON.stringify({ proxy_type: pxType, proxy_url: pxUrl, active: pxActive }) })
      toast('تنظیمات پروکسی ذخیره شد', 'success')
      loadAll()
    } catch { toast('خطا در ذخیره پروکسی', 'error') }
  }

  // ─── Org Default Model Actions ───────────────────────────────────────

  const saveOrgDefaultModel = async () => {
    setOrgDefaultSaving(true)
    try {
      await api('/api/admin/org-default-model', {
        method: 'POST',
        body: JSON.stringify({ default_model: orgDefaultModel || null }),
      })
      toast('مدل پیشفرض سازمان ذخیره شد', 'success')
    } catch { toast('خطا در ذخیره مدل پیشفرض', 'error') }
    finally { setOrgDefaultSaving(false) }
  }

  // ─── User Actions ────────────────────────────────────────────────────────

  const banUser = async (uid: number) => {
    try {
      await api(`/api/admin/users/${uid}/ban`, { method: 'POST' })
      toast('کاربر مسدود شد', 'success')
      loadAll()
    } catch { toast('خطا در مسدودسازی', 'error') }
  }

  const saveUserEdit = async () => {
    if (!editingUser) return
    try {
      await api(`/api/admin/users/${editingUser.id}`, {
        method: 'PUT',
        body: JSON.stringify(editingUser),
      })
      toast('کاربر ویرایش شد', 'success')
      setEditingUser(null)
      loadAll()
    } catch { toast('خطا در ویرایش کاربر', 'error') }
  }

  // ─── User Detail Actions ─────────────────────────────────────────

  const openUserDetail = async (uid: number) => {
    setSelectedUserId(uid)
    setUserDetailTab('overview')
    setUserTabData(null)
    setLoadingDetail(true)
    try {
      const r = await api(`/api/admin/users/${uid}/detail`)
      setUserDetail(await r.json())
    } catch { toast('خطا در بارگذاری جزئیات', 'error') }
    finally { setLoadingDetail(false) }
  }

  const loadUserTab = async (tab: UserDetailTab) => {
    if (!selectedUserId) return
    setUserDetailTab(tab)
    setLoadingDetail(true)
    setUserTabData(null)
    try {
      const r = await api(`/api/admin/users/${selectedUserId}/${tab}`)
      setUserTabData(await r.json())
    } catch { toast('خطا در بارگذاری', 'error') }
    finally { setLoadingDetail(false) }
  }

  // ─── Logout ──────────────────────────────────────────────────────────────

  const logout = () => {
    TOKEN = ''
    setAuthed(false)
    setTokenInput('')
    setAnalytics(null)
    setPrices([])
    setFeatures([])
    setDiscounts([])
    setModels([])
    setUsers([])
  }

  // ═════════════════════════════════════════════════════════════════════════
  // RENDER: Login Screen
  // ═════════════════════════════════════════════════════════════════════════

  if (!authed) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4" style={{ background: 'var(--bg-base)' }}>
        <div className="card w-full max-w-sm">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4" style={{ background: 'var(--accent-dim)' }}>
              <Icon name="settings" size={28} className="text-accent" />
            </div>
            <h1 className="text-xl font-bold text-primary">پنل مدیریت</h1>
            <p className="text-sm mt-1 text-muted">داشبورد مدیریت Sanjhubai</p>
          </div>

          <div className="space-y-4">
            <Field label="توکن ادمین">
              <input
                type="password"
                className="input w-full"
                placeholder="توکن خود را وارد کنید..."
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && login()}
                autoFocus
              />
            </Field>
            <button
              className="btn btn-lg w-full"
              onClick={login}
              disabled={loggingIn || !tokenInput.trim()}
            >
              {loggingIn ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  در حال ورود...
                </span>
              ) : (
                'ورود'
              )}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ═════════════════════════════════════════════════════════════════════════
  // RENDER: Admin Panel
  // ═════════════════════════════════════════════════════════════════════════

  const currentNav = NAV_ITEMS.find((n) => n.key === page)

  return (
    <div className="admin-layout min-h-screen" dir="rtl">
      {/* Mobile Header */}
      <div className="lg:hidden flex items-center justify-between p-4 border-b" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <button className="btn btn-icon btn-sm" onClick={() => setSidebarOpen(!sidebarOpen)}>
          <Icon name={sidebarOpen ? 'close' : 'menu'} size={20} />
        </button>
        <span className="text-sm font-bold text-accent">
          {currentNav?.label}
        </span>
        <button className="btn btn-icon btn-sm" onClick={logout}>
          <Icon name="logout" size={18} />
        </button>
      </div>

      <div className="flex">
        {/* ─── Sidebar ─────────────────────────────────────────────────── */}
        <aside
          className={`
            fixed lg:sticky top-0 right-0 z-40 h-screen w-64 shrink-0
            border-l overflow-y-auto transition-transform duration-200 slide-up
            lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : 'translate-x-full lg:translate-x-0'}
          `}
          style={{
            background: 'var(--bg-surface)',
            borderColor: 'var(--border)',
          }}
        >
          {/* Logo */}
          <div className="p-5 border-b" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'var(--accent-dim)' }}>
                <Icon name="settings" size={18} className="text-accent" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-primary">Sanjhubai</h2>
                <p className="text-[10px] text-muted">Admin Panel</p>
              </div>
            </div>
          </div>

          {/* Navigation */}
          <nav className="p-3 space-y-0.5">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.key}
                className={`
                  w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150
                  ${page === item.key
                    ? 'font-medium'
                    : 'hover:opacity-80'
                  }
                `}
                style={{
                  background: page === item.key ? 'var(--accent-dim)' : 'transparent',
                  color: page === item.key ? 'var(--accent)' : 'var(--text-secondary)',
                }}
                onClick={() => { setPage(item.key); setSidebarOpen(false) }}
              >
                <Icon name={item.icon} size={18} />
                <span>{item.label}</span>
                {item.key === 'users' && users.length > 0 && (
                  <span className="badge badge-accent mr-auto text-[10px]">{faNum(users.length)}</span>
                )}
                {item.key === 'models' && models.length > 0 && (
                  <span className="badge badge-accent mr-auto text-[10px]">{faNum(models.length)}</span>
                )}
              </button>
            ))}
          </nav>

          {/* Sidebar Footer */}
          <div className="absolute bottom-0 right-0 left-0 p-3 border-t" style={{ borderColor: 'var(--border)' }}>
            <button
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors text-muted"
              onClick={logout}
            >
              <Icon name="logout" size={18} />
              <span>خروج</span>
            </button>
          </div>
        </aside>

        {/* Mobile Overlay */}
        {sidebarOpen && (
          <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setSidebarOpen(false)} />
        )}

        {/* ─── Main Content ────────────────────────────────────────────── */}
        <main className="admin-main flex-1 min-w-0 p-4 lg:p-8 overflow-y-auto" style={{ background: 'var(--bg-base)' }}>
          {/* Refresh Button */}
          <div className="flex items-center justify-between mb-6 slide-up">
            <div>
              <h1 className="text-xl font-bold text-primary">{currentNav?.label}</h1>
            </div>
            <button className="btn btn-sm" onClick={page === 'security' ? loadSecurityData : loadAll} title="بروزرسانی">
              <Icon name="refresh" size={16} />
            </button>
          </div>

          {/* ─────────────────────────────────────────────────────────────
              داشبورد
             ───────────────────────────────────────────────────────────── */}
          {page === 'dashboard' && (
            <div className="space-y-6">
              {analytics ? (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
                    <StatCard icon="profile" label="کل کاربران" value={faNum(analytics.user_count)} color="var(--accent)" />
                    <StatCard icon="check" label="کاربران فعال" value={faNum(analytics.active_users)} color="var(--positive)" />
                    <StatCard icon="payment" label="درآمد کل (تومان)" value={faNum(analytics.total_revenue, { fallback: '۰' })} color="var(--info)" />
                    <StatCard icon="code" label="توکن مصرفی" value={faNum(analytics.total_tokens, { fallback: '۰' })} color="var(--warning)" />
                    <StatCard icon="chat" label="گفتگوها" value={faNum(analytics.conv_count, { fallback: '۰' })} color="var(--accent)" />
                  </div>

                  {/* Charts */}
                  <AdminCharts />

                  <div className="admin-card">
                    <div className="flex items-center gap-2 mb-4">
                      <Icon name="history" size={18} className="text-secondary" />
                      <h3 className="font-semibold text-sm text-primary">تراکنش‌های اخیر</h3>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="admin-table w-full text-sm">
                        <thead>
                          <tr>
                            <th className="text-right p-3">شناسه کاربر</th>
                            <th className="text-right p-3">مبلغ</th>
                            <th className="text-right p-3">شرح</th>
                            <th className="text-right p-3">تاریخ</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(analytics.recent_ledger || []).length === 0 ? (
                            <tr>
                              <td colSpan={4} className="p-6 text-center text-sm text-muted">
                                تراکنشی ثبت نشده
                              </td>
                            </tr>
                          ) : (
                            (analytics.recent_ledger || []).map((l: any) => (
                              <tr key={l.id}>
                                <td className="p-3 text-xs font-mono">{l.user_id}</td>
                                <td className="p-3">
                                  <span className={l.amount > 0 ? 'badge badge-positive' : 'badge badge-danger'}>
                                    {l.amount > 0 ? '+' : ''}{faNum(l.amount)}
                                  </span>
                                </td>
                                <td className="p-3 text-xs text-secondary">{l.reason}</td>
                                <td className="p-3 text-xs text-muted">
                                  {new Date(l.created_at).toLocaleDateString('fa-IR')}
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="admin-card">
                      <div className="skeleton h-3 w-20 mb-3 rounded" />
                      <div className="skeleton h-7 w-16 rounded" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────────
              Users
             ───────────────────────────────────────────────────────────── */}
          {page === 'users' && !selectedUserId && (
            <div className="space-y-4">
              <SectionHeader title="مدیریت کاربران" subtitle={`${faNum(users.length)} کاربر ثبت‌نام شده`} />
              <div className="admin-card">
                <div style={{ position: 'relative' }}>
                  <Icon name="search" size={16} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
                  <input
                    className="input w-full"
                    placeholder="جستجو: ایمیل، نام، شناسه..."
                    value={userSearch}
                    onChange={(e) => setUserSearch(e.target.value)}
                    style={{ paddingRight: '2.5rem' }}
                  />
                </div>
              </div>
              <div className="admin-card overflow-x-auto">
                <table className="admin-table w-full text-sm">
                  <thead>
                    <tr>
                      <th className="text-right p-3">شناسه</th>
                      <th className="text-right p-3">نام کاربری</th>
                      <th className="text-right p-3">ایمیل</th>
                      <th className="text-right p-3">پلن</th>
                      <th className="text-right p-3">موجودی</th>
                      <th className="text-right p-3">وضعیت</th>
                      <th className="text-right p-3">عملیات</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.filter(u => {
                      if (!userSearch) return true
                      const q = userSearch.toLowerCase()
                      return (u.username || '').toLowerCase().includes(q) ||
                             (u.email || '').toLowerCase().includes(q) ||
                             String(u.id).includes(q)
                    }).length === 0 ? (
                      <tr>
                        <td colSpan={7} className="p-6 text-center text-sm text-muted">
                          کاربری یافت نشد
                        </td>
                      </tr>
                    ) : (
                      users.filter(u => {
                        if (!userSearch) return true
                        const q = userSearch.toLowerCase()
                        return (u.username || '').toLowerCase().includes(q) ||
                               (u.email || '').toLowerCase().includes(q) ||
                               String(u.id).includes(q)
                      }).map((u) => (
                        <tr key={u.id} className="cursor-pointer hover:bg-[var(--bg-elevated)]" onClick={() => openUserDetail(u.id)}>
                          <td className="p-3 text-xs font-mono">{u.id}</td>
                          <td className="p-3 text-sm font-medium text-primary">{u.username || '—'}</td>
                          <td className="p-3 text-xs text-secondary">{u.email}</td>
                          <td className="p-3">
                            <span className="badge badge-accent">{u.plan || 'رایگان'}</span>
                          </td>
                          <td className="p-3 text-xs">{faNum(u.wallet_balance)}</td>
                          <td className="p-3">
                            <span className={u.is_active ? 'badge badge-positive' : 'badge badge-danger'}>
                              {u.is_active ? 'فعال' : 'غیرفعال'}
                            </span>
                          </td>
                          <td className="p-3">
                            <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                              <button className="btn btn-sm" onClick={() => setEditingUser(u)} title="ویرایش">
                                <Icon name="settings" size={14} />
                              </button>
                              <button className="btn btn-sm" onClick={() => openUserDetail(u.id)} title="جزئیات">
                                <Icon name="search" size={14} />
                              </button>
                              {u.is_active && (
                                <button className="btn btn-sm btn-danger" onClick={() => banUser(u.id)} title="مسدودسازی">
                                  <Icon name="security" size={14} />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* User Edit Modal */}
              {editingUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setEditingUser(null)}>
                  <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
                  <div className="card relative w-full max-w-md" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-bold text-primary">ویرایش کاربر</h3>
                      <button className="btn btn-icon btn-sm" onClick={() => setEditingUser(null)}>
                        <Icon name="close" size={16} />
                      </button>
                    </div>
                    <div className="space-y-3">
                      <Field label="نام کاربری">
                        <input className="input w-full" value={editingUser.username || ''} onChange={(e) => setEditingUser({ ...editingUser, username: e.target.value })} />
                      </Field>
                      <Field label="ایمیل">
                        <input className="input w-full" value={editingUser.email || ''} onChange={(e) => setEditingUser({ ...editingUser, email: e.target.value })} />
                      </Field>
                      <Field label="پلن">
                        <select className="input w-full" value={editingUser.plan || ''} onChange={(e) => setEditingUser({ ...editingUser, plan: e.target.value })}>
                          <option value="">رایگان</option>
                          <option value="pro">Pro</option>
                          <option value="enterprise">Enterprise</option>
                        </select>
                      </Field>
                      <Field label="موجودی کیف پول">
                        <input className="input w-full" type="number" value={editingUser.wallet_balance || 0} onChange={(e) => setEditingUser({ ...editingUser, wallet_balance: +e.target.value })} />
                      </Field>
                    </div>
                    <div className="flex gap-2 mt-5">
                      <button className="btn flex-1" onClick={saveUserEdit}>ذخیره</button>
                      <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => setEditingUser(null)}>انصراف</button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── User Detail View ─────────────────────────────────────── */}
          {page === 'users' && selectedUserId && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <button className="btn btn-ghost btn-sm" onClick={() => { setSelectedUserId(null); setUserDetail(null); setUserTabData(null) }}>
                  <Icon name="close" size={14} /> بازگشت
                </button>
                <SectionHeader title={`کاربر #${selectedUserId}`} subtitle={userDetail?.user?.email || ''} />
              </div>

              {loadingDetail && !userDetail && (
                <div className="admin-card"><div className="skeleton h-40 w-full rounded" /></div>
              )}

              {userDetail && (
                <>
                  {/* Stat Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
                    <StatCard icon="wallet" label="موجودی" value={faNum(userDetail.balance)} color="var(--positive)" />
                    <StatCard icon="models" label="توکن مصرفی" value={faNum(userDetail.stats.total_tokens)} color="var(--info)" />
                    <StatCard icon="chat" label="گفتگوها" value={userDetail.stats.conversation_count} color="var(--accent-purple)" />
                    <StatCard icon="pricing" label="هزینه کل" value={faNum(userDetail.stats.total_cost)} color="var(--warning)" />
                    <StatCard icon="wallet" label="پرداخت‌ها" value={userDetail.stats.payment_count} color="var(--accent)" />
                    <StatCard icon="dashboard" label="درخواست‌ها" value={userDetail.stats.usage_events} color="var(--danger)" />
                  </div>

                  {/* User Info Card */}
                  <div className="admin-card">
                    <div className="flex items-start gap-4">
                      <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
                        {(userDetail.user.display_name || userDetail.user.email || '?')[0].toUpperCase()}
                      </div>
                      <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                        <div><span className="text-muted">نام</span><p className="font-medium">{userDetail.user.display_name || '—'}</p></div>
                        <div><span className="text-muted">ایمیل</span><p className="font-medium">{userDetail.user.email || '—'}</p></div>
                        <div><span className="text-muted">تلگرام</span><p className="font-medium">{userDetail.user.telegram_id || '—'}</p></div>
                        <div><span className="text-muted">تلفن</span><p className="font-medium">{userDetail.user.phone || '—'}</p></div>
                        <div><span className="text-muted">کیف پول</span><p className="font-medium">{faNum(userDetail.wallet.balance)} (رزرو: {faNum(userDetail.wallet.reserved)})</p></div>
                        <div><span className="text-muted">سهمیه روزانه</span><p className="font-medium">{faNum(userDetail.quota?.daily_limit) || '—'}</p></div>
                        <div><span className="text-muted">مصرف امروز</span><p className="font-medium">{faNum(userDetail.quota?.used_today, { fallback: '۰' })}</p></div>
                        <div><span className="text-muted">عضویت</span><p className="font-medium">{new Date(userDetail.user.created_at).toLocaleDateString('fa-IR')}</p></div>
                      </div>
                    </div>
                    {String(userDetail.user.preferences?.ai_personality || '') && (
                      <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: 'var(--bg-elevated)' }}>
                        <span className="font-bold text-accent">🧠 Soul: </span>
                        <span className="text-secondary">{String(userDetail.user.preferences.ai_personality)}</span>
                      </div>
                    )}
                  </div>

                  {/* Tabs */}
                  <div className="flex gap-1 border-b" style={{ borderColor: 'var(--border)' }}>
                    {(['overview', 'conversations', 'usage', 'ledger', 'payments'] as UserDetailTab[]).map(tab => (
                      <button
                        key={tab}
                        className={`px-4 py-2 text-xs font-medium transition-colors ${userDetailTab === tab ? 'border-b-2' : 'opacity-60 hover:opacity-100'}`}
                        style={userDetailTab === tab ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : { color: 'var(--text-secondary)' }}
                        onClick={() => loadUserTab(tab)}
                      >
                        {{ overview: 'نمای کلی', conversations: 'گفتگوها', usage: 'مصرف توکن', ledger: 'تراکنش‌ها', payments: 'پرداخت‌ها' }[tab]}
                      </button>
                    ))}
                  </div>

                  {/* Tab Content */}
                  <div className="admin-card min-h-[200px]">
                    {loadingDetail && <div className="skeleton h-32 w-full rounded" />}
                    {!loadingDetail && userDetailTab === 'overview' && (
                      <div className="text-sm text-secondary">
                        <p>از تب‌های بالا برای مشاهده جزئیات استفاده کنید.</p>
                      </div>
                    )}
                    {!loadingDetail && userDetailTab === 'conversations' && userTabData && (
                      <div className="overflow-x-auto">
                        <table className="admin-table w-full text-sm">
                          <thead><tr>
                            <th className="text-right p-2">شناسه</th><th className="text-right p-2">عنوان</th>
                            <th className="text-right p-2">مدل</th><th className="text-right p-2">پیامها</th>
                            <th className="text-right p-2">تاریخ</th>
                          </tr></thead>
                          <tbody>
                            {(userTabData?.items || []).map((c: any) => (
                              <tr key={c.id}>
                                <td className="p-2 text-xs font-mono">{c.id}</td>
                                <td className="p-2 text-xs">{c.title}</td>
                                <td className="p-2 text-xs"><span className="badge badge-accent">{c.model || '—'}</span></td>
                                <td className="p-2 text-xs">{c.msg_count || '—'}</td>
                                <td className="p-2 text-xs">{new Date(c.updated_at).toLocaleDateString('fa-IR')}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <p className="text-xs mt-2 text-muted">
                          {(userTabData?.total || 0)} گفتگو
                        </p>
                      </div>
                    )}
                    {!loadingDetail && userDetailTab === 'usage' && userTabData && (
                      <div className="space-y-4">
                        <h3 className="text-sm font-bold text-primary">مصرف بر اساس مدل</h3>
                        <table className="admin-table w-full text-sm">
                          <thead><tr>
                            <th className="text-right p-2">مدل</th><th className="text-right p-2">درخواست</th>
                            <th className="text-right p-2">ورودی</th><th className="text-right p-2">خروجی</th>
                            <th className="text-right p-2">هزینه</th><th className="text-right p-2">آخرین استفاده</th>
                          </tr></thead>
                          <tbody>
                            {(userTabData?.by_model || []).map((m: any, i: number) => (
                              <tr key={i}>
                                <td className="p-2 text-xs font-medium">{m.model}</td>
                                <td className="p-2 text-xs">{m.calls}</td>
                                <td className="p-2 text-xs">{faNum(m.input_tokens || 0)}</td>
                                <td className="p-2 text-xs">{faNum(m.output_tokens || 0)}</td>
                                <td className="p-2 text-xs">{faNum(m.total_cost || 0)}</td>
                                <td className="p-2 text-xs">{m.last_used ? new Date(m.last_used).toLocaleDateString('fa-IR') : '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {!loadingDetail && userDetailTab === 'ledger' && userTabData && (
                      <div className="overflow-x-auto">
                        <table className="admin-table w-full text-sm">
                          <thead><tr>
                            <th className="text-right p-2">شناسه</th><th className="text-right p-2">مبلغ</th>
                            <th className="text-right p-2">مانده</th><th className="text-right p-2">شرح</th>
                            <th className="text-right p-2">تاریخ</th>
                          </tr></thead>
                          <tbody>
                            {(userTabData?.items || []).map((l: any) => (
                              <tr key={l.id}>
                                <td className="p-2 text-xs font-mono">{l.id}</td>
                                <td className={`p-2 text-xs font-bold ${l.amount >= 0 ? 'text-green-400' : 'text-red-400'}`}>{l.amount >= 0 ? '+' : ''}{faNum(l.amount)}</td>
                                <td className="p-2 text-xs">{faNum(l.balance_after)}</td>
                                <td className="p-2 text-xs">{l.reason}</td>
                                <td className="p-2 text-xs">{new Date(l.created_at).toLocaleDateString('fa-IR')}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <p className="text-xs mt-2 text-muted">
                          {(userTabData?.total || 0)} تراکنش
                        </p>
                      </div>
                    )}
                    {!loadingDetail && userDetailTab === 'payments' && userTabData && (
                      <div className="space-y-4">
                        <h3 className="text-sm font-bold text-primary">پرداخت‌ها</h3>
                        <table className="admin-table w-full text-sm">
                          <thead><tr>
                            <th className="text-right p-2">شناسه</th><th className="text-right p-2">مبلغ</th>
                            <th className="text-right p-2">وضعیت</th><th className="text-right p-2">نوع</th>
                            <th className="text-right p-2">کد مرجع</th><th className="text-right p-2">تاریخ</th>
                          </tr></thead>
                          <tbody>
                            {(userTabData?.payments || []).map((p: any) => (
                              <tr key={p.id}>
                                <td className="p-2 text-xs font-mono">{p.id}</td>
                                <td className="p-2 text-xs font-bold">{faNum(p.amount)}</td>
                                <td className="p-2"><span className={`badge ${p.status === 'verified' ? 'badge-positive' : p.status === 'pending' ? 'badge-accent' : 'badge-danger'}`}>{p.status === 'verified' ? 'تایید شده' : p.status === 'pending' ? 'در انتظار' : 'ناموفق'}</span></td>
                                <td className="p-2 text-xs">{p.payment_type}</td>
                                <td className="p-2 text-xs font-mono">{p.ref_id || '—'}</td>
                                <td className="p-2 text-xs">{new Date(p.created_at).toLocaleDateString('fa-IR')}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {(userTabData?.subscriptions || []).length > 0 && (
                          <>
                            <h3 className="text-sm font-bold text-primary">اشتراکها</h3>
                            <table className="admin-table w-full text-sm">
                              <thead><tr>
                                <th className="text-right p-2">پلن</th><th className="text-right p-2">وضعیت</th>
                                <th className="text-right p-2">شروع</th><th className="text-right p-2">پایان</th>
                                <th className="text-right p-2">مبلغ</th>
                              </tr></thead>
                              <tbody>
                                {(userTabData?.subscriptions || []).map((s: any, i: number) => (
                                  <tr key={i}>
                                    <td className="p-2 text-xs font-medium">{s.plan}</td>
                                    <td className="p-2"><span className={`badge ${s.status === 'active' ? 'badge-positive' : 'badge-accent'}`}>{s.status === 'active' ? 'فعال' : s.status}</span></td>
                                    <td className="p-2 text-xs">{new Date(s.starts_at).toLocaleDateString('fa-IR')}</td>
                                    <td className="p-2 text-xs">{s.ends_at ? new Date(s.ends_at).toLocaleDateString('fa-IR') : '—'}</td>
                                    <td className="p-2 text-xs">{faNum(s.price_paid)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────────
              Pricing
             ───────────────────────────────────────────────────────────── */}
          {page === 'pricing' && (
            <div className="space-y-6">
              <SectionHeader title="مدیریت تعرفه‌ها" subtitle="قیمت‌گذاری مدل‌ها به ازای هر میلیون توکن" />

              <div className="admin-card overflow-x-auto">
                <table className="admin-table w-full text-sm">
                  <thead>
                    <tr>
                      <th className="text-right p-3">مدل</th>
                      <th className="text-right p-3">ورودی</th>
                      <th className="text-right p-3">خروجی</th>
                      <th className="text-right p-3">واحد</th>
                      <th className="text-right p-3">وضعیت</th>
                      <th className="text-right p-3">تست</th>
                      <th className="text-right p-3">عملیات</th>
                    </tr>
                  </thead>
                  <tbody>
                    {prices.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="p-6 text-center text-sm text-muted">
                          تعرفه‌ای ثبت نشده
                        </td>
                      </tr>
                    ) : (
                      prices.map((p: any) => {
                        const testResult = testResults[p.model]
                        const isDisabled = p.availability === 'disabled'
                        return (
                          <tr key={p.model}>
                            <td className="p-3 text-sm font-mono font-medium text-primary">{p.model}</td>
                            <td className="p-3 text-xs">{faNum(p.input_per_million)}</td>
                            <td className="p-3 text-xs">{faNum(p.output_per_million)}</td>
                            <td className="p-3"><span className="badge">{p.currency}</span></td>
                            <td className="p-3">
                              <button
                                className={`badge ${isDisabled ? 'badge-danger' : 'badge-positive'}`}
                                style={{ cursor: 'pointer' }}
                                disabled={togglingModel === p.model}
                                onClick={() => toggleModel(p.model, p.availability)}
                                title="کلیک برای تغییر وضعیت"
                              >
                                {togglingModel === p.model ? '...' : (isDisabled ? 'غیرفعال' : 'فعال')}
                              </button>
                            </td>
                            <td className="p-3">
                              <button className="btn btn-sm" disabled={testingModel === p.model} onClick={() => testModel(p.model)}>
                                {testingModel === p.model ? (
                                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                                ) : 'تست'}
                              </button>
                              {testResult && (
                                <span className="text-xs mr-2" style={{ color: testResult.ok ? 'var(--success)' : 'var(--danger)' }}>
                                  {testResult.ok ? `${faNum(testResult.latency_ms)}ms` : (testResult.error || 'خطا')}
                                </span>
                              )}
                            </td>
                            <td className="p-3">
                              <button className="btn btn-sm" onClick={() => { setPzModel(p.model); setPzIn(String(p.input_per_million)); setPzOut(String(p.output_per_million)); setPzCur(p.currency) }}>
                                <Icon name="settings" size={14} />
                              </button>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>

              <div className="admin-card">
                <h3 className="font-semibold text-sm mb-4 text-primary">
                  {pzModel ? `ویرایش ${pzModel}` : 'افزودن تعرفه جدید'}
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <Field label="نام مدل">
                    <input className="input w-full" value={pzModel} onChange={(e) => setPzModel(e.target.value)} placeholder="gpt-4o" />
                  </Field>
                  <Field label="ورودی / میلیون توکن">
                    <input className="input w-full" type="number" value={pzIn} onChange={(e) => setPzIn(e.target.value)} placeholder="0" />
                  </Field>
                  <Field label="خروجی / میلیون توکن">
                    <input className="input w-full" type="number" value={pzOut} onChange={(e) => setPzOut(e.target.value)} placeholder="0" />
                  </Field>
                  <Field label="واحد پول">
                    <input className="input w-full" value={pzCur} onChange={(e) => setPzCur(e.target.value)} />
                  </Field>
                </div>
                <div className="flex gap-2 mt-4">
                  <button className="btn" onClick={savePricing}>
                    <Icon name="check" size={16} />
                    <span>ذخیره</span>
                  </button>
                  {pzModel && (
                    <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => { setPzModel(''); setPzIn(''); setPzOut(''); setPzCur('IRT') }}>
                      انصراف
                    </button>
                  )}
                </div>
              </div>

              {/* Token / Credit Packages — "N million tokens of <model> for <price>" bundles */}
              <SectionHeader title="بسته‌های اعتباری / توکن" subtitle="بسته‌هایی که در کیف پول کاربران قابل خریدند — با برچسب مدل، به‌صورت «N میلیون توکن مدل X» نمایش داده می‌شوند" />

              <div className="admin-card overflow-x-auto">
                <table className="admin-table w-full text-sm">
                  <thead>
                    <tr>
                      <th className="text-right p-3">شناسه</th>
                      <th className="text-right p-3">نام</th>
                      <th className="text-right p-3">مدل</th>
                      <th className="text-right p-3">مبلغ (تومان)</th>
                      <th className="text-right p-3">وضعیت</th>
                      <th className="text-right p-3">عملیات</th>
                    </tr>
                  </thead>
                  <tbody>
                    {creditPackages.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="p-6 text-center text-sm text-muted">
                          بسته‌ای ثبت نشده — از فرم پایین برای افزودن یک بسته استفاده کنید
                        </td>
                      </tr>
                    ) : (
                      creditPackages.map((pkg) => (
                        <tr key={pkg.id}>
                          <td className="p-3 text-sm font-mono text-primary">{pkg.id}</td>
                          <td className="p-3 text-sm">{pkg.name_fa}</td>
                          <td className="p-3 text-xs font-mono">{pkg.model_id || '—'}</td>
                          <td className="p-3 text-xs">{faNum(Math.round(pkg.base_amount / 10))}</td>
                          <td className="p-3">
                            <button
                              className={`badge ${pkg.active ? 'badge-positive' : 'badge-danger'}`}
                              style={{ cursor: 'pointer' }}
                              onClick={() => toggleCreditPackageActive(pkg)}
                            >
                              {pkg.active ? 'فعال' : 'غیرفعال'}
                            </button>
                          </td>
                          <td className="p-3">
                            <button
                              className="btn btn-sm"
                              onClick={() => {
                                setCpId(pkg.id); setCpNameFa(pkg.name_fa); setCpNameEn(pkg.name_en)
                                setCpBaseAmount(String(pkg.base_amount)); setCpTotalCredits(String(pkg.total_credits))
                                setCpBonusPercent(String(pkg.bonus_percent)); setCpModelId(pkg.model_id || '')
                              }}
                            >
                              <Icon name="settings" size={14} />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              <div className="admin-card">
                <h3 className="font-semibold text-sm mb-4 text-primary">
                  {cpId ? `ویرایش بسته ${cpId}` : 'افزودن بسته جدید'}
                </h3>
                <p className="text-xs text-muted mb-4">
                  «مبلغ پرداختی» همان چیزی است که واقعاً از کاربر گرفته می‌شود؛ «اعتبار دریافتی» چیزی است که به کیف پول اضافه می‌شود — اگر اعتبار دریافتی بیشتر از مبلغ پرداختی باشد، تفاوت همان بونوس واقعی است. هر دو به ریال هستند. مدل انتخابی صرفاً برچسب است؛ اعتبار در کیف پول عمومی کاربر شارژ می‌شود و طبق قیمت زنده هر مدل مصرف می‌شود.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <Field label="شناسه بسته (یکتا)">
                    <input className="input w-full" value={cpId} onChange={(e) => setCpId(e.target.value)} placeholder="pkg_mimo_20m" disabled={!!cpId && creditPackages.some((p) => p.id === cpId)} />
                  </Field>
                  <Field label="نام فارسی">
                    <input className="input w-full" value={cpNameFa} onChange={(e) => setCpNameFa(e.target.value)} placeholder="۲۰ میلیون توکن mimo" />
                  </Field>
                  <Field label="نام انگلیسی">
                    <input className="input w-full" value={cpNameEn} onChange={(e) => setCpNameEn(e.target.value)} placeholder="20M mimo tokens" />
                  </Field>
                  <Field label="مدل مرتبط (اختیاری)">
                    <select className="input w-full" value={cpModelId} onChange={(e) => setCpModelId(e.target.value)} style={{ appearance: 'auto' }}>
                      <option value="">— بدون مدل (اعتبار عمومی) —</option>
                      {models.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="مبلغ پرداختی (ریال)">
                    <input className="input w-full" type="number" value={cpBaseAmount} onChange={(e) => setCpBaseAmount(e.target.value)} placeholder="200000" />
                  </Field>
                  <Field label="اعتبار دریافتی (ریال)">
                    <input className="input w-full" type="number" value={cpTotalCredits} onChange={(e) => setCpTotalCredits(e.target.value)} placeholder="200000" />
                  </Field>
                </div>
                <div className="flex gap-2 mt-4">
                  <button className="btn" onClick={saveCreditPackage} disabled={cpSaving}>
                    {cpSaving ? (
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                    ) : (<><Icon name="check" size={16} /><span>ذخیره</span></>)}
                  </button>
                  {cpId && (
                    <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => { setCpId(''); setCpNameFa(''); setCpNameEn(''); setCpBaseAmount(''); setCpTotalCredits(''); setCpBonusPercent('0'); setCpModelId('') }}>
                      انصراف
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────────
              Features
             ───────────────────────────────────────────────────────────── */}
          {page === 'features' && (
            <div className="space-y-6">
              <SectionHeader title="امکانات و ویژگی‌ها" subtitle={`${faNum(features.length)} ویژگی ثبت شده`} />

              <div className="space-y-2">
                {features.length === 0 && (
                  <div className="admin-card text-center py-8 text-muted">
                    ویژگی‌ای ثبت نشده
                  </div>
                )}
                {features.map((f) => (
                  <div key={f.id} className="admin-card flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm" style={{ background: 'var(--bg-elevated)' }}>
                        {f.icon || '—'}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-primary">{f.title}</p>
                        <p className="text-xs text-muted">{f.description || 'بدون توضیح'}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={f.active ? 'badge badge-positive' : 'badge badge-warning'}>
                        {f.active ? 'فعال' : 'غیرفعال'}
                      </span>
                      <span className="badge text-[10px]">#{f.order_idx}</span>
                      <button className="btn btn-sm" onClick={() => editFeature(f)}>
                        <Icon name="settings" size={14} />
                      </button>
                      <button className="btn btn-sm btn-danger" onClick={() => delFeature(f.id)}>
                        <Icon name="close" size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="admin-card">
                <h3 className="font-semibold text-sm mb-4 text-primary">
                  {ftId ? 'ویرایش ویژگی' : 'افزودن ویژگی جدید'}
                </h3>
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Field label="عنوان">
                      <input className="input w-full" value={ftTitle} onChange={(e) => setFtTitle(e.target.value)} placeholder="چت هوشمند" />
                    </Field>
                    <Field label="آیکون">
                      <input className="input w-full" value={ftIcon} onChange={(e) => setFtIcon(e.target.value)} placeholder="icon-name" />
                    </Field>
                  </div>
                  <Field label="توضیحات">
                    <textarea className="input w-full min-h-[80px] resize-y" value={ftDesc} onChange={(e) => setFtDesc(e.target.value)} />
                  </Field>
                  <div className="grid grid-cols-2 gap-4">
                    <Field label="ترتیب نمایش">
                      <input className="input w-full" type="number" value={ftOrder} onChange={(e) => setFtOrder(e.target.value)} />
                    </Field>
                    <Field label="وضعیت">
                      <select className="input w-full" value={String(ftActive)} onChange={(e) => setFtActive(e.target.value === 'true')}>
                        <option value="true">فعال</option>
                        <option value="false">غیرفعال</option>
                      </select>
                    </Field>
                  </div>
                </div>
                <div className="flex gap-2 mt-4">
                  <button className="btn" onClick={saveFeature}>
                    <Icon name="check" size={16} />
                    <span>{ftId ? 'بروزرسانی' : 'افزودن'}</span>
                  </button>
                  {ftId && (
                    <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={resetFeatureForm}>
                      انصراف
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────────
              Discounts
             ───────────────────────────────────────────────────────────── */}
          {page === 'discounts' && (
            <div className="space-y-6">
              <SectionHeader title="کدهای تخفیف" subtitle={`${faNum(discounts.length)} کد تخفیف فعال`} />

              <div className="space-y-2">
                {discounts.length === 0 && (
                  <div className="admin-card text-center py-8 text-muted">
                    کد تخفیفی ثبت نشده
                  </div>
                )}
                {discounts.map((d) => (
                  <div key={d.id} className="admin-card flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="px-3 py-1.5 rounded-lg font-mono text-sm font-bold" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
                        {d.code}
                      </div>
                      <span className="text-sm text-primary">{d.percent}%</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={d.active ? 'badge badge-positive' : 'badge badge-warning'}>
                        {d.active ? 'فعال' : 'غیرفعال'}
                      </span>
                      <button className="btn btn-sm" onClick={() => editDiscount(d)}>
                        <Icon name="settings" size={14} />
                      </button>
                      <button className="btn btn-sm btn-danger" onClick={() => delDiscount(d.id)}>
                        <Icon name="close" size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="admin-card">
                <h3 className="font-semibold text-sm mb-4 text-primary">
                  {dcId ? 'ویرایش کد تخفیف' : 'افزودن کد تخفیف'}
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <Field label="کد تخفیف">
                    <input className="input w-full" value={dcCode} onChange={(e) => setDcCode(e.target.value)} placeholder="WELCOME10" />
                  </Field>
                  <Field label="درصد تخفیف">
                    <input className="input w-full" type="number" value={dcPercent} onChange={(e) => setDcPercent(e.target.value)} />
                  </Field>
                  <Field label="وضعیت">
                    <select className="input w-full" value={String(dcActive)} onChange={(e) => setDcActive(e.target.value === 'true')}>
                      <option value="true">فعال</option>
                      <option value="false">غیرفعال</option>
                    </select>
                  </Field>
                </div>
                <div className="flex gap-2 mt-4">
                  <button className="btn" onClick={saveDiscount}>
                    <Icon name="check" size={16} />
                    <span>{dcId ? 'بروزرسانی' : 'افزودن'}</span>
                  </button>
                  {dcId && (
                    <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={resetDiscountForm}>
                      انصراف
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────────
              About
             ───────────────────────────────────────────────────────────── */}
          {page === 'about' && (
            <div className="space-y-6">
              <SectionHeader title="درباره ما" subtitle="محتوای صفحه درباره ما" />

              <div className="admin-card">
                <div className="space-y-4">
                  <Field label="عنوان">
                    <input className="input w-full" value={abTitle} onChange={(e) => setAbTitle(e.target.value)} placeholder="درباره Sanjhubai" />
                  </Field>
                  <Field label="متن">
                    <textarea
                      className="input w-full min-h-[200px] resize-y leading-relaxed"
                      value={abBody}
                      onChange={(e) => setAbBody(e.target.value)}
                      placeholder="متن درباره ما به فارسی..."
                    />
                  </Field>
                </div>
                <button className="btn mt-4" onClick={saveAbout}>
                  <Icon name="check" size={16} />
                  <span>ذخیره</span>
                </button>
              </div>
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────────
              Proxy
             ───────────────────────────────────────────────────────────── */}
          {page === 'proxy' && (
            <div className="space-y-6">
              <SectionHeader title="تنظیمات پروکسی" subtitle="مدیریت تونل و پروکسی اتصال" />

              <div className="admin-card">
                <div className="flex items-center gap-3 mb-4 p-3 rounded-lg" style={{ background: proxyConfig.active ? 'var(--positive)' + '15' : 'var(--warning)' + '15' }}>
                  <Icon name={proxyConfig.active ? 'check' : 'notification'} size={18} style={{ color: proxyConfig.active ? 'var(--positive)' : 'var(--warning)' }} />
                  <span className="text-sm font-medium" style={{ color: proxyConfig.active ? 'var(--positive)' : 'var(--warning)' }}>
                    {proxyConfig.active ? 'تونل فعال است' : 'تونل غیرفعال است'}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <Field label="نوع پروکسی">
                    <select className="input w-full" value={pxType} onChange={(e) => setPxType(e.target.value)}>
                      <option value="socks5">SOCKS5</option>
                      <option value="http">HTTP</option>
                    </select>
                  </Field>
                  <Field label="آدرس پروکسی">
                    <input className="input w-full" value={pxUrl} onChange={(e) => setPxUrl(e.target.value)} placeholder="socks5://user:pass@host:port" />
                  </Field>
                  <Field label="وضعیت">
                    <select className="input w-full" value={String(pxActive)} onChange={(e) => setPxActive(e.target.value === 'true')}>
                      <option value="true">فعال</option>
                      <option value="false">غیرفعال</option>
                    </select>
                  </Field>
                </div>
                <button className="btn mt-4" onClick={saveProxy}>
                  <Icon name="check" size={16} />
                  <span>ذخیره و اعمال</span>
                </button>
              </div>
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────────
              Models
             ───────────────────────────────────────────────────────────── */}
          {page === 'models' && (
            <div className="space-y-6">
              <SectionHeader title="مدل‌های فعال" subtitle={`${faNum(models.length)} مدل در دسترس`} />

              {/* Org Default Model */}
              <div className="admin-card">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--accent-dim)' }}>
                    <Icon name="models" size={16} className="text-accent" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-primary">مدل پیشفرض سازمان</h3>
                    <p className="text-xs text-muted">مدلی که کاربران جدید به‌صورت پیشفرض استفاده می‌کنند</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <select
                    className="input flex-1"
                    value={orgDefaultModel}
                    onChange={(e) => setOrgDefaultModel(e.target.value)}
                  >
                    <option value="">بدون مدل پیشفرض (اولین مدل لیست)</option>
                    {models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <button className="btn" onClick={saveOrgDefaultModel} disabled={orgDefaultSaving}>
                    {orgDefaultSaving ? (
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                    ) : 'ذخیره'}
                  </button>
                </div>
              </div>

              {models.length === 0 ? (
                <div className="admin-card text-center py-12">
                  <Icon name="models" size={40} style={{ color: 'var(--text-muted)', margin: '0 auto 12px' }} />
                  <p className="text-muted">مدلی بارگذاری نشده</p>
                  <p className="text-xs mt-1 text-muted">پروکسی را بررسی کنید</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {models.map((m) => (
                    <div key={m} className="admin-card flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--accent-dim)' }}>
                        <Icon name="models" size={16} className="text-accent" />
                      </div>
                      <span className="text-sm font-mono text-primary">{m}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────────
              داشبورد امنیت
             ───────────────────────────────────────────────────────────── */}
          {page === 'security' && (
            <div className="space-y-6">
              <SectionHeader
                title="مرکز عملیات امنیتی (SOC)"
                subtitle="نظارت بر تهدیدات، رویدادها و فعالیت کاربران"
              />

              {/* ─── Threat Level + Stats Row ──────────────────────────── */}
              {securityStats ? (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                    {/* Threat Level Card */}
                    <div
                      className="admin-card"
                      style={{
                        borderRight: `3px solid ${THREAT_LEVEL_COLOR[securityStats.threat_level]}`,
                      }}
                    >
                      <div className="flex items-center gap-3 mb-3">
                        <div
                          className="p-2 rounded-lg"
                          style={{
                            background: `color-mix(in srgb, ${THREAT_LEVEL_COLOR[securityStats.threat_level]} 15%, transparent)`,
                          }}
                        >
                          <Icon
                            name="warning"
                            size={18}
                            style={{ color: THREAT_LEVEL_COLOR[securityStats.threat_level] }}
                          />
                        </div>
                        <span className="text-xs text-muted">سطح تهدید</span>
                      </div>
                      <p
                        className="text-xl font-bold"
                        style={{ color: THREAT_LEVEL_COLOR[securityStats.threat_level] }}
                      >
                        {{ low: 'پایین', medium: 'متوسط', high: 'بالا', critical: 'بحرانی' }[securityStats.threat_level]}
                      </p>
                    </div>

                    <StatCard
                      icon="lock"
                      label="ورودهای ناموفق (۲۴ ساعت)"
                      value={faNum(securityStats.failed_logins_24h)}
                      color="var(--danger)"
                    />
                    <StatCard
                      icon="user"
                      label="نشستهای فعال"
                      value={faNum(securityStats.active_sessions)}
                      color="var(--info)"
                    />
                    <StatCard
                      icon="security"
                      label="کاربران مسدود شده"
                      value={faNum(securityStats.banned_users?.length, { fallback: '۰' })}
                      color="var(--warning)"
                    />
                  </div>

                  {/* ─── Failed Login Chart (sparkline-style bars) ──────── */}
                  <div className="admin-card">
                    <div className="flex items-center gap-2 mb-4">
                      <Icon name="chart" size={18} className="text-secondary" />
                      <h3 className="font-semibold text-sm text-primary">
                        نمودار ورودهای ناموفق (۲۴ ساعت اخیر)
                      </h3>
                    </div>
                    <div className="flex items-end gap-1 h-24">
                      {(securityStats.failed_login_chart || []).slice(-24).map((bar, i) => {
                        const maxCount = Math.max(...(securityStats.failed_login_chart || []).map((b) => b.count), 1)
                        const heightPct = (bar.count / maxCount) * 100
                        return (
                          <div key={i} className="flex-1 flex flex-col items-center gap-1">
                            <div
                              className="w-full rounded-t transition-all duration-300"
                              style={{
                                height: `${Math.max(heightPct, 4)}%`,
                                background: bar.count > maxCount * 0.7
                                  ? 'var(--danger)'
                                  : bar.count > maxCount * 0.3
                                    ? 'var(--warning)'
                                    : 'var(--accent)',
                                opacity: 0.8,
                              }}
                              title={`${bar.hour}: ${bar.count} تلاش ناموفق`}
                            />
                          </div>
                        )
                      })}
                    </div>
                    <div className="flex justify-between mt-2">
                      <span className="text-[10px] text-muted">
                        {securityStats.failed_login_chart?.[0]?.hour || ''}
                      </span>
                      <span className="text-[10px] text-muted">
                        {securityStats.failed_login_chart?.[securityStats.failed_login_chart.length - 1]?.hour || ''}
                      </span>
                    </div>
                  </div>

                  {/* ─── Banned Users ──────────────────────────────────── */}
                  <div className="admin-card">
                    <div className="flex items-center gap-2 mb-4">
                      <Icon name="security" size={18} className="text-warning" />
                      <h3 className="font-semibold text-sm text-primary">
                        کاربران مسدود شده
                      </h3>
                      <span className="badge badge-warning mr-auto">{securityStats.banned_users?.length || 0}</span>
                    </div>
                    {(securityStats.banned_users || []).length === 0 ? (
                      <div className="text-center py-6 text-sm text-muted">
                        کاربر مسدود شده‌ای وجود ندارد
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="admin-table w-full text-sm">
                          <thead>
                            <tr>
                              <th className="text-right p-3">شناسه</th>
                              <th className="text-right p-3">نام کاربری</th>
                              <th className="text-right p-3">ایمیل</th>
                              <th className="text-right p-3">تاریخ مسدودیت</th>
                              <th className="text-right p-3">عملیات</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(securityStats.banned_users || []).map((u) => (
                              <tr key={u.id}>
                                <td className="p-3 text-xs font-mono">{u.id}</td>
                                <td className="p-3 text-sm text-primary">{u.username || '—'}</td>
                                <td className="p-3 text-xs text-secondary">{u.email}</td>
                                <td className="p-3 text-xs text-muted">
                                  {u.banned_at ? new Date(u.banned_at).toLocaleDateString('fa-IR') : '—'}
                                </td>
                                <td className="p-3">
                                  <button
                                    className="btn btn-sm"
                                    style={{ background: 'var(--positive)', color: 'var(--text-on-accent)' }}
                                    onClick={() => unbanUser(u.id)}
                                  >
                                    رفع مسدودیت
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                /* Loading skeleton */
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="admin-card">
                      <div className="skeleton h-3 w-20 mb-3 rounded" />
                      <div className="skeleton h-7 w-16 rounded" />
                    </div>
                  ))}
                </div>
              )}

              {/* ─── Security Events Table ──────────────────────────── */}
              <div className="admin-card">
                <div className="flex items-center gap-2 mb-4">
                  <Icon name="notification" size={18} className="text-danger" />
                  <h3 className="font-semibold text-sm text-primary">
                    رویدادهای امنیتی اخیر
                  </h3>
                  {securityLoading && (
                    <span className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin inline-block" />
                  )}
                </div>
                <div className="overflow-x-auto">
                  <table className="admin-table w-full text-sm">
                    <thead>
                      <tr>
                        <th className="text-right p-3">نوع رویداد</th>
                        <th className="text-right p-3">کاربر</th>
                        <th className="text-right p-3">آدرس IP</th>
                        <th className="text-right p-3">جزئیات</th>
                        <th className="text-right p-3">زمان</th>
                      </tr>
                    </thead>
                    <tbody>
                      {securityEvents.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="p-6 text-center text-sm text-muted">
                            رویداد امنیتی ثبت نشده
                          </td>
                        </tr>
                      ) : (
                        securityEvents.map((ev) => (
                          <tr key={ev.id}>
                            <td className="p-3">
                              <span className={`badge ${
                                ev.event_type?.includes('failed') || ev.event_type?.includes('lockout')
                                  ? 'badge-danger'
                                  : ev.event_type?.includes('login') || ev.event_type?.includes('success')
                                    ? 'badge-positive'
                                    : 'badge-accent'
                              }`}>
                                {ev.event_type || 'نامشخص'}
                              </span>
                            </td>
                            <td className="p-3 text-xs text-secondary">
                              {ev.user_email || ev.user_id || '—'}
                            </td>
                            <td className="p-3 text-xs font-mono text-muted">
                              {ev.ip_address || '—'}
                            </td>
                            <td className="p-3 text-xs text-secondary">
                              {ev.details || '—'}
                            </td>
                            <td className="p-3 text-xs text-muted">
                              {toFaDigits(new Date(ev.created_at).toLocaleString('fa-IR'))}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* ─── Audit Log Table ─────────────────────────────────── */}
              <div className="admin-card">
                <div className="flex items-center gap-2 mb-4">
                  <Icon name="history" size={18} className="text-accent" />
                  <h3 className="font-semibold text-sm text-primary">
                    لاگ عملیات ادمین
                  </h3>
                </div>

                {/* Filter bar */}
                <div className="flex flex-wrap gap-2 mb-4">
                  {[
                    { label: 'همه', value: '' },
                    { label: 'ban', value: 'ban' },
                    { label: 'unban', value: 'unban' },
                    { label: 'edit_user', value: 'edit_user' },
                    { label: 'create', value: 'create' },
                    { label: 'delete', value: 'delete' },
                    { label: 'update', value: 'update' },
                  ].map((f) => (
                    <button
                      key={f.value}
                      className={`btn btn-sm ${auditActionFilter === f.value ? 'font-bold' : ''}`}
                      style={{
                        background: auditActionFilter === f.value ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                        color: auditActionFilter === f.value ? 'var(--accent)' : 'var(--text-secondary)',
                      }}
                      onClick={() => loadAuditWithFilter(f.value)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>

                <div className="overflow-x-auto">
                  <table className="admin-table w-full text-sm">
                    <thead>
                      <tr>
                        <th className="text-right p-3">شناسه</th>
                        <th className="text-right p-3">عملیات</th>
                        <th className="text-right p-3">نوع هدف</th>
                        <th className="text-right p-3">شناسه هدف</th>
                        <th className="text-right p-3">جزئیات</th>
                        <th className="text-right p-3">زمان</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLogs.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="p-6 text-center text-sm text-muted">
                            لاگ عملیاتی ثبت نشده
                          </td>
                        </tr>
                      ) : (
                        auditLogs.map((log) => (
                          <tr key={log.id}>
                            <td className="p-3 text-xs font-mono">{log.id}</td>
                            <td className="p-3">
                              <span className={`badge ${
                                log.action?.includes('ban') ? 'badge-danger'
                                : log.action?.includes('delete') ? 'badge-warning'
                                : log.action?.includes('create') ? 'badge-positive'
                                : 'badge-accent'
                              }`}>
                                {log.action || '—'}
                              </span>
                            </td>
                            <td className="p-3 text-xs text-secondary">
                              {log.target_type || '—'}
                            </td>
                            <td className="p-3 text-xs font-mono">
                              {log.target_id || '—'}
                            </td>
                            <td className="p-3 text-xs text-secondary">
                              {log.details || '—'}
                            </td>
                            <td className="p-3 text-xs text-muted">
                              {toFaDigits(new Date(log.created_at).toLocaleString('fa-IR'))}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {auditTotal > 50 && (
                  <div className="flex items-center justify-between mt-4 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
                    <span className="text-xs text-muted">
                      صفحه {auditPage} از {Math.ceil(auditTotal / 50)}
                    </span>
                    <div className="flex gap-2">
                      <button
                        className="btn btn-sm"
                        disabled={auditPage <= 1}
                        onClick={() => { setAuditPage(Math.max(1, auditPage - 1)); loadSecurityData() }}
                      >
                        قبلی
                      </button>
                      <button
                        className="btn btn-sm"
                        disabled={auditPage >= Math.ceil(auditTotal / 50)}
                        onClick={() => { setAuditPage(auditPage + 1); loadSecurityData() }}
                      >
                        بعدی
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
