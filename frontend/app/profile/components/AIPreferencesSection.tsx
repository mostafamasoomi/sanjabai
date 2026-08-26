'use client'

import { useRef } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { aiPreferencesSectionStrings } from './AIPreferencesSection.strings'

type AIPreferencesSectionProps = {
  defaultModel: string
  setDefaultModel: (v: string) => void
  models: string[]
  modelsError: boolean
  fetchModels: () => void
  aiPersonality: string
  setAiPersonality: (v: string) => void
  pinnedContext: string
  setPinnedContext: (v: string) => void
  handlePinnedContextFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void
}

export default function AIPreferencesSection({
  defaultModel, setDefaultModel, models, modelsError, fetchModels,
  aiPersonality, setAiPersonality, pinnedContext, setPinnedContext, handlePinnedContextFileUpload,
}: AIPreferencesSectionProps) {
  const lang = useLang()
  const s = aiPreferencesSectionStrings(lang)
  const f = fmt(lang)
  const dir = lang === 'fa' ? 'rtl' : 'ltr'
  const mdFileInputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="cpu" size={16} className="text-accent" />
        <h2 className="card-title">
          {s.title}
        </h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Default Model */}
        <div className="profile-input-group">
          <label className="profile-input-label">{s.defaultModel}</label>
          <select
            value={defaultModel}
            onChange={(e) => setDefaultModel(e.target.value)}
            className="input"
            style={{ appearance: 'auto' }}
          >
            <option value="">{s.selectModel}</option>
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          {modelsError ? (
            <p style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Icon name="warning" size={12} />
              {s.modelsLoadError}
              <button
                type="button"
                onClick={fetchModels}
                style={{ background: 'transparent', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: 11 }}
              >
                {s.retry}
              </button>
            </p>
          ) : (
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              {s.defaultModelHint}
            </p>
          )}
        </div>

        {/* AI Personality */}
        <div className="profile-input-group">
          <label className="profile-input-label">
            {s.personality}
          </label>
          <textarea dir={dir}
            value={aiPersonality}
            onChange={(e) => setAiPersonality(e.target.value)}
            placeholder={s.personalityPlaceholder}
            className="input"
            rows={4}
            style={{ resize: 'vertical', minHeight: 100 }}
          />
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            {s.personalityHint}
          </p>
        </div>

        {/* Pinned Context (persistent note / .md upload) */}
        <div className="profile-input-group">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
            <label className="profile-input-label" style={{ marginBottom: 0 }}>
              {s.pinnedContext}
            </label>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => mdFileInputRef.current?.click()}
            >
              <Icon name="paperclip" size={14} />
              <span>{s.uploadMd}</span>
            </button>
            <input
              ref={mdFileInputRef}
              type="file"
              accept=".md,.markdown,.txt,text/markdown,text/plain"
              style={{ display: 'none' }}
              onChange={handlePinnedContextFileUpload}
            />
          </div>
          <textarea dir={dir}
            value={pinnedContext}
            onChange={(e) => setPinnedContext(e.target.value)}
            placeholder={s.pinnedContextPlaceholder}
            className="input"
            rows={8}
            maxLength={20000}
            style={{ resize: 'vertical', minHeight: 160, fontFamily: 'monospace', fontSize: 13 }}
          />
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            {s.pinnedContextHint(f.num(pinnedContext.length))}
          </p>
        </div>
      </div>
    </div>
  )
}
