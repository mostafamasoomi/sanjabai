'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { useCatalog, priceBand, PRICE_BAND_LABEL } from '@/lib/useCatalog'
import { toast } from '@/components/ui'
import { Icon, type IconName } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt, navIcon } from '@/lib/i18n'
import { assistantDetailPageStrings } from './page.strings'

/* ═══════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════ */

type Assistant = {
  id: number
  name: string
  description: string
  system_prompt: string
  model_id: string | null
  icon: string | null
  is_public: boolean
  user_id: number
  created_at: string
  updated_at: string
}

/* ═══════════════════════════════════════════════════════════════
   Loading Skeleton
   ═══════════════════════════════════════════════════════════════ */

function DetailSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', padding: '1rem 0' }}>
      <div className="skeleton" style={{ width: '8rem', height: '1.25rem' }} />
      <div className="skeleton" style={{ width: '60%', height: '1.5rem' }} />
      <div className="skeleton" style={{ width: '100%', height: '2.5rem', borderRadius: 'var(--radius-md)' }} />
      <div className="skeleton" style={{ width: '100%', height: '2.5rem', borderRadius: 'var(--radius-md)' }} />
      <div className="skeleton" style={{ width: '100%', height: '10rem', borderRadius: 'var(--radius-md)' }} />
      <div className="skeleton" style={{ width: '100%', height: '2.5rem', borderRadius: 'var(--radius-md)' }} />
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Assistant Detail / Edit Page
   ═══════════════════════════════════════════════════════════════ */

