'use client'

import { useState } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { CATEGORIES } from '../types'

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
      toast('لطفاً فیلدهای ضروری را پر کنید', 'error')
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
        toast('اسکیل با موفقیت ایجاد شد', 'success')
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
        toast('خطا در ایجاد اسکیل', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
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
            ایجاد اسکیل جدید
          </h2>
          <button onClick={onClose} className="btn btn-ghost btn-icon" aria-label="بستن">
            <Icon name="close" size={18} />
          </button>
        </div>

        {/* Title */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            عنوان *
          </label>
          <input
            type="text"
            className="input"
            value={titleFa}
            onChange={(e) => setTitleFa(e.target.value)}
            placeholder="عنوان اسکیل را وارد کنید"
            style={{ width: '100%', fontSize: '0.875rem' }}
          />
        </div>

        {/* Description */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            توضیحات
          </label>
          <textarea dir="rtl"
            className="input"
            value={descriptionFa}
            onChange={(e) => setDescriptionFa(e.target.value)}
            placeholder="توضیحات اسکیل را وارد کنید"
            rows={3}
            style={{ width: '100%', fontSize: '0.875rem', resize: 'vertical' }}
          />
        </div>

        {/* Category */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            دسته‌بندی
          </label>
          <select
            className="input"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ width: '100%', fontSize: '0.875rem' }}
          >
            {CATEGORIES.filter((c) => c.key !== 'all').map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        {/* Prompt Template */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            الگوی پرامپت *
          </label>
          <textarea dir="rtl"
            className="input"
            value={promptTemplate}
            onChange={(e) => setPromptTemplate(e.target.value)}
            placeholder="الگوی پرامپت را وارد کنید. از {{variable_name}} برای متغیرها استفاده کنید."
            rows={5}
            style={{ width: '100%', fontSize: '0.875rem', resize: 'vertical', fontFamily: 'var(--font-mono, monospace)' }}
          />
        </div>

        {/* Variables */}
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <label style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              متغیرها
            </label>
            <button
              className="btn btn-ghost btn-sm"
              onClick={addVariable}
              style={{ fontSize: '0.75rem', padding: '0.125rem 0.5rem' }}
            >
              <Icon name="plus" size={12} />
              افزودن
            </button>
          </div>
          {variables.map((v, i) => (
            <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
              <input
                type="text"
                className="input"
                value={v.name}
                onChange={(e) => updateVariable(i, 'name', e.target.value)}
                placeholder="نام متغیر"
                style={{ flex: 1, fontSize: '0.8125rem' }}
              />
              <input
                type="text"
                className="input"
                value={v.description}
                onChange={(e) => updateVariable(i, 'description', e.target.value)}
                placeholder="توضیحات"
                style={{ flex: 2, fontSize: '0.8125rem' }}
              />
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => removeVariable(i)}
                style={{ color: 'var(--danger)', padding: '0.25rem' }}
                aria-label="حذف متغیر"
              >
                <Icon name="trash" size={14} />
              </button>
            </div>
          ))}
        </div>

        {/* Default Model */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            مدل پیش‌فرض
          </label>
          <input
            type="text"
            className="input"
            value={defaultModel}
            onChange={(e) => setDefaultModel(e.target.value)}
            placeholder="نام مدل (اختیاری)"
            style={{ width: '100%', fontSize: '0.875rem' }}
          />
        </div>

        {/* Tags */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            برچسب‌ها (با کاما جدا کنید)
          </label>
          <input
            type="text"
            className="input"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="برچسب۱, برچسب۲, ..."
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
            aria-label={isPublic ? 'عمومی' : 'خصوصی'}
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
            {isPublic ? 'عمومی — برای همه قابل مشاهده' : 'خصوصی — فقط برای شما'}
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
              در حال ذخیره...
            </span>
          ) : (
            <>
              <Icon name="check" size={16} />
              ذخیره
            </>
          )}
        </button>
      </div>
    </div>
  )
}
