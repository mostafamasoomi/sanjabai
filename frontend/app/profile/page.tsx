'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'

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

  useEffect(() => {
    if (user) {
      fetchUsage()
      fetchBalance()
    }
  }, [user])

  const fetchUsage = async () => {
    try {
      const token = localStorage.getItem('token')
      const r = await fetch('/api/usage', { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) setUsage(await r.json())
    } catch {}
  }

  const fetchBalance = async () => {
    try {
      const token = localStorage.getItem('token')
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
      const token = localStorage.getItem('token')
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
      const token = localStorage.getItem('token')
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

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold">پروفایل کاربری</h1>

      {/* User info */}
      <div className="card">
        <h2 className="text-lg font-bold mb-4">اطلاعات حساب</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-[var(--text-muted)]">ایمیل</label>
            <p className="font-medium">{user?.email || '—'}</p>
          </div>
          <div>
            <label className="text-xs text-[var(--text-muted)]">تاریخ عضویت</label>
            <p className="font-medium">{user?.created_at ? new Date(user.created_at).toLocaleDateString('fa-IR') : '—'}</p>
          </div>
          <div>
            <label className="text-xs text-[var(--text-muted)]">موجودی</label>
            <p className="font-medium text-gradient">{balance !== null ? `${balance.toLocaleString('fa-IR')} تومان` : '—'}</p>
          </div>
          <div>
            <label className="text-xs text-[var(--text-muted)]">مصرف امروز</label>
            <p className="font-medium">{usage ? `${usage.used_today?.toLocaleString('fa-IR')} / ${usage.daily_limit?.toLocaleString('fa-IR')} توکن` : '—'}</p>
          </div>
        </div>
      </div>

      {/* Change password */}
      <div className="card">
        <h2 className="text-lg font-bold mb-4">تغییر رمز عبور</h2>
        <div className="space-y-3">
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="رمز عبور فعلی"
            className="input"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="رمز عبور جدید (حداقل ۸ کاراکتر)"
            className="input"
          />
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="تکرار رمز عبور جدید"
            className="input"
          />
          <button
            onClick={handleChangePassword}
            disabled={changingPassword || !currentPassword || !newPassword}
            className="btn btn-primary"
          >
            {changingPassword ? '⏳ در حال تغییر...' : '🔒 تغییر رمز عبور'}
          </button>
        </div>
      </div>

      {/* Telegram link */}
      <div className="card">
        <h2 className="text-lg font-bold mb-4">اتصال تلگرام</h2>
        <p className="text-sm text-[var(--text-dim)] mb-4">
          با اتصال حساب تلگرام می‌توانید از طریق ربات Multiai چت کنید و موجودی خود را ببینید.
        </p>
        <div className="flex gap-2">
          <input
            type="number"
            value={telegramId}
            onChange={(e) => setTelegramId(e.target.value)}
            placeholder="شناسه عددی تلگرام (Telegram ID)"
            className="input flex-1"
          />
          <button
            onClick={handleLinkTelegram}
            disabled={linkingTelegram || !telegramId}
            className="btn btn-secondary"
          >
            {linkingTelegram ? '⏳' : '🔗 اتصال'}
          </button>
        </div>
        <p className="text-xs text-[var(--text-muted)] mt-2">
          برای دریافت شناسه تلگرام، به ربات @userinfobot پیام دهید.
        </p>
      </div>

      {/* Referral */}
      <div className="card">
        <h2 className="text-lg font-bold mb-4">🎁 دعوت دوستان</h2>
        <p className="text-sm text-[var(--text-dim)] mb-4">
          با دعوت دوستان به Multiai، به ازای هر ثبت‌نام موفق <strong>۵,۰۰۰ تومان</strong> اعتبار هدیه بگیرید.
        </p>
        {user?.referral_code && (
          <div className="space-y-3">
            <div>
              <label className="text-xs text-[var(--text-muted)]">کد دعوت شما</label>
              <div className="flex gap-2 mt-1">
                <code className="flex-1 p-3 rounded-lg bg-[var(--bg)] border border-[var(--border)] text-sm font-mono">
                  {user.referral_code}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(user.referral_code || '')
                    toast('کد کپی شد', 'success')
                  }}
                  className="btn btn-secondary btn-sm"
                >
                  📋
                </button>
              </div>
            </div>
            <div>
              <label className="text-xs text-[var(--text-muted)]">لینک دعوت</label>
              <div className="flex gap-2 mt-1">
                <code className="flex-1 p-3 rounded-lg bg-[var(--bg)] border border-[var(--border)] text-xs font-mono truncate">
                  {typeof window !== 'undefined' ? `${window.location.origin}/signup?ref=${user.referral_code}` : ''}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/signup?ref=${user.referral_code}`)
                    toast('لینک کپی شد', 'success')
                  }}
                  className="btn btn-secondary btn-sm"
                >
                  📋
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Danger zone */}
      <div className="card border-[var(--danger)]/30">
        <h2 className="text-lg font-bold text-[var(--danger)] mb-2">منطقه خطر</h2>
        <p className="text-sm text-[var(--text-dim)] mb-4">
          حذف حساب کاربری غیرقابل بازگشت است. تمام داده‌ها و تاریخچه شما حذف خواهد شد.
        </p>
        <button className="btn btn-danger" disabled>
          🗑️ حذف حساب (به‌زودی)
        </button>
      </div>
    </div>
  )
}