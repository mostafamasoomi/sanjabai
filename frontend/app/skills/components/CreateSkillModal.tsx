'use client'

import { useState } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { CATEGORY_KEYS, categoryLabel } from '../types'
import { createSkillModalStrings } from './CreateSkillModal.strings'

/* ═══════════════════════════════════════════════════════════════
   Create Skill Modal
   ═══════════════════════════════════════════════════════════════ */

export default function CreateSkillModal({
  open,
  onClose,
  token,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  token: string | null
  onCreated: () => void
}) {
  const lang = useLang()
  const s = createSkillModalStrings(lang)

  const [titleFa, setTitleFa] = useState('')
  const [descriptionFa, setDescriptionFa] = useState('')
  const [category, setCategory] = useState('writing')
  const [promptTemplate, setPromptTemplate] = useState('')
  const [variables, setVariables] = useState<{ name: string; description: string }[]>([])
  const [defaultModel, setDefaultModel] = useState('')
  const [isPublic, setIsPublic] = useState(true)
  const [tagsInput, setTagsInput] = useState('')
  const [loading, setLoading] = useState(false)

  const addVariable = () => {
    setVariables([...variables, { name: '', description: '' }])
  }

  const removeVariable = (index: number) => {
    setVariables(variables.filter((_, i) => i !== index))
  }

  const updateVariable = (index: number, field: 'name' | 'description', value: string) => {
    const updated = [...variables]
    updated[index][field] = value
    setVariables(updated)
  }

  const handleSubmit = async () => {
    if (!token || !titleFa.trim() || !promptTemplate.trim()) {
      toast(s.requiredFieldsToast, 'error')
      return
    }

    setLoading(true)
    try {
      const body = {
        title: titleFa,
        title_fa: titleFa,
        description: descriptionFa,
        description_fa: descriptionFa,
        category,
        prompt_template: promptTemplate,
        variables: variables.filter((v) => v.name.trim()),
        default_model: defaultModel,
        is_public: isPublic,
        tags: tagsInput
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      }

      const res = await apiFetch('/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      })

      if (res.ok) {
        toast(s.createdToast, 'success')
        onCreated()
        onClose()
        // Reset form
        setTitleFa('')
        setDescriptionFa('')
        setCategory('writing')
        setPromptTemplate('')
        setVariables([])
        setDefaultModel('')
        setIsPublic(true)
        setTagsInput('')
      } else {
        toast(s.createErrorToast, 'error')
      }
    } catch {
      toast(s.serverErrorToast, 'error')
    } finally {
      setLoading(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-[var(--bg-elevated)] border border-[var(--border-strong)] rounded-[var(--radius-xl)] p-6 max-w-lg w-full shadow-xl fade-in overflow-y-auto max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {s.modalTitle}
          </h2>
          <button onClick={onClose} className="btn btn-ghost btn-icon" aria-label={s.closeAria}>
            <Icon name="close" size={18} />
          </button>
        </div>

        {/* Title */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            {s.titleLabel}
          </label>
          <input
            type="text"
            className="input"
            value={titleFa}
            onChange={(e) => setTitleFa(e.target.value)}
            placeholder={s.titlePlaceholder}
            style={{ width: '100%', fontSize: '0.875rem' }}
          />
        </div>

        {/* Description — always Persian content (title_fa/description_fa are
            dedicated Persian fields in the data model), so the input keeps
            its own rtl direction regardless of the panel's language. */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            {s.descriptionLabel}
          </label>
          <textarea dir="rtl"
            className="input"
            value={descriptionFa}
            onChange={(e) => setDescriptionFa(e.target.value)}
            placeholder={s.descriptionPlaceholder}
            rows={3}
            style={{ width: '100%', fontSize: '0.875rem', resize: 'vertical' }}
          />
        </div>

        {/* Category */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            {s.categoryLabel}
          </label>
          <select
            className="input"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ width: '100%', fontSize: '0.875rem' }}
          >
            {CATEGORY_KEYS.filter((c) => c !== 'all').map((c) => (
              <option key={c} value={c}>
                {categoryLabel(c, lang)}
              </option>
            ))}
          </select>
        </div>

        {/* Prompt Template — the executable template body, same "content,
            not chrome" rule as the prompt library: kept rtl regardless of
            panel language. */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            {s.promptLabel}
          </label>
          <textarea dir="rtl"
            className="input"
            value={promptTemplate}
            onChange={(e) => setPromptTemplate(e.target.value)}
            placeholder={s.promptPlaceholder}
            rows={5}
            style={{ width: '100%', fontSize: '0.875rem', resize: 'vertical', fontFamily: 'var(--font-mono, monospace)' }}
          />
        </div>

        {/* Variables */}
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <label style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {s.variablesLabel}
            </label>
            <button
              className="btn btn-ghost btn-sm"
              onClick={addVariable}
              style={{ fontSize: '0.75rem', padding: '0.125rem 0.5rem' }}
            >
              <Icon name="plus" size={12} />
              {s.addAction}
            </button>
          </div>
          {variables.map((v, i) => (
            <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
              <input
                type="text"
                className="input"
                value={v.name}
                onChange={(e) => updateVariable(i, 'name', e.target.value)}
                placeholder={s.variableNamePlaceholder}
                style={{ flex: 1, fontSize: '0.8125rem' }}
              />
              <input
                type="text"
                className="input"
                value={v.description}
                onChange={(e) => updateVariable(i, 'description', e.target.value)}
                placeholder={s.variableDescPlaceholder}
                style={{ flex: 2, fontSize: '0.8125rem' }}
              />
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => removeVariable(i)}
                style={{ color: 'var(--danger)', padding: '0.25rem' }}
                aria-label={s.removeVariableAria}
              >
                <Icon name="trash" size={14} />
              </button>
            </div>
          ))}
        </div>

        {/* Default Model */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            {s.defaultModelLabel}
          </label>
          <input
            type="text"
            className="input"
            value={defaultModel}
            onChange={(e) => setDefaultModel(e.target.value)}
            placeholder={s.defaultModelPlaceholder}
            style={{ width: '100%', fontSize: '0.875rem' }}
          />
        </div>

        {/* Tags */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            {s.tagsLabel}
          </label>
          <input
            type="text"
            className="input"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder={s.tagsPlaceholder}
            style={{ width: '100%', fontSize: '0.875rem' }}
          />
        </div>

        {/* Public toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <button
            onClick={() => setIsPublic(!isPublic)}
            style={{
              width: '2.5rem',
              height: '1.375rem',
              borderRadius: 'var(--radius-full)',
              background: isPublic ? 'var(--accent)' : 'var(--bg-surface)',
              border: `1.5px solid ${isPublic ? 'var(--accent)' : 'var(--border)'}`,
              cursor: 'pointer',
              position: 'relative',
              transition: 'all 0.2s ease',
              padding: 0,
            }}
            aria-label={s.publicAria(isPublic)}
          >
            <span
              style={{
                position: 'absolute',
                top: '1.5px',
                right: isPublic ? 'auto' : '1.5px',
                left: isPublic ? '1.5px' : 'auto',
                width: '1rem',
                height: '1rem',
                borderRadius: '50%',
                background: 'white',
                transition: 'all 0.2s ease',
              }}
            />
          </button>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
            {s.publicHint(isPublic)}
          </span>
        </div>

        {/* Submit */}
        <button
          className="btn btn-primary w-full"
          onClick={handleSubmit}
          disabled={loading || !titleFa.trim() || !promptTemplate.trim()}
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin" style={{ width: '1rem', height: '1rem', border: '2px solid var(--border)', borderTopColor: 'var(--accent)', borderRadius: '50%', display: 'inline-block' }} />
              {s.savingText}
            </span>
          ) : (
            <>
              <Icon name="check" size={16} />
              {s.saveAction}
            </>
          )}
        </button>
      </div>
    </div>
  )
}
