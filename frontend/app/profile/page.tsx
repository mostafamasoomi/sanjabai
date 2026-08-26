'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { useProfileData } from './hooks/useProfileData'
import { profilePageStrings } from './page.strings'
import ProfileErrorBanner from './components/ProfileErrorBanner'
import ProfileAvatarCard from './components/ProfileAvatarCard'
import PersonalInfoSection from './components/PersonalInfoSection'
import AIPreferencesSection from './components/AIPreferencesSection'
import AutonomySection from './components/AutonomySection'
import AppearanceSection from './components/AppearanceSection'
import NotificationsSection from './components/NotificationsSection'
import ChangePasswordSection from './components/ChangePasswordSection'
import TelegramLinkSection from './components/TelegramLinkSection'
import ReferralSection from './components/ReferralSection'
import DangerZoneSection from './components/DangerZoneSection'

/* ═══════════════════════════════════════════════════════════════════════════
   Profile page. State/logic lives in hooks/useProfileData.ts (fetches, form
   state, isDirty, mutation handlers); each card is a presentational
   component under components/ -- this file just wires them together and
   owns only what's genuinely page-wide (header, load-error banner, loading
   spinner, save button). Split out of a single 1073-line page.tsx to keep
   every file under the project's 500-line cap; pure move, no behaviour
   change. See app/chat/ for the pattern this follows.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function ProfilePage() {
  const lang = useLang()
  const s = profilePageStrings(lang)
  const {
    user,
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
  } = useProfileData()

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
            {s.title}
          </h1>
        </div>
      </div>

      {profileError && (
        <ProfileErrorBanner
          onRetry={() => { setLoadingProfile(true); fetchProfile() }}
        />
      )}

      <ProfileAvatarCard
        avatarUrl={avatarUrl}
        avatarUploading={avatarUploading}
        handleAvatarUpload={handleAvatarUpload}
        userInitial={userInitial}
        displayName={displayName}
        bio={bio}
        user={user}
        balance={balance}
        usage={usage}
        statsError={statsError}
      />

      <PersonalInfoSection
        displayName={displayName}
        setDisplayName={setDisplayName}
        bio={bio}
        setBio={setBio}
        timezone={timezone}
        setTimezone={setTimezone}
      />

      <AIPreferencesSection
        defaultModel={defaultModel}
        setDefaultModel={setDefaultModel}
        models={models}
        modelsError={modelsError}
        fetchModels={fetchModels}
        aiPersonality={aiPersonality}
        setAiPersonality={setAiPersonality}
        pinnedContext={pinnedContext}
        setPinnedContext={setPinnedContext}
        handlePinnedContextFileUpload={handlePinnedContextFileUpload}
      />

      <AutonomySection
        autonomyLevel={autonomyLevel}
        setAutonomyLevel={setAutonomyLevel}
      />

      <AppearanceSection
        theme={theme}
        setTheme={setTheme}
        language={language}
        setLanguage={setLanguage}
      />

      <NotificationsSection
        emailNotif={emailNotif}
        setEmailNotif={setEmailNotif}
        telegramNotif={telegramNotif}
        setTelegramNotif={setTelegramNotif}
      />

      {/* ─── Save Button ─── */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 24 }}>
        <button
          onClick={handleSaveProfile}
          disabled={saving || !isDirty}
          className="btn btn-primary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '10px 24px', fontSize: 14, fontWeight: 600, opacity: saving || !isDirty ? 0.5 : 1 }}
        >
          {saving ? (
            <span className="apikeys-spinner" />
          ) : (
            <Icon name="check" size={14} />
          )}
          {s.saveChanges}
        </button>
      </div>

      <ChangePasswordSection
        currentPassword={currentPassword}
        setCurrentPassword={setCurrentPassword}
        newPassword={newPassword}
        setNewPassword={setNewPassword}
        confirmPassword={confirmPassword}
        setConfirmPassword={setConfirmPassword}
        changingPassword={changingPassword}
        handleChangePassword={handleChangePassword}
      />

      <TelegramLinkSection
        telegramId={telegramId}
        setTelegramId={setTelegramId}
        linkingTelegram={linkingTelegram}
        handleLinkTelegram={handleLinkTelegram}
      />

      <ReferralSection user={user} />

      <DangerZoneSection />
    </div>
  )
}
