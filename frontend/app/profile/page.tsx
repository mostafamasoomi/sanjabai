'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

export default function ProfilePage() {
  const { user } = useAuth()

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

  // Settings toggles — persisted to localStorage
  const [emailNotif, setEmailNotif] = useState(() => typeof window !== 'undefined' ? localStorage.getItem('pref_email_notif') === 'true' : true)
  const [telegramNotif, setTelegramNotif] = useState(() => typeof window !== 'undefined' ? localStorage.getItem('pref_telegram_notif') === 'true' : false)
  const [darkMode, setDarkMode] = useState(() => typeof window !== 'undefined' ? localStorage.getItem('pref_dark_mode') !== 'false' : true)

  useEffect(() => {
    if (user) {
      fetchUsage()
      fetchBalance()
    }
  }, [user])

  const fetchUsage = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const r = await fetch('/api/usage', { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) setUsage(await r.json())
    } catch {}
  }

  const fetchBalance = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const r = await fetch('/api/wallet', { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) setBalance((await r.json()).balance)
    } catch {}
  }

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast('رمز عبور جدید با تکرار آن مطابقت ندارد', 'error')
      return
    }
    if (newPassword.length < 8) {
      toast('رمز عبور باید حداقل ۸ کاراکتر باشد', 'error')
      return
    }
    setChangingPassword(true)
    try {
      const token = localStorage.getItem('auth_token')
      const r = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      const data = await r.json()
      if (r.ok) {
        toast('رمز عبور با موفقیت تغییر کرد', 'success')
        setCurrentPassword('')
        setNewPassword('')
        setConfirmPassword('')
      } else {
        toast(data.detail || 'خطا در تغییر رمز عبور', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setChangingPassword(false)
    }
  }

  const handleLinkTelegram = async () => {
    if (!telegramId) {
      toast('شناسه تلگرام را وارد کنید', 'error')
      return
    }
    setLinkingTelegram(true)
    try {
      const token = localStorage.getItem('auth_token')
      const r = await fetch('/api/auth/telegram-link', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ telegram_id: parseInt(telegramId) }),
      })
      if (r.ok) {
        toast('حساب تلگرام با موفقیت متصل شد', 'success')
      } else {
        toast('خطا در اتصال تلگرام', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setLinkingTelegram(false)
    }
  }

  const userInitial = user?.email?.[0]?.toUpperCase() || 'U'

  return (
    <div className="profile-page">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <div className="profile-header-icon">
          <Icon name="user" size={20} style={{ color: 'var(--accent)' }} />
        </div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>پروفایل کاربری</h1>
      </div>

      {/* Avatar + User info card */}
      <div className="card profile-avatar-card">
        <div className="profile-avatar-section">
          <div className="profile-avatar">
            <span className="profile-avatar-letter">{userInitial}</span>
          </div>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{user?.email || 'کاربر'}</h2>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              عضو از {user?.created_at ? new Date(user.created_at).toLocaleDateString('fa-IR', { year: 'numeric', month: 'long' }) : '—'}
            </p>
          </div>
        </div>

        <div className="profile-stats-grid">
          <div className="profile-stat-card">
            <Icon name="wallet" size={18} style={{ color: 'var(--accent)' }} />
            <div>
              <span className="profile-stat-label">موجودی</span>
              <span className="profile-stat-value text-gradient">
                {balance !== null ? `${balance.toLocaleString('fa-IR')} تومان` : '—'}
              </span>
            </div>
          </div>
          <div className="profile-stat-card">
            <Icon name="chart" size={18} style={{ color: 'var(--positive)' }} />
            <div>
              <span className="profile-stat-label">مصرف امروز</span>
              <span className="profile-stat-value">
                {usage ? `${usage.used_today?.toLocaleString('fa-IR')} / ${usage.daily_limit?.toLocaleString('fa-IR')} توکن` : '—'}
              </span>
            </div>
          </div>
          <div className="profile-stat-card">
            <Icon name="mail" size={18} style={{ color: 'var(--info)' }} />
            <div>
              <span className="profile-stat-label">ایمیل</span>
              <span className="profile-stat-value">{user?.email || '—'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Settings toggles */}
      <div className="card profile-section-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="settings" size={16} style={{ color: 'var(--accent)' }} />
          <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>تنظیمات</h2>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <div className="profile-toggle-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Icon name="mail" size={16} style={{ color: 'var(--text-muted)' }} />
              <div>
                <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>اعلان ایمیلی</span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>دریافت اعلانها از طریق ایمیل</p>
              </div>
            </div>
            <button
              className={`profile-toggle ${emailNotif ? 'active' : ''}`}
              onClick={() => {
                const next = !emailNotif
                setEmailNotif(next)
                localStorage.setItem('pref_email_notif', String(next))
                toast(next ? 'اعلان ایمیلی فعال شد' : 'اعلان ایمیلی غیرفعال شد', 'success')
              }}
              role="switch"
              aria-checked={emailNotif}
            >
              <span className="profile-toggle-knob" />
            </button>
          </div>

          <div className="profile-toggle-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Icon name="send" size={16} style={{ color: 'var(--text-muted)' }} />
              <div>
                <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>اعلان تلگرامی</span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>دریافت اعلانها از طریق ربات تلگرام</p>
              </div>
            </div>
            <button
              className={`profile-toggle ${telegramNotif ? 'active' : ''}`}
              onClick={() => {
                const next = !telegramNotif
                setTelegramNotif(next)
                localStorage.setItem('pref_telegram_notif', String(next))
                toast(next ? 'اعلان تلگرامی فعال شد' : 'اعلان تلگرامی غیرفعال شد', 'success')
              }}
              role="switch"
              aria-checked={telegramNotif}
            >
              <span className="profile-toggle-knob" />
            </button>
          </div>

          <div className="profile-toggle-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Icon name="moon" size={16} style={{ color: 'var(--text-muted)' }} />
              <div>
                <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>حالت تاریک</span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>استفاده از تم تاریک</p>
              </div>
            </div>
            <button
              className={`profile-toggle ${darkMode ? 'active' : ''}`}
              onClick={() => {
                const next = !darkMode
                setDarkMode(next)
                localStorage.setItem('pref_dark_mode', String(next))
                if (next) {
                  document.documentElement.classList.add('dark')
                } else {
                  document.documentElement.classList.remove('dark')
                }
                toast(next ? 'حالت تاریک فعال شد' : 'حالت روشن فعال شد', 'success')
              }}
              role="switch"
              aria-checked={darkMode}
            >
              <span className="profile-toggle-knob" />
            </button>
          </div>
        </div>
      </div>

      {/* Change password */}
      <div className="card profile-section-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="lock" size={16} style={{ color: 'var(--accent)' }} />
          <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>تغییر رمز عبور</h2>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="profile-input-group">
            <label className="profile-input-label">رمز عبور فعلی</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="رمز عبور فعلی"
              className="input"
            />
          </div>
          <div className="profile-input-group">
            <label className="profile-input-label">رمز عبور جدید</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="حداقل ۸ کاراکتر"
              className="input"
            />
          </div>
          <div className="profile-input-group">
            <label className="profile-input-label">تکرار رمز عبور جدید</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="تکرار رمز عبور جدید"
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
            تغییر رمز عبور
          </button>
        </div>
      </div>

      {/* Telegram link */}
      <div className="card profile-section-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Icon name="send" size={16} style={{ color: 'var(--accent)' }} />
          <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>اتصال تلگرام</h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          با اتصال حساب تلگرام میتوانید از طریق ربات Multiai چت کنید و موجودی خود را ببینید.
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="number"
            value={telegramId}
            onChange={(e) => setTelegramId(e.target.value)}
            placeholder="شناسه عددی تلگرام (Telegram ID)"
            className="input"
            style={{ flex: 1 }}
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
            اتصال
          </button>
        </div>
        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
          <Icon name="info" size={12} />
          برای دریافت شناسه تلگرام، به ربات @userinfobot پیام دهید.
        </p>
      </div>

      {/* Referral */}
      <div className="card profile-section-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Icon name="gift" size={16} style={{ color: 'var(--accent)' }} />
          <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>دعوت دوستان</h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          با دعوت دوستان به Multiai، به ازای هر ثبتنام موفق اعتبار هدیه دریافت کنید.
        </p>
        {user?.referral_code && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label className="profile-input-label">کد دعوت شما</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <code className="apikeys-code-block" style={{ flex: 1 }}>
                  {user.referral_code}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(user.referral_code || '')
                    toast('کد کپی شد', 'success')
                  }}
                  className="btn btn-secondary btn-sm"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                >
                  <Icon name="copy" size={14} />
                  کپی
                </button>
              </div>
            </div>
            <div>
              <label className="profile-input-label">لینک دعوت</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <code className="apikeys-code-block" style={{ flex: 1, fontSize: 11 }}>
                  {typeof window !== 'undefined' ? `${window.location.origin}/signup?ref=${user.referral_code}` : ''}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/signup?ref=${user.referral_code}`)
                    toast('لینک کپی شد', 'success')
                  }}
                  className="btn btn-secondary btn-sm"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                >
                  <Icon name="copy" size={14} />
                  کپی
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Danger zone */}
      <div className="card profile-danger-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Icon name="warning" size={16} style={{ color: 'var(--danger)' }} />
          <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--danger)' }}>منطقه خطر</h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          حذف حساب کاربری غیرقابل بازگشت است. تمام دادهها و تاریخچه شما حذف خواهد شد.
        </p>
        <button className="btn btn-danger" disabled style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Icon name="trash" size={14} />
          حذف حساب (بهزودی)
        </button>
      </div>
    </div>
  )
}
