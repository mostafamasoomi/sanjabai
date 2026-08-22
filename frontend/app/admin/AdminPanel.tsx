'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon, type IconName } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { toast } from '@/components/ui'
import dynamic from 'next/dynamic'
import { Field } from './sections/shared'
import DashboardSection from './sections/DashboardSection'
import UsersSection from './sections/UsersSection'
import PricingSection from './sections/PricingSection'
import FeaturesSection from './sections/FeaturesSection'
import DiscountsSection from './sections/DiscountsSection'
import AboutSection from './sections/AboutSection'
import ProxySection from './sections/ProxySection'
import ModelsSection from './sections/ModelsSection'
import SecuritySection from './sections/SecuritySection'

const MonitoringTab = dynamic(() => import('./components/MonitoringTab'), { ssr: false })
const MarkupSection = dynamic(() => import('./sections/MarkupSection'), { ssr: false })
const ExchangeRateSection = dynamic(() => import('./sections/ExchangeRateSection'), { ssr: false })
const ImagePricingSection = dynamic(() => import('./sections/ImagePricingSection'), { ssr: false })
const PackagesSection = dynamic(() => import('./sections/PackagesSection'), { ssr: false })
const AnalyticsSection = dynamic(() => import('./sections/AnalyticsSection'), { ssr: false })
const ModelOpsSection = dynamic(() => import('./sections/ModelOpsSection'), { ssr: false })
const PlansSection = dynamic(() => import('./sections/PlansSection'), { ssr: false })
const SiteControlSection = dynamic(() => import('./sections/SiteControlSection'), { ssr: false })

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjabai Admin Panel — Aurora Design System
   RTL Persian, dark theme, Stripe/Linear inspired
   ═══════════════════════════════════════════════════════════════════════════ */

// ─── Types ───────────────────────────────────────────────────────────────────

type Page = 'dashboard' | 'analytics' | 'site-control' | 'pricing' | 'markup' | 'exchange-rate' | 'image-pricing' | 'packages' | 'plans' | 'features' | 'discounts' | 'about' | 'proxy' | 'models' | 'model-ops' | 'users' | 'security' | 'monitoring'

export interface Analytics {
  user_count: number
  active_users: number
  total_revenue: number
  total_tokens: number
  conv_count: number
  recent_ledger: { id: number; user_id: number; amount: number; reason: string; created_at: string }[]
}

export interface PricingRow {
  model: string
  input_per_million: number
  output_per_million: number
  currency: string
  availability?: string
}

export interface ModelTestResult {
  ok: boolean
  latency_ms: number
  error: string | null
  upstream?: string
}

