'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { toast } from '@/components/ui'

const PROMPT_TEMPLATES = [
  { label: '💡 خلاقانه', prompt: 'یک ایده استارتاپ جدید در حوزه هوش مصنوعی پیشنهاد بده. مزایا، بازار هدف و مدل درآمدی را توضیح بده.' },
  { label: '📝 محتوا', prompt: 'یک پست وبلاگ ۳۰۰ کلمه‌ای درباره آینده هوش مصنوعی در ایران بنویس.' },
  { label: '💻 کد', prompt: 'یک تابع Python بنویس که یک لیست از اعداد را گرفته و آمار توصیفی (میانگین، میانه، انحراف معیار) را برگرداند.' },
  { label: '📊 تحلیل', prompt: 'مزایا و معایب استفاده از Next.js در مقابل React خالص را تحلیل کن.' },
  { label: '🌐 ترجمه', prompt: 'متن زیر را به انگلیسی روان ترجمه کن: "هوش مصنوعی در حال تغییر شیوه زندگی ماست."' },
  { label: '🎯 خلاصه', prompt: 'مفهوم Transformer architecture در یادگیری عمیق را در ۳ جمله توضیح بده.' },
]

export default function PlaygroundPage() {
  const { user } = useAuth()
  const { models, loading: modelsLoading } = useCatalog()
  const [selectedModel, setSelectedModel] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [userPrompt, setUserPrompt] = useState('')
  const [response, setResponse] = useState('')
  const [loading, setLoading] = useState(false)
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(1024)

  // Select the first catalog model once the live catalog is available.
  useEffect(() => {
    if (!selectedModel && models.length > 0) setSelectedModel(models[0].id)
  }, [models, selectedModel])

  const handleSubmit = async () => {
    if (!userPrompt.trim()) return
    setLoading(true)
    setResponse('')
    try {
      const token = localStorage.getItem('auth_token')
      const messages: any[] = []
      if (systemPrompt.trim()) messages.push({ role: 'system', content: systemPrompt })
      messages.push({ role: 'user', content: userPrompt })

      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          model: selectedModel,
          messages,
          temperature,
          max_tokens: maxTokens,
        }),
      })
      const data = await r.json()
      if (r.ok) {
        setResponse(data.choices?.[0]?.message?.content || 'پاسخی دریافت نشد')
      } else {
        toast(data.detail || 'خطا', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold">🎮 Playground</h1>
      <p className="text-sm text-[var(--text-dim)]">مدل‌ها را تست کنید و بهترین prompt را پیدا کنید.</p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left panel - settings */}
        <div className="space-y-4">
          {/* Model selector */}
          <div className="card">
            <h3 className="font-bold text-sm mb-3">🧠 مدل</h3>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="input"
            >
              {modelsLoading && <option value="" disabled>در حال بارگذاری...</option>}
              {models.slice(0, 30).map(m => (
                <option key={m.id} value={m.id}>{m.displayName}</option>
              ))}
            </select>
          </div>

          {/* Parameters */}
          <div className="card space-y-3">
            <h3 className="font-bold text-sm">⚙️ پارامترها</h3>
            <div>
              <label className="text-xs text-[var(--text-muted)]">Temperature: {temperature}</label>
              <input
                type="range" min="0" max="2" step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-[var(--accent)]"
              />
            </div>
            <div>
              <label className="text-xs text-[var(--text-muted)]">Max Tokens: {maxTokens}</label>
              <input
                type="range" min="64" max="4096" step="64"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                className="w-full accent-[var(--accent)]"
              />
            </div>
          </div>

          {/* Templates */}
          <div className="card">
            <h3 className="font-bold text-sm mb-3">📋 پرامپت‌های آماده</h3>
            <div className="space-y-1.5">
              {PROMPT_TEMPLATES.map(t => (
                <button
                  key={t.label}
                  onClick={() => setUserPrompt(t.prompt)}
                  className="w-full text-right text-xs p-2 rounded-lg hover:bg-[var(--bg-hover)] transition-colors"
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right panel - prompt & response */}
        <div className="lg:col-span-2 space-y-4">
          {/* System prompt */}
          <div className="card">
            <h3 className="font-bold text-sm mb-2">System Prompt</h3>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="اختیاری — نقش و رفتار مدل را تعریف کنید"
              className="input min-h-[60px] resize-none"
              rows={2}
            />
          </div>

          {/* User prompt */}
          <div className="card">
            <h3 className="font-bold text-sm mb-2">User Prompt</h3>
            <textarea
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              placeholder="پرامپت خود را بنویسید..."
              className="input min-h-[100px] resize-none"
              rows={4}
            />
            <button
              onClick={handleSubmit}
              disabled={loading || !userPrompt.trim()}
              className="btn btn-primary mt-3"
            >
              {loading ? '⏳ در حال پردازش...' : '🚀 اجرا'}
            </button>
          </div>

          {/* Response */}
          {response && (
            <div className="card border-[var(--accent)]/20">
              <h3 className="font-bold text-sm mb-3 text-[var(--accent)]">✨ پاسخ</h3>
              <div className="text-sm leading-relaxed whitespace-pre-wrap">{response}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}