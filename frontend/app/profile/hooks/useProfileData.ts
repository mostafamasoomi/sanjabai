'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { useProfileDataStrings } from './useProfileData.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Profile page state, fetches, and mutation handlers. Split out of page.tsx
   to keep every file under the project's 500-line cap -- pure move, no
   behaviour change. Owns everything that isn't JSX; page.tsx and the
   components/ presentational pieces just render what this returns.

   Two different "language"s live in this file. `language`/`setLanguage`
   below is the ACCOUNT's own stored preference (`GET/PUT /api/auth/profile`
   `.language`), unrelated to the site-wide UI language. The toasts here used
   to pick fa/en off that stored preference, which meant a user who flipped
   the header's language toggle to English still got Persian toasts until
   they separately saved an English account preference in AppearanceSection.
   Toasts are transient UI chrome, so they now follow `useLang()` (`s.*`
   below) like every other rendered string on the page; `language` itself is
   untouched and still round-trips to the API exactly as before.
   ═══════════════════════════════════════════════════════════════════════════ */
export function useProfileData() {
  const { user, token } = useAuth()
  const lang = useLang()
  const s = useProfileDataStrings(lang)

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

  // Load-error states. These used to be empty `catch {}` blocks, so a failed
  // fetch left the form silently blank with no signal to the user.
  const [profileError, setProfileError] = useState(false)
  const [modelsError, setModelsError] = useState(false)
  const [statsError, setStatsError] = useState(false)

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
    setProfileError(false)
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
      } else {
        setProfileError(true)
      }
    } catch {
      setProfileError(true)
    } finally {
      setLoadingProfile(false)
    }
  }

  const fetchModels = async () => {
    setModelsError(false)
    try {
      // /api/models does not exist (404). The real catalog endpoint is
      // /catalog/models (same shape: { data: [{ id }] }); the old 404 is why
      // the default-model <select> could never populate.
      const r = await fetch('/api/catalog/models')
      if (r.ok) {
        const data = await r.json()
        setModels((data.data || []).map((m: { id: string }) => m.id))
      } else {
        setModelsError(true)
      }
    } catch {
      setModelsError(true)
    }
  }

  const fetchUsage = async () => {
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/me/usage', { headers: { Authorization: `Bearer ${t}` } })
      if (r.ok) setUsage(await r.json())
      else setStatsError(true)
    } catch {
      setStatsError(true)
    }
  }

  const fetchBalance = async () => {
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/wallet', { headers: { Authorization: `Bearer ${t}` } })
      if (r.ok) setBalance((await r.json()).balance)
      else setStatsError(true)
    } catch {
      setStatsError(true)
    }
  }

  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await apiFetch('/api/auth/profile', {
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
        toast(s.profileSaved, 'success')
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
        toast(data.detail || s.profileSaveError, 'error')
      }
    } catch {
      toast(s.serverError, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handlePinnedContextFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (file.size > 1024 * 1024) {
      toast(s.fileTooLarge, 'error')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const text = String(reader.result || '').slice(0, 20000)
      setPinnedContext(text)
      toast(s.fileLoaded, 'success')
    }
    reader.onerror = () => {
      toast(s.fileReadError, 'error')
    }
    reader.readAsText(file)
  }

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 2 * 1024 * 1024) {
      toast(s.imageTooLarge, 'error')
      return
    }
    setAvatarUploading(true)
    try {
      const reader = new FileReader()
      reader.onload = async () => {
        const base64 = (reader.result as string).split(',')[1]
        const t = token || localStorage.getItem('sanjabai_auth_token')
        const r = await apiFetch('/api/auth/avatar', {
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
          toast(s.avatarUpdated, 'success')
        } else {
          toast(data.detail || s.avatarUploadError, 'error')
        }
        setAvatarUploading(false)
      }
      reader.readAsDataURL(file)
    } catch {
      toast(s.avatarUploadError, 'error')
      setAvatarUploading(false)
    }
  }

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast(s.passwordMismatch, 'error')
      return
    }
    if (newPassword.length < 8) {
      toast(s.passwordTooShort, 'error')
      return
    }
    setChangingPassword(true)
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await apiFetch('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${t}`,
        },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      if (r.ok) {
        toast(s.passwordChanged, 'success')
        setCurrentPassword('')
        setNewPassword('')
        setConfirmPassword('')
      } else {
        const data = await r.json()
        toast(data.detail || s.passwordChangeError, 'error')
      }
    } catch {
      toast(s.serverError, 'error')
    } finally {
      setChangingPassword(false)
    }
  }

  const handleLinkTelegram = async () => {
    if (!telegramId) {
      toast(s.enterTelegramId, 'error')
      return
    }
    // Validate before sending: a non-numeric value makes parseInt return NaN,
    // which serialises to null and the backend rejects with a generic error.
    // Telegram IDs are positive integers.
    const tgId = parseInt(telegramId.trim(), 10)
    if (!Number.isInteger(tgId) || tgId <= 0 || String(tgId) !== telegramId.trim()) {
      toast(s.telegramIdInvalid, 'error')
      return
    }
    setLinkingTelegram(true)
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await apiFetch('/api/auth/telegram-link', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${t}`,
        },
        body: JSON.stringify({ telegram_id: tgId }),
      })
      if (r.ok) {
        toast(s.telegramLinked, 'success')
      } else {
        toast(s.telegramLinkError, 'error')
      }
    } catch {
      toast(s.serverError, 'error')
    } finally {
      setLinkingTelegram(false)
    }
  }

  const userInitial = displayName?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || 'U'

  // Dirty check against the values last loaded/saved. originalValues was
  // declared for this but never read, so Save was always enabled. The `??`
  // defaults mean an as-yet-unpopulated originalValues ({}) compares equal to
  // the initial field defaults, so the form starts clean.
  const isDirty =
    displayName !== (originalValues.display_name ?? '') ||
    bio !== (originalValues.bio ?? '') ||
    timezone !== (originalValues.timezone ?? 'Asia/Tehran') ||
    language !== (originalValues.language ?? 'fa') ||
    defaultModel !== (originalValues.default_model ?? '') ||
    aiPersonality !== (originalValues.ai_personality ?? '') ||
    pinnedContext !== (originalValues.pinned_context ?? '') ||
    autonomyLevel !== (originalValues.autonomy_level ?? 'medium') ||
    theme !== (originalValues.theme ?? 'dark') ||
    emailNotif !== (originalValues.email_notif ?? true) ||
    telegramNotif !== (originalValues.telegram_notif ?? false)

  return {
    user, token,
    displayName, setDisplayName,
    bio, setBio,
    avatarUrl,
    timezone, setTimezone,
    language, setLanguage,
    defaultModel, setDefaultModel,
    aiPersonality, setAiPersonality,
    pinnedContext, setPinnedContext,
    autonomyLevel, setAutonomyLevel,
    theme, setTheme,
    emailNotif, setEmailNotif,
    telegramNotif, setTelegramNotif,
    models,
    currentPassword, setCurrentPassword,
    newPassword, setNewPassword,
    confirmPassword, setConfirmPassword,
    changingPassword,
    telegramId, setTelegramId,
    linkingTelegram,
    usage, balance,
    loadingProfile, setLoadingProfile,
    saving,
    avatarUploading,
    profileError, modelsError, statsError,
    fetchProfile, fetchModels,
    handleSaveProfile,
    handlePinnedContextFileUpload,
    handleAvatarUpload,
    handleChangePassword,
    handleLinkTelegram,
    userInitial, isDirty,
  }
}
