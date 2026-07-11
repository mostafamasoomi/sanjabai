'use client'

import { useState, useEffect } from 'react'
import { Icon } from '@/components/ui/Icon'

type ModelInfo = {
  id: string
  name: string
  provider: string
  tier: string
  description: string
  caps: string[]
  context: number
}

const MODELS: ModelInfo[] = [
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI', tier: 'flagship', description: 'مدل چندوجهی پرچمدار OpenAI — بهترین برای وظایف پیچیده، کدنویسی و تحلیل', caps: ['چت', 'کدنویسی', 'تحلیل', 'تصویر'], context: 128000 },
  { id: 'claude-3.5-sonnet', name: 'Claude 3.5 Sonnet', provider: 'Anthropic', tier: 'flagship', description: 'مدل متعادل با استدلال قوی و خروجی طبیعی — عالی برای نوشتن و تحلیل', caps: ['چت', 'کدنویسی', 'نوشتن', 'تحلیل'], context: 200000 },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'Google', tier: 'flagship', description: 'مدل قدرتمند گوگل با پنجره زمینه بزرگ — مناسب برای اسناد طولانی', caps: ['چت', 'کدنویسی', 'تحلیل', 'چندرسانه‌ای'], context: 1000000 },
  { id: 'deepseek-v3', name: 'DeepSeek V3', provider: 'DeepSeek', tier: 'mid', description: 'مدل متن‌باز قدرتمند با قیمت اقتصادی — گزینه عالی برای استفاده روزمره', caps: ['چت', 'کدنویسی', 'تحلیل'], context: 64000 },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini', provider: 'OpenAI', tier: 'mini', description: 'مدل کوچک و سریع — مناسب برای کارهای ساده و روزمره', caps: ['چت', 'کدنویسی'], context: 128000 },
  { id: 'claude-opus-4', name: 'Claude Opus 4', provider: 'Anthropic', tier: 'flagship', description: 'قوی‌ترین مدل Anthropic — برای پیچیده‌ترین وظایف تحلیلی', caps: ['چت', 'کدنویسی', 'نوشتن', 'تحلیل', 'تصویر'], context: 200000 },
  { id: 'llama-3.1-405b', name: 'Llama 3.1 405B', provider: 'Meta', tier: 'mid', description: 'بزرگ‌ترین مدل متن‌باز — عملکرد عالی در وظایف عمومی', caps: ['چت', 'کدنویسی', 'تحلیل'], context: 128000 },
  { id: 'bynara-auto', name: 'Bynara Auto', provider: 'Bynara', tier: 'mid', description: 'مسیریابی خودکار به بهترین مدل — انتخاب هوشمند براساس نیاز', caps: ['چت', 'کدنویسی', 'همه‌کاره'], context: 128000 },
]

export default function ModelsPage() {
  const [filter, setFilter] = useState('all')

  const tiers: Record<string, { label: string; color: string }> = {
    flagship: { label: 'پرچمدار', color: 'badge-accent' },
    mid: { label: 'متوسط', color: 'badge-positive' },
    mini: { label: 'اقتصادی', color: 'badge-warning' },
  }

  const filtered = filter === 'all' ? MODELS : MODELS.filter(m => m.tier === filter)

  return (
    <div className="py-6">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-2">مدل‌های هوش مصنوعی</h1>
        <p className="text-[var(--text-secondary)]">همه مدل‌ها از یک پنل — بهترین مدل را برای نیاز خود انتخاب کنید</p>
      </div>

      <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
        {[
          { key: 'all', label: 'همه' },
          { key: 'flagship', label: 'پرچمدار' },
          { key: 'mid', label: 'متوسط' },
          { key: 'mini', label: 'اقتصادی' },
        ].map(f => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`btn btn-sm ${filter === f.key ? 'btn-primary' : 'btn-ghost'}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filtered.map(m => (
          <div key={m.id} className="card card-interactive">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-bold text-base">{m.name}</h3>
                <p className="text-xs text-[var(--text-muted)]">{m.provider}</p>
              </div>
              <span className={`badge ${tiers[m.tier]?.color || 'badge-accent'}`}>
                {tiers[m.tier]?.label || m.tier}
              </span>
            </div>

            <p className="text-sm text-[var(--text-secondary)] mb-3 leading-relaxed">{m.description}</p>

            <div className="flex items-center gap-4 text-xs text-[var(--text-muted)] mb-3">
              <span className="flex items-center gap-1">
                <Icon name="models" size={12} />
                {m.context.toLocaleString()} token
              </span>
            </div>

            <div className="flex flex-wrap gap-1.5 mb-4">
              {m.caps.map(c => (
                <span key={c} className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--bg-hover)] text-[var(--text-secondary)]">
                  {c}
                </span>
              ))}
            </div>

            <a href={`/chat?model=${m.id}`} className="btn btn-primary btn-sm w-full">
              <Icon name="chat" size={14} />
              شروع چت با {m.name}
            </a>
          </div>
        ))}
      </div>
    </div>
  )
}