export default function AssistantDetailPage() {
  const params = useParams()
  const router = useRouter()
  const { token, user, loading: authLoading } = useAuth()
  const { models, loading: modelsLoading } = useCatalog()
  const lang = useLang()
  const s = assistantDetailPageStrings(lang)
  const f = fmt(lang)

  const assistantId = params?.id as string

  const [assistant, setAssistant] = useState<Assistant | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  // Edit form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [modelId, setModelId] = useState('')
  const [isPublic, setIsPublic] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const fetchAssistant = useCallback(async () => {
    if (!assistantId || !token) return
    setLoading(true)
    try {
      const res = await fetch(`/api/assistants/${assistantId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data: Assistant = await res.json()
        setAssistant(data)
        setName(data.name)
        setDescription(data.description || '')
        setSystemPrompt(data.system_prompt || '')
        setModelId(data.model_id || '')
        setIsPublic(data.is_public)
      } else {
        setError(true)
      }
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [assistantId, token])

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace('/login')
      return
    }
    fetchAssistant()
  }, [fetchAssistant, authLoading, user, router])

  const isOwner = user && assistant && user.id === assistant.user_id

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token || !assistant) return
    if (!name.trim()) {
      toast(s.requiredNameToast, 'error')
      return
    }
    if (!systemPrompt.trim()) {
      toast(s.requiredPromptToast, 'error')
      return
    }

    setSubmitting(true)
    try {
      const res = await apiFetch(`/api/assistants/${assistant.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
          system_prompt: systemPrompt.trim(),
          model_id: modelId || null,
          is_public: isPublic,
        }),
      })

      if (res.ok) {
        const data = await res.json()
        setAssistant(data)
        toast(s.updatedToast, 'success')
      } else {
        const data = await res.json()
        toast(data.detail || s.updateErrorFallback, 'error')
      }
    } catch {
      toast(s.serverErrorToast, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!token || !assistant) return
    if (!confirmDelete) {
      setConfirmDelete(true)
      setTimeout(() => setConfirmDelete(false), 5000)
      return
    }

    setDeleting(true)
    try {
      const res = await apiFetch(`/api/assistants/${assistant.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        toast(s.deleteSuccessToast, 'success')
        router.push('/assistants')
      } else {
        toast(s.deleteErrorToast, 'error')
      }
    } catch {
      toast(s.serverErrorToast, 'error')
    } finally {
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  // Loading state
  if (loading || authLoading) {
    return (
      <div style={{ maxWidth: '40rem', margin: '0 auto' }}>
        <DetailSkeleton />
      </div>
    )
  }

  // Error state
  if (error || !assistant) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
          gap: '1.5rem',
        }}
      >
        <Icon name="warning" size={48} className="text-[var(--text-muted)]" style={{ opacity: 0.4 }} />
        <div className="text-center">
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
            {s.notFoundTitle}
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            {s.notFoundDesc}
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => router.push('/assistants')}>
          <Icon name={navIcon(lang, 'back')} size={16} />
          {s.backToAssistants}
        </button>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: '40rem', margin: '0 auto', padding: '1rem 0' }}>
      {/* Back button */}
      <button
        className="btn btn-ghost btn-sm"
        onClick={() => router.push('/assistants')}
        style={{ marginBottom: '1rem', fontSize: '0.8125rem' }}
      >
        <Icon name={navIcon(lang, 'back')} size={14} />
        {s.backToAssistants}
      </button>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
        <div
          style={{
            width: '2.5rem',
            height: '2.5rem',
            borderRadius: 'var(--radius-md)',
            background: 'var(--accent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Icon name={(assistant.icon as IconName) || 'sparkles'} size={20} className="text-white" />
        </div>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.4 }}>
            {isOwner ? s.editTitle : assistant.name}
          </h1>
          {!isOwner && (
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {s.createdOn(f.date(assistant.created_at))}
            </p>
          )}
        </div>
      </div>

      {/* Start chat button for non-owners or quick access */}
      {!isOwner && (
        <button
          className="btn btn-primary"
          onClick={() => router.push(`/chat?assistant=${assistant.id}`)}
          style={{ marginBottom: '1.5rem', marginTop: '1rem' }}
        >
          <Icon name="chat" size={16} />
          {s.startChat}
        </button>
      )}

      {/* Edit form (only for owner) */}
      {isOwner && (
        <form onSubmit={handleUpdate}>
          <div
            style={{
              background: 'var(--bg-surface)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border)',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
              marginTop: '1rem',
            }}
          >
            {/* Name */}
            <div>
              <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
                {s.nameLabel} <span className="text-danger">*</span>
              </label>
              <input
                type="text"
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={s.namePlaceholder}
                style={{ width: '100%', fontSize: '0.875rem' }}
                maxLength={100}
              />
            </div>

            {/* Description */}
            <div>
              <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
                {s.descriptionLabel}
              </label>
              <input
                type="text"
                className="input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={s.descriptionPlaceholder}
                style={{ width: '100%', fontSize: '0.875rem' }}
                maxLength={500}
              />
            </div>

            {/* System Prompt — free-form, user-authored content; kept rtl
                regardless of panel language, same as the skills prompt
                template field. */}
            <div>
              <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
                {s.systemPromptLabel} <span className="text-danger">*</span>
              </label>
              <textarea dir="rtl"
                className="input"
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                placeholder={s.systemPromptPlaceholder}
                style={{ width: '100%', fontSize: '0.875rem', minHeight: '10rem', resize: 'vertical' }}
                rows={6}
              />
              <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                {s.systemPromptHint}
              </p>
            </div>

            {/* Model */}
            <div>
              <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
                {s.defaultModelLabel}
              </label>
              {modelsLoading ? (
                <div className="skeleton" style={{ width: '100%', height: '2.5rem', borderRadius: 'var(--radius-md)' }} />
              ) : (
                <div className="model-select-wrapper" dir="ltr">
                  <select
                    className="input"
                    value={modelId}
                    onChange={(e) => setModelId(e.target.value)}
                    style={{ width: '100%', fontSize: '0.875rem' }}
                  >
                    <option value="">{s.noDefaultModelOption}</option>
                    {models.map((m) => (
                      <option key={m.id} value={m.providerModelId || m.id}>
                        {m.displayName} ({PRICE_BAND_LABEL[priceBand(m, models)]})
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Public toggle */}
            <div className="flex items-center gap-3">
              <label className="smart-mode-toggle" title={isPublic ? s.publicLabel : s.privateLabel}>
                <input
                  type="checkbox"
                  checked={isPublic}
                  onChange={() => setIsPublic(!isPublic)}
                  className="sr-only"
                />
                <span className={`smart-mode-switch ${isPublic ? 'smart-mode-on' : ''}`}>
                  <span className="smart-mode-knob" />
                </span>
              </label>
              <div>
                <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {isPublic ? s.publicLabel : s.privateLabel}
                </span>
                <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                  {isPublic ? s.publicHintOn : s.publicHintOff}
                </p>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.25rem', justifyContent: 'space-between' }}>
            <button
              type="button"
              className="btn btn-ghost text-[var(--danger)]"
              onClick={handleDelete}
              disabled={deleting}
              style={{ fontSize: '0.8125rem' }}
            >
              {deleting ? (
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                  <span className="animate-spin" style={{ width: '0.875rem', height: '0.875rem', border: '2px solid var(--border)', borderTopColor: 'var(--danger)', borderRadius: '50%', display: 'inline-block' }} />
                  {s.deletingText}
                </span>
              ) : confirmDelete ? (
                <>
                  <Icon name="trash" size={14} />
                  {s.confirmDeleteAction}
                </>
              ) : (
                <>
                  <Icon name="trash" size={14} />
                  {s.deleteAction}
                </>
              )}
            </button>

            <div className="flex gap-3">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => router.push(`/chat?assistant=${assistant.id}`)}
              >
                <Icon name="chat" size={16} />
                {s.startChat}
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={submitting}
              >
                {submitting ? (
                  <span className="flex items-center gap-2">
                    <span className="animate-spin" style={{ width: '1rem', height: '1rem', border: '2px solid var(--border)', borderTopColor: 'currentColor', borderRadius: '50%', display: 'inline-block' }} />
                    {s.savingText}
                  </span>
                ) : (
                  <>
                    <Icon name="check" size={16} />
                    {s.saveChangesAction}
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      )}
    </div>
  )
}
