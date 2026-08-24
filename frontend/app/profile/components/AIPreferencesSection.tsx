'use client'

import { useRef } from 'react'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'

type AIPreferencesSectionProps = {
  isFa: boolean
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
  isFa, defaultModel, setDefaultModel, models, modelsError, fetchModels,
  aiPersonality, setAiPersonality, pinnedContext, setPinnedContext, handlePinnedContextFileUpload,
}: AIPreferencesSectionProps) {
  const mdFileInputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="card profile-section-card">
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
          {modelsError ? (
            <p style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Icon name="warning" size={12} />
              {isFa ? 'خطا در بارگذاری فهرست مدل‌ها.' : 'Failed to load the model list.'}
              <button
                type="button"
                onClick={fetchModels}
                style={{ background: 'transparent', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: 11 }}
              >
                {isFa ? 'تلاش مجدد' : 'Retry'}
              </button>
            </p>
          ) : (
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              {isFa ? 'مدل پیش‌فرض برای چت‌های جدید' : 'Default model for new chats'}
            </p>
          )}
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
              ? `این یادداشت (تا ۶۰۰۰ کاراکتر ابتدایی آن) در تمام چت‌ها و مستقل از دستیار انتخابی تزریق می‌شود. ${faNum(pinnedContext.length)} / ۲۰٬۰۰۰ کاراکتر`
              : `This note (up to its first 6000 characters) is injected into every chat regardless of the selected assistant. ${pinnedContext.length}/20,000 characters`}
          </p>
        </div>
      </div>
    </div>
  )
}
