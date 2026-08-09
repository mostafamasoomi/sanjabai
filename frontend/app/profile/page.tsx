'use client'

import { useState, useEffect, useRef } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { faNum, faPrice } from '@/lib/format'

const AUTONOMY_LEVELS = [
  {
    value: 'low',
    label_fa: 'پایین — تأیید قبل از هر عمل',
    label_en: 'Low — Confirm before actions',
    desc_fa: 'هوش مصنوعی قبل از انجام هر عملیاتی از شما تأیید می‌گیرد. مناسب برای کاربرانی که کنترل کامل می‌خواهند.',
    desc_en: 'AI asks for your confirmation before performing any action. Suitable for users who want full control.',
    icon: 'lock',
  },
  {
    value: 'medium',
    label_fa: 'متوسط — اجرای خودکار وظایف رایج',
    label_en: 'Medium — Auto-execute common tasks',
    desc_fa: 'وظایف رایج و امن به صورت خودکار اجرا می‌شوند. اعمال حساس همچنان نیاز به تأیید دارند.',
    desc_en: 'Common and safe tasks execute automatically. Sensitive actions still require confirmation.',
    icon: 'settings',
  },
  {
    value: 'high',
    label_fa: 'بالا — خودمختاری کامل با محدودیت‌های امنیتی',
    label_en: 'High — Full autonomy with safety limits',
    desc_fa: 'هوش مصنوعی با بیشترین آزادی عمل می‌کند. فقط اعمال غیرقابل‌برگشت نیاز به تأیید دارند.',
    desc_en: 'AI operates with maximum freedom. Only irreversible actions require confirmation.',
    icon: 'rocket',
  },
]

const TIMEZONES = [
  { value: 'Asia/Tehran', label: 'تهران (IRST)' },
  { value: 'Asia/Dubai', label: 'دوبی (GST)' },
  { value: 'Europe/London', label: 'لندن (GMT)' },
  { value: 'America/New_York', label: 'نیویورک (EST)' },
  { value: 'Asia/Tokyo', label: 'توکیو (JST)' },
  { value: 'UTC', label: 'UTC' },
]

