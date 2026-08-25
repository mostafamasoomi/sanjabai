'use client'

import { Fragment } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/adminI18n'
import { Field, NumInput } from './shared'
import { isLossPath, type Draft, type PackageRow } from './PackagesTypes'
import { packagesRowStrings } from './PackagesRow.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   One editable row of the packages table (plus its "legacy fields" expander
   row), extracted from PackagesSection.tsx so that file stays under the
   500-line cap. Pure presentational component -- all state lives in the
   parent, this only renders `d`/`p` and calls back on change/save/toggle.
   ═══════════════════════════════════════════════════════════════════════════ */

interface PackagesRowProps {
  p: PackageRow
  d: Draft
  saving: boolean
  expanded: boolean
  onField: (field: keyof Draft, value: string | boolean) => void
  onSave: () => void
  onToggleExpanded: () => void
}

export default function PackagesRow({ p, d, saving, expanded, onField, onSave, onToggleExpanded }: PackagesRowProps) {
  const lang = useLang()
  const s = packagesRowStrings(lang)
  const f = fmt(lang)
  const warn = isLossPath(d)
  return (
    <Fragment>
      <tr style={warn ? { background: 'color-mix(in srgb, var(--warning, #f59e0b) 10%, transparent)' } : undefined}>
        <td className="p-3">
          <input className="input mb-1" value={d.name_fa} placeholder={s.namePlaceholderFa}
            onChange={(e) => onField('name_fa', e.target.value)} style={{ maxWidth: 160 }} />
          <input className="input" value={d.name_en} placeholder={s.namePlaceholderEn}
            onChange={(e) => onField('name_en', e.target.value)} style={{ maxWidth: 160 }} />
          <div className="text-xs font-mono text-muted mt-1">{p.id}</div>
          <button className="text-xs text-muted underline mt-1" onClick={onToggleExpanded}>
            {expanded ? s.hideLegacy : s.showLegacy}
          </button>
        </td>
        <td className="p-3">
          <input type="checkbox" checked={d.active} onChange={(e) => onField('active', e.target.checked)} />
        </td>
        <td className="p-3">
          <NumInput value={d.base_amount} onChange={(v) => onField('base_amount', v)} />
          <div className="text-xs text-muted mt-1">{f.price(p.base_amount)}</div>
        </td>
        <td className="p-3">
          <NumInput value={d.total_credits} onChange={(v) => onField('total_credits', v)} />
          <div className="text-xs text-muted mt-1">{f.price(p.total_credits)}</div>
        </td>
        <td className="p-3"><NumInput value={d.bonus_percent} onChange={(v) => onField('bonus_percent', v)} width={80} /></td>
        <td className="p-3"><NumInput value={d.request_quota} onChange={(v) => onField('request_quota', v)} placeholder={s.noQuotaPlaceholder} /></td>
        <td className="p-3"><NumInput value={d.token_quota} onChange={(v) => onField('token_quota', v)} placeholder={s.noQuotaPlaceholder} /></td>
        <td className="p-3">
          <NumInput value={d.max_cost_per_request_toman} onChange={(v) => onField('max_cost_per_request_toman', v)} placeholder={s.noCeilingPlaceholder} />
          {warn && (
            <div className="text-xs flex items-center gap-1 mt-1" style={{ color: 'var(--warning, #f59e0b)' }}>
              <Icon name="warning" size={12} />
              <span>{s.ceilingRequired}</span>
            </div>
          )}
        </td>
        <td className="p-3">
          <NumInput value={d.rate_limit_per_window} onChange={(v) => onField('rate_limit_per_window', v)} placeholder={s.noCeilingPlaceholder} />
        </td>
        <td className="p-3">
          <NumInput value={d.premium_rate_limit_per_window} onChange={(v) => onField('premium_rate_limit_per_window', v)} placeholder={s.noCeilingPlaceholder} />
        </td>
        <td className="p-3"><NumInput value={d.validity_days} onChange={(v) => onField('validity_days', v)} width={90} placeholder={s.noExpiryPlaceholder} /></td>
        <td className="p-3">
          <button className="btn btn-sm" onClick={onSave} disabled={saving} title={s.save}>
            {saving ? (
              <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : <Icon name="check" size={14} />}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={12} className="p-3" style={{ background: 'var(--bg-elevated)' }}>
            <p className="text-xs text-muted mb-2">
              {s.legacyNote}
            </p>
            <div className="flex flex-wrap gap-4">
              <Field label={s.fieldDescription}>
                <input className="input" value={d.description}
                  onChange={(e) => onField('description', e.target.value)} style={{ minWidth: 220 }} />
              </Field>
              <Field label={s.fieldPriceLegacy}>
                <NumInput value={d.price} onChange={(v) => onField('price', v)} width={110} />
              </Field>
              <Field label={s.fieldCreditsLegacy}>
                <NumInput value={d.credits} onChange={(v) => onField('credits', v)} width={110} />
              </Field>
              <Field label={s.fieldBonusCreditsLegacy}>
                <NumInput value={d.bonus_credits} onChange={(v) => onField('bonus_credits', v)} width={110} />
              </Field>
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  )
}