export interface CreditPackageRow {
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

export interface FeatureRow {
  id: number
  title: string
  description: string
  icon: string
  order_idx: number
  active: boolean
}

export interface DiscountRow {
  id: number
  code: string
  percent: number
  active: boolean
}

export interface ProxyConfig {
  proxy_type: string
  proxy_url: string
  active: boolean
}

export interface SecurityStats {
  threat_level: 'low' | 'medium' | 'high' | 'critical'
  failed_logins_24h: number
  active_sessions: number
  failed_login_chart: { hour: string; count: number }[]
  banned_users: { id: number; email: string; username: string; banned_at: string }[]
}

export interface SecurityEvent {
  id: number
  event_type: string
  user_id: number | null
  user_email: string | null
  ip_address: string | null
  details: string | null
  created_at: string
}

export interface AuditLog {
  id: number
  admin_id: number
  action: string
  target_type: string | null
  target_id: number | null
  details: string | null
  created_at: string
}

// Mirrors exactly what GET /admin/users returns, verified against the live
// endpoint rather than assumed.
//
// This type previously declared `username`, `is_active`, `plan` and
// `wallet_balance` -- four fields the server has never sent. TypeScript was
// satisfied because the rows arrive as untyped JSON and get asserted into
// this shape, so the mismatch could not surface at compile time; those
// columns simply rendered blank in production, and the status badge read
// "inactive" for every user because `is_active` was always undefined.
//
// There is no `role` column on `users` either -- the only role signal is
// `preferences.panel` (consumer/developer), which the user detail drawer
// reads. And there is no editable `plan` on a user row; a plan is expressed
// through the `subscriptions` table, not a column here.
//
// `balance` is the authoritative wallet balance; `ledger_sum` is the same
// figure reconstructed from the append-only ledger. They must be equal --
// a divergence is a billing-integrity bug, which is why both are shown.
export interface UserRow {
  id: number
  email: string
  phone: string | null
  telegram_id: number | null
  referral_code: string | null
  referred_by: number | null
  created_at: string
  banned: boolean
  balance: number
  reserved: number
  ledger_sum: number
  used_today: number
}

export interface UserDetail {
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

export type UserDetailTab = 'overview' | 'conversations' | 'usage' | 'ledger' | 'payments'

// ─── Sidebar Navigation ──────────────────────────────────────────────────────

const NAV_ITEMS: { key: Page; label: string; icon: IconName }[] = [
  { key: 'dashboard', label: 'داشبورد', icon: 'dashboard' },
  { key: 'analytics', label: 'تحلیل و درآمد', icon: 'chart' },
  { key: 'site-control', label: 'کنترل سایت', icon: 'settings' },
  { key: 'users', label: 'کاربران', icon: 'profile' },
  { key: 'pricing', label: 'تعرفه‌ها', icon: 'pricing' },
  { key: 'markup', label: 'درصد سود', icon: 'chart' },
  { key: 'exchange-rate', label: 'نرخ ارز', icon: 'globe' },
  { key: 'image-pricing', label: 'قیمت‌گذاری تصویر', icon: 'camera' },
  { key: 'packages', label: 'بسته‌ها', icon: 'wallet' },
  { key: 'plans', label: 'پلن و اشتراک', icon: 'wallet' },
  { key: 'features', label: 'امکانات', icon: 'models' },
  { key: 'discounts', label: 'تخفیف‌ها', icon: 'wallet' },
  { key: 'about', label: 'درباره ما', icon: 'notification' },
  { key: 'proxy', label: 'پروکسی', icon: 'security' },
  { key: 'models', label: 'مدل‌ها', icon: 'code' },
  { key: 'model-ops', label: 'عملیات کاتالوگ', icon: 'code' },
  { key: 'security', label: 'امنیت', icon: 'lock' },
  { key: 'monitoring', label: 'پایش', icon: 'chart' },
]

// ─── API Helper ──────────────────────────────────────────────────────────────

let TOKEN = ''

export async function api(path: string, opts: RequestInit = {}) {
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
            <p className="text-sm mt-1 text-muted">داشبورد مدیریت Sanjabai</p>
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
            border-l overflow-y-auto transition-transform duration-200
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
                <h2 className="text-sm font-bold text-primary">Sanjabai</h2>
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
          <div className="flex items-center justify-between mb-6">
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
          {page === 'dashboard' && <DashboardSection analytics={analytics} />}

          {page === 'users' && (
            <UsersSection
              users={users}
              userSearch={userSearch}
              setUserSearch={setUserSearch}
              editingUser={editingUser}
              setEditingUser={setEditingUser}
              selectedUserId={selectedUserId}
              setSelectedUserId={setSelectedUserId}
              userDetail={userDetail}
              setUserDetail={setUserDetail}
              userDetailTab={userDetailTab}
              userTabData={userTabData}
              setUserTabData={setUserTabData}
              loadingDetail={loadingDetail}
              openUserDetail={openUserDetail}
              loadUserTab={loadUserTab}
              banUser={banUser}
              saveUserEdit={saveUserEdit}
            />
          )}

          {/* ─────────────────────────────────────────────────────────────
              Pricing
             ───────────────────────────────────────────────────────────── */}
          {page === 'pricing' && (
            <PricingSection
              prices={prices}
              testResults={testResults}
              togglingModel={togglingModel}
              testingModel={testingModel}
              toggleModel={toggleModel}
              testModel={testModel}
              pzModel={pzModel}
              setPzModel={setPzModel}
              pzIn={pzIn}
              setPzIn={setPzIn}
              pzOut={pzOut}
              setPzOut={setPzOut}
              pzCur={pzCur}
              setPzCur={setPzCur}
              savePricing={savePricing}
              creditPackages={creditPackages}
              models={models}
              cpId={cpId}
              setCpId={setCpId}
              cpNameFa={cpNameFa}
              setCpNameFa={setCpNameFa}
              cpNameEn={cpNameEn}
              setCpNameEn={setCpNameEn}
              cpBaseAmount={cpBaseAmount}
              setCpBaseAmount={setCpBaseAmount}
              cpTotalCredits={cpTotalCredits}
              setCpTotalCredits={setCpTotalCredits}
              cpBonusPercent={cpBonusPercent}
              setCpBonusPercent={setCpBonusPercent}
              cpModelId={cpModelId}
              setCpModelId={setCpModelId}
              cpSaving={cpSaving}
              saveCreditPackage={saveCreditPackage}
              toggleCreditPackageActive={toggleCreditPackageActive}
            />
          )}

          {/* ─────────────────────────────────────────────────────────────
              Features
             ───────────────────────────────────────────────────────────── */}
          {page === 'features' && (
            <FeaturesSection
              features={features}
              ftId={ftId}
              ftTitle={ftTitle}
              setFtTitle={setFtTitle}
              ftDesc={ftDesc}
              setFtDesc={setFtDesc}
              ftIcon={ftIcon}
              setFtIcon={setFtIcon}
              ftOrder={ftOrder}
              setFtOrder={setFtOrder}
              ftActive={ftActive}
              setFtActive={setFtActive}
              saveFeature={saveFeature}
              editFeature={editFeature}
              delFeature={delFeature}
              resetFeatureForm={resetFeatureForm}
            />
          )}

          {/* ─────────────────────────────────────────────────────────────
              Discounts
             ───────────────────────────────────────────────────────────── */}
          {page === 'discounts' && (
            <DiscountsSection
              discounts={discounts}
              dcId={dcId}
              dcCode={dcCode}
              setDcCode={setDcCode}
              dcPercent={dcPercent}
              setDcPercent={setDcPercent}
              dcActive={dcActive}
              setDcActive={setDcActive}
              saveDiscount={saveDiscount}
              editDiscount={editDiscount}
              delDiscount={delDiscount}
              resetDiscountForm={resetDiscountForm}
            />
          )}

          {/* ─────────────────────────────────────────────────────────────
              About
             ───────────────────────────────────────────────────────────── */}
          {page === 'about' && (
            <AboutSection abTitle={abTitle} setAbTitle={setAbTitle} abBody={abBody} setAbBody={setAbBody} saveAbout={saveAbout} />
          )}

          {/* ─────────────────────────────────────────────────────────────
              Proxy
             ───────────────────────────────────────────────────────────── */}
          {page === 'proxy' && (
            <ProxySection
              proxyConfig={proxyConfig}
              pxType={pxType}
              setPxType={setPxType}
              pxUrl={pxUrl}
              setPxUrl={setPxUrl}
              pxActive={pxActive}
              setPxActive={setPxActive}
              saveProxy={saveProxy}
            />
          )}

          {/* ─────────────────────────────────────────────────────────────
              Models
             ───────────────────────────────────────────────────────────── */}
          {page === 'models' && (
            <ModelsSection
              models={models}
              orgDefaultModel={orgDefaultModel}
              setOrgDefaultModel={setOrgDefaultModel}
              orgDefaultSaving={orgDefaultSaving}
              saveOrgDefaultModel={saveOrgDefaultModel}
              api={api}
            />
          )}

          {/* ─────────────────────────────────────────────────────────────
              داشبورد امنیت
             ───────────────────────────────────────────────────────────── */}
          {page === 'security' && (
            <SecuritySection
              securityStats={securityStats}
              securityEvents={securityEvents}
              auditLogs={auditLogs}
              auditPage={auditPage}
              setAuditPage={setAuditPage}
              auditTotal={auditTotal}
              auditActionFilter={auditActionFilter}
              securityLoading={securityLoading}
              unbanUser={unbanUser}
              loadAuditWithFilter={loadAuditWithFilter}
              loadSecurityData={loadSecurityData}
            />
          )}
          {page === 'markup' && <MarkupSection api={api} />}
          {page === 'exchange-rate' && <ExchangeRateSection api={api} />}
          {page === 'image-pricing' && <ImagePricingSection api={api} />}
          {page === 'packages' && <PackagesSection api={api} />}
          {page === 'analytics' && <AnalyticsSection api={api} />}
          {page === 'site-control' && <SiteControlSection api={api} />}
          {page === 'plans' && <PlansSection api={api} />}
          {page === 'model-ops' && <ModelOpsSection api={api} />}
          {page === 'monitoring' && <MonitoringTab api={api} />}
        </main>
      </div>
    </div>
  )
}