export default function ProfilePage() {
  const { user, token } = useAuth()

  // Profile fields
  const [displayName, setDisplayName] = useState('')
  const [bio, setBio] = useState('')
  const [avatarUrl, setAvatarUrl] = useState('')
  const [timezone, setTimezone] = useState('Asia/Tehran')
  const [language, setLanguage] = useState('fa')

  // Preferences
  const [defaultModel, setDefaultModel] = useState('')
  const [aiPersonality, setAiPersonality] = useState('')
  const [pinnedContext, setPinnedContext] = useState('')
  const [autonomyLevel, setAutonomyLevel] = useState('medium')
  const [theme, setTheme] = useState('dark')
  const [emailNotif, setEmailNotif] = useState(true)
  const [telegramNotif, setTelegramNotif] = useState(false)

  // Available models
  const [models, setModels] = useState<string[]>([])

  // Change password
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)

  // Telegram link
  const [telegramId, setTelegramId] = useState('')
  const [linkingTelegram, setLinkingTelegram] = useState(false)

  // Usage stats
  const [usage, setUsage] = useState<any>(null)
  const [balance, setBalance] = useState<number | null>(null)

  // Loading/saving states
  const [loadingProfile, setLoadingProfile] = useState(true)
  const [saving, setSaving] = useState(false)
  const [avatarUploading, setAvatarUploading] = useState(false)

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null)
  const mdFileInputRef = useRef<HTMLInputElement>(null)

  // Track original values for dirty checking
  const [originalValues, setOriginalValues] = useState<any>({})

  useEffect(() => {
    if (user) {
      fetchProfile()
      fetchUsage()
      fetchBalance()
      fetchModels()
    }
  }, [user])

  const fetchProfile = async () => {
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/auth/profile', {
        headers: { Authorization: `Bearer ${t}` },
      })
      if (r.ok) {
        const data = await r.json()
        setDisplayName(data.display_name || '')
        setBio(data.bio || '')
        setAvatarUrl(data.avatar_url || '')
        setTimezone(data.timezone || 'Asia/Tehran')
        setLanguage(data.language || 'fa')
        const prefs = data.preferences || {}
        setDefaultModel(prefs.default_model || '')
        setAiPersonality(prefs.ai_personality || '')
        setPinnedContext(prefs.pinned_context || '')
        setAutonomyLevel(prefs.autonomy_level || 'medium')
        setTheme(prefs.theme || 'dark')
        setEmailNotif(prefs.notification_settings?.email !== false)
        setTelegramNotif(prefs.notification_settings?.telegram === true)
        setOriginalValues({
          display_name: data.display_name || '',
          bio: data.bio || '',
          timezone: data.timezone || 'Asia/Tehran',
          language: data.language || 'fa',
          default_model: prefs.default_model || '',
          ai_personality: prefs.ai_personality || '',
          pinned_context: prefs.pinned_context || '',
          autonomy_level: prefs.autonomy_level || 'medium',
          theme: prefs.theme || 'dark',
          email_notif: prefs.notification_settings?.email !== false,
          telegram_notif: prefs.notification_settings?.telegram === true,
        })
      }
    } catch {} finally {
      setLoadingProfile(false)
    }
  }

  const fetchModels = async () => {
    try {
      const r = await fetch('/api/models')
      if (r.ok) {
        const data = await r.json()
        setModels((data.data || []).map((m: { id: string }) => m.id))
      }
    } catch {}
  }

  const fetchUsage = async () => {
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/me/usage', { headers: { Authorization: `Bearer ${t}` } })
      if (r.ok) setUsage(await r.json())
    } catch {}
  }

  const fetchBalance = async () => {
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/wallet', { headers: { Authorization: `Bearer ${t}` } })
      if (r.ok) setBalance((await r.json()).balance)
    } catch {}
  }

  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/auth/profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${t}`,
        },
        body: JSON.stringify({
          display_name: displayName,
          bio,
          timezone,
          language,
          preferences: {
            default_model: defaultModel,
            ai_personality: aiPersonality,
            pinned_context: pinnedContext,
            autonomy_level: autonomyLevel,
            theme,
            notification_settings: {
              email: emailNotif,
              telegram: telegramNotif,
            },
          },
        }),
      })
      const data = await r.json()
      if (r.ok) {
        toast(language === 'fa' ? 'پروفایل با موفقیت ذخیره شد' : 'Profile saved successfully', 'success')
        // Sync theme with document
        if (theme === 'dark') {
          document.documentElement.classList.add('dark')
        } else {
          document.documentElement.classList.remove('dark')
        }
        // Update localStorage for backward compat
        localStorage.setItem('pref_dark_mode', String(theme === 'dark'))
        localStorage.setItem('pref_email_notif', String(emailNotif))
        localStorage.setItem('pref_telegram_notif', String(telegramNotif))
        // Update original values
        setOriginalValues({
          display_name: displayName, bio, timezone, language,
          default_model: defaultModel, ai_personality: aiPersonality,
          pinned_context: pinnedContext,
          autonomy_level: autonomyLevel, theme,
          email_notif: emailNotif, telegram_notif: telegramNotif,
        })
      } else {
        toast(data.detail || (language === 'fa' ? 'خطا در ذخیره پروفایل' : 'Error saving profile'), 'error')
      }
    } catch {
      toast(language === 'fa' ? 'خطا در ارتباط با سرور' : 'Server connection error', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handlePinnedContextFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (file.size > 1024 * 1024) {
      toast(language === 'fa' ? 'حجم فایل نباید بیشتر از ۱ مگابایت باشد' : 'File must be under 1MB', 'error')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const text = String(reader.result || '').slice(0, 20000)
      setPinnedContext(text)
      toast(language === 'fa' ? 'فایل بارگذاری شد — برای ذخیره، «ذخیره تغییرات» را بزنید' : 'File loaded — click Save to apply', 'success')
    }
    reader.onerror = () => {
      toast(language === 'fa' ? 'خطا در خواندن فایل' : 'Error reading file', 'error')
    }
    reader.readAsText(file)
  }

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 2 * 1024 * 1024) {
      toast(language === 'fa' ? 'حجم تصویر نباید بیشتر از ۲ مگابایت باشد' : 'Image must be under 2MB', 'error')
      return
    }
    setAvatarUploading(true)
    try {
      const reader = new FileReader()
      reader.onload = async () => {
        const base64 = (reader.result as string).split(',')[1]
        const t = token || localStorage.getItem('sanjabai_auth_token')
        const r = await fetch('/api/auth/avatar', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${t}`,
          },
          body: JSON.stringify({ avatar_base64: base64 }),
        })
        const data = await r.json()
        if (r.ok) {
          setAvatarUrl(data.avatar_url)
          toast(language === 'fa' ? 'تصویر پروفایل بروزرسانی شد' : 'Avatar updated', 'success')
        } else {
          toast(data.detail || (language === 'fa' ? 'خطا در آپلود تصویر' : 'Upload error'), 'error')
        }
        setAvatarUploading(false)
      }
      reader.readAsDataURL(file)
    } catch {
      toast(language === 'fa' ? 'خطا در آپلود تصویر' : 'Upload error', 'error')
      setAvatarUploading(false)
    }
  }

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast(language === 'fa' ? 'رمز عبور جدید با تکرار آن مطابقت ندارد' : 'Passwords do not match', 'error')
      return
    }
    if (newPassword.length < 8) {
      toast(language === 'fa' ? 'رمز عبور باید حداقل ۸ کاراکتر باشد' : 'Password must be at least 8 characters', 'error')
      return
    }
    setChangingPassword(true)
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${t}`,
        },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      if (r.ok) {
        toast(language === 'fa' ? 'رمز عبور با موفقیت تغییر کرد' : 'Password changed successfully', 'success')
        setCurrentPassword('')
        setNewPassword('')
        setConfirmPassword('')
      } else {
        const data = await r.json()
        toast(data.detail || (language === 'fa' ? 'خطا در تغییر رمز عبور' : 'Password change error'), 'error')
      }
    } catch {
      toast(language === 'fa' ? 'خطا در ارتباط با سرور' : 'Server connection error', 'error')
    } finally {
      setChangingPassword(false)
    }
  }

  const handleLinkTelegram = async () => {
    if (!telegramId) {
      toast(language === 'fa' ? 'شناسه تلگرام را وارد کنید' : 'Enter Telegram ID', 'error')
      return
    }
    setLinkingTelegram(true)
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/auth/telegram-link', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${t}`,
        },
        body: JSON.stringify({ telegram_id: parseInt(telegramId) }),
      })
      if (r.ok) {
        toast(language === 'fa' ? 'حساب تلگرام با موفقیت متصل شد' : 'Telegram linked successfully', 'success')
      } else {
        toast(language === 'fa' ? 'خطا در اتصال تلگرام' : 'Telegram link error', 'error')
      }
    } catch {
      toast(language === 'fa' ? 'خطا در ارتباط با سرور' : 'Server connection error', 'error')
    } finally {
      setLinkingTelegram(false)
    }
  }

  const userInitial = displayName?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || 'U'
  const isFa = language === 'fa'

  if (loadingProfile) {
    return (
      <div className="profile-page" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '50vh' }}>
        <div className="apikeys-spinner" style={{ width: 32, height: 32 }} />
      </div>
    )
  }

  return (
    <div className="profile-page">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div className="profile-header-icon">
            <Icon name="user" size={20} className="text-accent" />
          </div>
          <h1 className="page-title">
            {isFa ? 'پروفایل کاربری' : 'User Profile'}
          </h1>
        </div>
      </div>

      {/* Avatar + User info card */}
      <div className="card profile-avatar-card slide-up">
        <div className="profile-avatar-section">
          <div
            className="profile-avatar cursor-pointer relative"
            onClick={() => fileInputRef.current?.click()}
          >
            {avatarUrl ? (
              <img
                src={avatarUrl}
                alt="avatar"
                style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' }}
              />
            ) : (
              <span className="profile-avatar-letter">{userInitial}</span>
            )}
            <div style={{
              position: 'absolute', bottom: 0, right: 0,
              background: 'var(--accent)', borderRadius: '50%',
              width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: '2px solid var(--bg-card)',
            }}>
              {avatarUploading ? (
                <div className="apikeys-spinner" style={{ width: 12, height: 12 }} />
              ) : (
                <Icon name="camera" size={12} style={{ color: 'var(--text-on-accent)' }} />
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleAvatarUpload}
            />
          </div>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
              {displayName || user?.email || (isFa ? 'کاربر' : 'User')}
            </h2>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              {isFa
                ? `عضو از ${user?.created_at ? new Date(user.created_at).toLocaleDateString('fa-IR', { year: 'numeric', month: 'long' }) : '—'}`
                : `Member since ${user?.created_at ? new Date(user.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long' }) : '—'}`
              }
            </p>
            {bio && <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>{bio}</p>}
          </div>
        </div>

        <div className="profile-stats-grid">
          <div className="profile-stat-card">
            <Icon name="wallet" size={18} className="text-accent" />
            <div>
              <span className="profile-stat-label">{isFa ? 'موجودی' : 'Balance'}</span>
              <span className="profile-stat-value text-gradient">
                {balance === null ? '—' : isFa ? faPrice(balance) : `${balance.toLocaleString('en-US')} IRR`}
              </span>
            </div>
          </div>
          <div className="profile-stat-card">
            <Icon name="chart" size={18} className="text-positive" />
            <div>
              <span className="profile-stat-label">{isFa ? 'مصرف ماهانه' : 'Monthly usage'}</span>
              <span className="profile-stat-value">
                {!usage?.monthly
                  ? '—'
                  : isFa
                    ? `${faNum(usage.monthly.inp + usage.monthly.out || 0)} توکن`
                    : `${(usage.monthly.inp + usage.monthly.out || 0).toLocaleString('en-US')} tokens`}
              </span>
            </div>
          </div>
          <div className="profile-stat-card">
            <Icon name="mail" size={18} style={{ color: 'var(--info)' }} />
            <div>
              <span className="profile-stat-label">{isFa ? 'ایمیل' : 'Email'}</span>
              <span className="profile-stat-value">{user?.email || '—'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* ─── Profile Info Section ─── */}
      <div className="card profile-section-card slide-up" style={{ animationDelay: '0.05s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="user" size={16} className="text-accent" />
          <h2 className="card-title">
            {isFa ? 'اطلاعات شخصی' : 'Personal Info'}
          </h2>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="profile-input-group">
            <label className="profile-input-label">{isFa ? 'نام نمایشی' : 'Display Name'}</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={isFa ? 'نام شما' : 'Your name'}
              className="input"
              maxLength={100}
            />
          </div>
          <div className="profile-input-group">
            <label className="profile-input-label">{isFa ? 'بیوگرافی' : 'Bio'}</label>
            <textarea dir="rtl"
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              placeholder={isFa ? 'درباره خودتان بنویسید...' : 'Tell us about yourself...'}
              className="input"
              rows={3}
              maxLength={500}
              style={{ resize: 'vertical', minHeight: 80 }}
            />
            <span style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'left', display: 'block' }}>
              {faNum(bio.length)}/۵۰۰
            </span>
          </div>
          <div className="profile-input-group">
            <label className="profile-input-label">{isFa ? 'منطقه زمانی' : 'Timezone'}</label>
            <select
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="input"
              style={{ appearance: 'auto' }}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz.value} value={tz.value}>{tz.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* ─── AI Preferences Section ─── */}
      <div className="card profile-section-card slide-up" style={{ animationDelay: '0.1s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="cpu" size={16} className="text-accent" />
          <h2 className="card-title">
            {isFa ? 'تنظیمات هوش مصنوعی' : 'AI Preferences'}
          </h2>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Default Model */}
          <div className="profile-input-group">
            <label className="profile-input-label">{isFa ? 'مدل پیش‌فرض' : 'Default Model'}</label>
            <select
              value={defaultModel}
              onChange={(e) => setDefaultModel(e.target.value)}
              className="input"
              style={{ appearance: 'auto' }}
            >
              <option value="">{isFa ? '— انتخاب مدل —' : '— Select model —'}</option>
              {models.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              {isFa ? 'مدل پیش‌فرض برای چت‌های جدید' : 'Default model for new chats'}
            </p>
          </div>

          {/* AI Personality */}
          <div className="profile-input-group">
            <label className="profile-input-label">
              {isFa ? 'شخصیت / دستورالعمل هوش مصنوعی' : 'AI Personality / Instructions'}
            </label>
            <textarea dir="rtl"
              value={aiPersonality}
              onChange={(e) => setAiPersonality(e.target.value)}
              placeholder={isFa
                ? 'مثال: تو یک دستیار فنی هستی. پاسخ‌ها را مختصر و فنی بده...'
                : 'Example: You are a technical assistant. Keep responses concise and technical...'
              }
              className="input"
              rows={4}
              style={{ resize: 'vertical', minHeight: 100 }}
            />
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              {isFa
                ? 'این دستورالعمل به عنوان سیستم پرامپت در هر چت جدید ارسال می‌شود'
                : 'This instruction is sent as a system prompt in every new chat'}
            </p>
          </div>

          {/* Pinned Context (persistent note / .md upload) */}
          <div className="profile-input-group">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <label className="profile-input-label" style={{ marginBottom: 0 }}>
                {isFa ? 'یادداشت دائمی (قابل استفاده در همه چت‌ها)' : 'Pinned context (used in every chat)'}
              </label>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => mdFileInputRef.current?.click()}
              >
                <Icon name="paperclip" size={14} />
                <span>{isFa ? 'آپلود فایل md' : 'Upload .md file'}</span>
              </button>
              <input
                ref={mdFileInputRef}
                type="file"
                accept=".md,.markdown,.txt,text/markdown,text/plain"
                style={{ display: 'none' }}
                onChange={handlePinnedContextFileUpload}
              />
            </div>
            <textarea dir="rtl"
              value={pinnedContext}
              onChange={(e) => setPinnedContext(e.target.value)}
              placeholder={isFa
                ? 'یادداشتی که می‌خواهی هوش مصنوعی همیشه بداند — مثلاً پروژه‌هایت، اصطلاحات تیمت، یا محتوای یک فایل md. برخلاف حافظه‌های خودکار، این متن کامل در هر چت جدید تزریق می‌شود.'
                : "Anything you want the AI to always know — your projects, team jargon, or the contents of an .md file. Unlike auto-extracted memories, this whole note is injected into every new chat."
              }
              className="input"
              rows={8}
              maxLength={20000}
              style={{ resize: 'vertical', minHeight: 160, fontFamily: 'monospace', fontSize: 13 }}
            />
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              {isFa
                ? `این یادداشت (تا ۶۰۰۰ کاراکتر ابتدایی آن) در تمام چت‌ها و مستقل از دستیار انتخابی تزریق می‌شود. ${pinnedContext.length.toLocaleString('fa-IR')} / ۲۰,۰۰۰ کاراکتر`
                : `This note (up to its first 6000 characters) is injected into every chat regardless of the selected assistant. ${pinnedContext.length}/20,000 characters`}
            </p>
          </div>
        </div>
      </div>

      {/* ─── Autonomy Level Section ─── */}
      <div className="card profile-section-card slide-up" style={{ animationDelay: '0.15s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="rocket" size={16} className="text-accent" />
          <h2 className="card-title">
            {isFa ? 'سطح خودمختاری' : 'Autonomy Level'}
          </h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          {isFa
            ? 'سطح آزادی عمل هوش مصنوعی را تنظیم کنید. این تنظیم مشخص می‌کند هوش مصنوعی چقدر بدون تأیید شما عمل کند.'
            : 'Set how much freedom the AI has to act on your behalf. This controls when the AI asks for confirmation.'}
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {AUTONOMY_LEVELS.map((level) => (
            <div
              key={level.value}
              onClick={() => setAutonomyLevel(level.value)}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 12,
                padding: '14px 16px',
                borderRadius: 10,
                border: `2px solid ${autonomyLevel === level.value ? 'var(--accent)' : 'var(--border)'}`,
                background: autonomyLevel === level.value ? 'var(--accent-bg)' : 'transparent',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              <div style={{
                width: 20, height: 20, borderRadius: '50%', marginTop: 2, flexShrink: 0,
                border: `2px solid ${autonomyLevel === level.value ? 'var(--accent)' : 'var(--border)'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {autonomyLevel === level.value && (
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--accent)' }} />
                )}
              </div>
              <div className="flex-1">
                <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)', marginBottom: 4 }}>
                  {isFa ? level.label_fa : level.label_en}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  {isFa ? level.desc_fa : level.desc_en}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ─── Appearance & Language Section ─── */}
      <div className="card profile-section-card slide-up" style={{ animationDelay: '0.2s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="palette" size={16} className="text-accent" />
          <h2 className="card-title">
            {isFa ? 'ظاهر و زبان' : 'Appearance & Language'}
          </h2>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {/* Theme toggle */}
          <div className="profile-toggle-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Icon name="moon" size={16} className="text-muted" />
              <div>
                <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                  {isFa ? 'حالت تاریک' : 'Dark Mode'}
                </span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  {isFa ? 'استفاده از تم تاریک' : 'Use dark theme'}
                </p>
              </div>
            </div>
            <button
              className={`profile-toggle ${theme === 'dark' ? 'active' : ''}`}
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              role="switch"
              aria-checked={theme === 'dark'}
            >
              <span className="profile-toggle-knob" />
            </button>
          </div>

          {/* Language selector */}
          <div className="profile-toggle-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Icon name="globe" size={16} className="text-muted" />
              <div>
                <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                  {isFa ? 'زبان / Language' : 'Language / زبان'}
                </span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  {isFa ? 'فارسی یا انگلیسی' : 'Persian or English'}
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-sm ${language === 'fa' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setLanguage('fa')}
                style={{ fontSize: 12, padding: '4px 12px' }}
              >
                فارسی
              </button>
              <button
                className={`btn btn-sm ${language === 'en' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setLanguage('en')}
                style={{ fontSize: 12, padding: '4px 12px' }}
              >
                English
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ─── Notification Preferences ─── */}
      <div className="card profile-section-card slide-up" style={{ animationDelay: '0.25s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="bell" size={16} className="text-accent" />
          <h2 className="card-title">
            {isFa ? 'اعلان‌ها' : 'Notifications'}
          </h2>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <div className="profile-toggle-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Icon name="mail" size={16} className="text-muted" />
              <div>
                <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                  {isFa ? 'اعلان ایمیلی' : 'Email Notifications'}
                </span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  {isFa ? 'دریافت اعلانها از طریق ایمیل' : 'Receive notifications via email'}
                </p>
              </div>
            </div>
            <button
              className={`profile-toggle ${emailNotif ? 'active' : ''}`}
              onClick={() => setEmailNotif(!emailNotif)}
              role="switch"
              aria-checked={emailNotif}
            >
              <span className="profile-toggle-knob" />
            </button>
          </div>
          <div className="profile-toggle-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Icon name="send" size={16} className="text-muted" />
              <div>
                <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                  {isFa ? 'اعلان تلگرامی' : 'Telegram Notifications'}
                </span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  {isFa ? 'دریافت اعلانها از طریق ربات تلگرام' : 'Receive notifications via Telegram bot'}
                </p>
              </div>
            </div>
            <button
              className={`profile-toggle ${telegramNotif ? 'active' : ''}`}
              onClick={() => setTelegramNotif(!telegramNotif)}
              role="switch"
              aria-checked={telegramNotif}
            >
              <span className="profile-toggle-knob" />
            </button>
          </div>
        </div>
      </div>

      {/* ─── Save Button ─── */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 24 }}>
        <button
          onClick={handleSaveProfile}
          disabled={saving}
          className="btn btn-primary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '10px 24px', fontSize: 14, fontWeight: 600 }}
        >
          {saving ? (
            <span className="apikeys-spinner" />
          ) : (
            <Icon name="check" size={14} />
          )}
          {isFa ? 'ذخیره تغییرات' : 'Save Changes'}
        </button>
      </div>

      {/* Change password */}
      <div className="card profile-section-card slide-up" style={{ animationDelay: '0.3s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="lock" size={16} className="text-accent" />
          <h2 className="card-title">
            {isFa ? 'تغییر رمز عبور' : 'Change Password'}
          </h2>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="profile-input-group">
            <label className="profile-input-label">{isFa ? 'رمز عبور فعلی' : 'Current Password'}</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder={isFa ? 'رمز عبور فعلی' : 'Current password'}
              className="input"
            />
          </div>
          <div className="profile-input-group">
            <label className="profile-input-label">{isFa ? 'رمز عبور جدید' : 'New Password'}</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder={isFa ? 'حداقل ۸ کاراکتر' : 'At least 8 characters'}
              className="input"
            />
          </div>
          <div className="profile-input-group">
            <label className="profile-input-label">{isFa ? 'تکرار رمز عبور جدید' : 'Confirm New Password'}</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder={isFa ? 'تکرار رمز عبور جدید' : 'Confirm new password'}
              className="input"
            />
          </div>
          <button
            onClick={handleChangePassword}
            disabled={changingPassword || !currentPassword || !newPassword}
            className="btn btn-primary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, alignSelf: 'flex-start' }}
          >
            {changingPassword ? (
              <span className="apikeys-spinner" />
            ) : (
              <Icon name="lock" size={14} />
            )}
            {isFa ? 'تغییر رمز عبور' : 'Change Password'}
          </button>
        </div>
      </div>

      {/* Telegram link */}
      <div className="card profile-section-card slide-up" style={{ animationDelay: '0.35s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Icon name="send" size={16} className="text-accent" />
          <h2 className="card-title">
            {isFa ? 'اتصال تلگرام' : 'Link Telegram'}
          </h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          {isFa
            ? 'با اتصال حساب تلگرام می‌توانید از طریق ربات Sanjabai چت کنید و موجودی خود را ببینید.'
            : 'Link your Telegram account to chat via the Sanjabai bot and view your balance.'}
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="number"
            value={telegramId}
            onChange={(e) => setTelegramId(e.target.value)}
            placeholder={isFa ? 'شناسه عددی تلگرام (Telegram ID)' : 'Telegram numeric ID'}
            className="input flex-1"
          />
          <button
            onClick={handleLinkTelegram}
            disabled={linkingTelegram || !telegramId}
            className="btn btn-secondary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            {linkingTelegram ? (
              <span className="apikeys-spinner" />
            ) : (
              <Icon name="link" size={14} />
            )}
            {isFa ? 'اتصال' : 'Link'}
          </button>
        </div>
        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
          <Icon name="info" size={12} />
          {isFa
            ? 'برای دریافت شناسه تلگرام، به ربات @userinfobot پیام دهید.'
            : 'To get your Telegram ID, message @userinfobot.'}
        </p>
      </div>

      {/* Referral */}
      <div className="card profile-section-card slide-up" style={{ animationDelay: '0.4s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Icon name="gift" size={16} className="text-accent" />
          <h2 className="card-title">
            {isFa ? 'دعوت دوستان' : 'Invite Friends'}
          </h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          {isFa
            ? 'با دعوت دوستان به Sanjabai، به ازای هر ثبت‌نام موفق اعتبار هدیه دریافت کنید.'
            : 'Invite friends to Sanjabai and earn bonus credits for each successful signup.'}
        </p>
        {user?.referral_code && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label className="profile-input-label">{isFa ? 'کد دعوت شما' : 'Your Referral Code'}</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <code className="apikeys-code-block flex-1">
                  {user.referral_code}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(user.referral_code || '')
                    toast(isFa ? 'کد کپی شد' : 'Code copied', 'success')
                  }}
                  className="btn btn-secondary btn-sm"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                >
                  <Icon name="copy" size={14} />
                  {isFa ? 'کپی' : 'Copy'}
                </button>
              </div>
            </div>
            <div>
              <label className="profile-input-label">{isFa ? 'لینک دعوت' : 'Referral Link'}</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <code className="apikeys-code-block" style={{ flex: 1, fontSize: 11 }}>
                  {typeof window !== 'undefined' ? `${window.location.origin}/signup?ref=${user.referral_code}` : ''}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/signup?ref=${user.referral_code}`)
                    toast(isFa ? 'لینک کپی شد' : 'Link copied', 'success')
                  }}
                  className="btn btn-secondary btn-sm"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                >
                  <Icon name="copy" size={14} />
                  {isFa ? 'کپی' : 'Copy'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Danger zone */}
      <div className="card profile-danger-card slide-up" style={{ animationDelay: '0.45s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Icon name="warning" size={16} className="text-danger" />
          <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--danger)' }}>
            {isFa ? 'منطقه خطر' : 'Danger Zone'}
          </h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          {isFa
            ? 'حذف حساب کاربری غیرقابل بازگشت است. تمام دادهها و تاریخچه شما حذف خواهد شد.'
            : 'Account deletion is permanent. All your data and history will be removed.'}
        </p>
        <button className="btn btn-danger" disabled style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Icon name="trash" size={14} />
          {isFa ? 'حذف حساب (به‌زودی)' : 'Delete Account (coming soon)'}
        </button>
      </div>
    </div>
  )
}
