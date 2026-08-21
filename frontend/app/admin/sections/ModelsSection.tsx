'use client'

import dynamic from 'next/dynamic'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { SectionHeader } from './shared'

const ModelsTab = dynamic(() => import('../components/ModelsTab'), { ssr: false })

/* ═══════════════════════════════════════════════════════════════════════════
   Models — moved verbatim out of AdminPanel.tsx (page === 'models'): the org
   default-model card, plus the already-extracted <ModelsTab />. All state and
   handlers for the default-model card still live in AdminPanel; this
   component is purely presentational.
   ═══════════════════════════════════════════════════════════════════════════ */

interface ModelsSectionProps {
  models: string[]
  orgDefaultModel: string
  setOrgDefaultModel: (v: string) => void
  orgDefaultSaving: boolean
  saveOrgDefaultModel: () => void
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

export default function ModelsSection({ models, orgDefaultModel, setOrgDefaultModel, orgDefaultSaving, saveOrgDefaultModel, api }: ModelsSectionProps) {
  return (
    <div className="space-y-6">
      <SectionHeader title="مدل‌های فعال" subtitle={`${faNum(models.length)} مدل در دسترس`} />

      {/* Org Default Model */}
      <div className="admin-card">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--accent-dim)' }}>
            <Icon name="models" size={16} className="text-accent" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-primary">مدل پیشفرض سازمان</h3>
            <p className="text-xs text-muted">مدلی که کاربران جدید به‌صورت پیشفرض استفاده می‌کنند</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <select
            className="input flex-1"
            value={orgDefaultModel}
            onChange={(e) => setOrgDefaultModel(e.target.value)}
          >
            <option value="">بدون مدل پیشفرض (اولین مدل لیست)</option>
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <button className="btn" onClick={saveOrgDefaultModel} disabled={orgDefaultSaving}>
            {orgDefaultSaving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : 'ذخیره'}
          </button>
        </div>
      </div>

      <ModelsTab api={api} />
    </div>
  )
}
