'use client'

import { Icon } from '@/components/ui/Icon'
import { SectionHeader, Field } from './shared'
import type { ProxyConfig } from '../AdminPanel'

/* ═══════════════════════════════════════════════════════════════════════════
   Proxy — moved verbatim out of AdminPanel.tsx (page === 'proxy').
   All state and handlers still live in AdminPanel; this component is purely
   presentational.
   ═══════════════════════════════════════════════════════════════════════════ */

interface ProxySectionProps {
  proxyConfig: ProxyConfig
  pxType: string
  setPxType: (v: string) => void
  pxUrl: string
  setPxUrl: (v: string) => void
  pxActive: boolean
  setPxActive: (v: boolean) => void
  saveProxy: () => void
}

export default function ProxySection({ proxyConfig, pxType, setPxType, pxUrl, setPxUrl, pxActive, setPxActive, saveProxy }: ProxySectionProps) {
  return (
    <div className="space-y-6">
      <SectionHeader title="تنظیمات پروکسی" subtitle="مدیریت تونل و پروکسی اتصال" />

      <div className="admin-card">
        <div className="flex items-center gap-3 mb-4 p-3 rounded-lg" style={{ background: proxyConfig.active ? 'var(--positive)' + '15' : 'var(--warning)' + '15' }}>
          <Icon name={proxyConfig.active ? 'check' : 'notification'} size={18} style={{ color: proxyConfig.active ? 'var(--positive)' : 'var(--warning)' }} />
          <span className="text-sm font-medium" style={{ color: proxyConfig.active ? 'var(--positive)' : 'var(--warning)' }}>
            {proxyConfig.active ? 'تونل فعال است' : 'تونل غیرفعال است'}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Field label="نوع پروکسی">
            <select className="input w-full" value={pxType} onChange={(e) => setPxType(e.target.value)}>
              <option value="socks5">SOCKS5</option>
              <option value="http">HTTP</option>
            </select>
          </Field>
          <Field label="آدرس پروکسی">
            <input className="input w-full" value={pxUrl} onChange={(e) => setPxUrl(e.target.value)} placeholder="socks5://user:pass@host:port" />
          </Field>
          <Field label="وضعیت">
            <select className="input w-full" value={String(pxActive)} onChange={(e) => setPxActive(e.target.value === 'true')}>
              <option value="true">فعال</option>
              <option value="false">غیرفعال</option>
            </select>
          </Field>
        </div>
        <button className="btn mt-4" onClick={saveProxy}>
          <Icon name="check" size={16} />
          <span>ذخیره و اعمال</span>
        </button>
      </div>
    </div>
  )
}
