'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Create Assistant Page
   ═══════════════════════════════════════════════════════════════ */

export default function CreateAssistantPage() {
  const { token, user, loading: authLoading } = useAuth()
  const { models, loading: modelsLoading } = useCatalog()
  const router = useRouter()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [modelId, setModelId] = useState('')
  const [isPublic, setIsPublic] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace('/login')
    }
  }, [authLoading, user, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token) return
    if (!name.trim()) {
      toast('نام دستیار الزامی است', 'error')
      return
    }
    if (!systemPrompt.trim()) {
      toast('پرامپت سیستم الزامی است', 'error')
      return
    }

    setSubmitting(true)
    try {
      const res = await fetch('/api/assistants', {
        method: 'POST',
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
        toast('دستیار با موفقیت ساخته شد', 'success')
        router.push('/assistants')
      } else {
        const data = await res.json()
        toast(data.detail || 'خطا در ساخت دستیار', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (authLoading) {
    return (
      <div style={{ maxWidth: '40rem', margin: '0 auto', padding: '1rem 0' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="skeleton" style={{ width: '10rem', height: '1.5rem' }} />
          <div className="skeleton" style={{ width: '100%', height: '2.5rem', borderRadius: 'var(--radius-md)' }} />
          <div className="skeleton" style={{ width: '100%', height: '2.5rem', borderRadius: 'var(--radius-md)' }} />
          <div className="skeleton" style={{ width: '100%', height: '10rem', borderRadius: 'var(--radius-md)' }} />
        </div>
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
        <Icon name="arrowLeft" size={14} />
        بازگشت به دستیارها
      </button>

      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
        ساخت دستیار جدید
      </h1>
      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
        یک دستیار هوشمند با پرامپت سیستم سفارشی بسازید
      </p>

      <form onSubmit={handleSubmit}>
        <div
          style={{
            background: 'var(--bg-surface)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
          }}
        >
          {/* Name */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
              نام دستیار <span className="text-danger">*</span>
            </label>
            <input
              type="text"
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="مثال: دستیار برنامه‌نویسی"
              style={{ width: '100%', fontSize: '0.875rem' }}
              maxLength={100}
            />
          </div>

          {/* Description */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
              توضیحات
            </label>
            <input
              type="text"
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="توضیح کوتاه درباره دستیار"
              style={{ width: '100%', fontSize: '0.875rem' }}
              maxLength={500}
            />
          </div>

          {/* System Prompt */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
              پرامپت سیستم <span className="text-danger">*</span>
            </label>
            <textarea dir="rtl"
              className="input"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="تو یک دستیار متخصص در... هستی. وظیفه تو..."
              style={{ width: '100%', fontSize: '0.875rem', minHeight: '10rem', resize: 'vertical' }}
              rows={6}
            />
            <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              این پرامپت در ابتدای هر مکالمه به مدل ارسال می‌شود
            </p>
          </div>

          {/* Model */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
              مدل پیش‌فرض
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
                  <option value="">بدون مدل پیش‌فرض (استفاده از مدل انتخابی کاربر)</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.providerModelId || m.id}>
                      {m.displayName} ({m.provider})
                    </option>
                  ))}
                </select>
              </div>
            )}
            <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              در صورت انتخاب، هنگام شروع گفتگو با این دستیار، این مدل استفاده می‌شود
            </p>
          </div>

          {/* Public toggle */}
          <div className="flex items-center gap-3">
            <label className="smart-mode-toggle" title={isPublic ? 'عمومی' : 'خصوصی'}>
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
                {isPublic ? 'عمومی' : 'خصوصی'}
              </span>
              <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                {isPublic ? 'همه کاربران می‌توانند از این دستیار استفاده کنند' : 'فقط شما به این دستیار دسترسی دارید'}
              </p>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.25rem', justifyContent: 'flex-end' }}>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => router.push('/assistants')}
            disabled={submitting}
          >
            انصراف
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting}
          >
            {submitting ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin" style={{ width: '1rem', height: '1rem', border: '2px solid var(--border)', borderTopColor: 'currentColor', borderRadius: '50%', display: 'inline-block' }} />
                در حال ساخت...
              </span>
            ) : (
              <>
                <Icon name="plus" size={16} />
                ساخت دستیار
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
