'use client'

import { Modal } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import type { ModelCatalogItem } from '@/types/catalog'
import { useLang } from '@/components/LanguageToggle'
import { type Task, type TaskForm, deliveryChannels, cronPresets } from '../types'
import { taskFormModalStrings } from './TaskFormModal.strings'

export default function TaskFormModal({
  open,
  onClose,
  editingTask,
  form,
  setForm,
  saving,
  onSave,
  availableModels,
  catalogLoading,
}: {
  open: boolean
  onClose: () => void
  editingTask: Task | null
  form: TaskForm
  setForm: (updater: (f: TaskForm) => TaskForm) => void
  saving: boolean
  onSave: () => void
  availableModels: ModelCatalogItem[]
  catalogLoading: boolean
}) {
  const lang = useLang()
  const s = taskFormModalStrings(lang)
  const channels = deliveryChannels(lang)
  const presets = cronPresets(lang)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingTask ? s.editTitle : s.createTitle}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Title */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            {s.title} <span className="text-danger">*</span>
          </label>
          <input
            className="input"
            value={form.title}
            onChange={(e) => setForm((fm) => ({ ...fm, title: e.target.value }))}
            placeholder={s.titlePlaceholder}
          />
        </div>

        {/* Description */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            {s.description}
          </label>
          <textarea
            className="input"
            rows={2}
            value={form.description}
            onChange={(e) => setForm((fm) => ({ ...fm, description: e.target.value }))}
            placeholder={s.descriptionPlaceholder}
            style={{ resize: 'vertical' }}
          />
        </div>

        {/* Prompt */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            {s.prompt} <span className="text-danger">*</span>
          </label>
          <textarea
            className="input"
            rows={5}
            value={form.prompt}
            onChange={(e) => setForm((fm) => ({ ...fm, prompt: e.target.value }))}
            placeholder={s.promptPlaceholder}
            style={{ resize: 'vertical', direction: 'ltr', textAlign: 'left', fontFamily: 'var(--font-mono)' }}
          />
        </div>

        {/* Model */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            {s.model}
          </label>
          {availableModels.length > 0 ? (
            <select
              className="input cursor-pointer"
              value={form.model}
              onChange={(e) => setForm((fm) => ({ ...fm, model: e.target.value }))}
            >
              {/* Empty value = sentinel: backend picks the cheapest
                  available model at run time (backend/tasks.py). */}
              <option value="">{s.autoSelect}</option>
              {availableModels.map((m) => (
                <option key={m.id} value={m.id}>{m.displayName}</option>
              ))}
            </select>
          ) : (
            <div className="input" style={{ color: 'var(--text-muted)', cursor: 'default' }}>
              {catalogLoading ? s.loadingModels : s.noModelsAvailable}
            </div>
          )}
        </div>

        {/* Cron Expression */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            {s.cronLabel}
          </label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {presets.map((preset) => (
              <button
                key={preset.value}
                type="button"
                className={`btn btn-sm ${form.cron_expression === preset.value ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setForm((fm) => ({ ...fm, cron_expression: preset.value }))}
                style={{ fontSize: 11 }}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <input
            className="input"
            value={form.cron_expression}
            onChange={(e) => setForm((fm) => ({ ...fm, cron_expression: e.target.value }))}
            placeholder="0 9 * * *"
            style={{ direction: 'ltr', textAlign: 'left', fontFamily: 'var(--font-mono)' }}
          />
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            {s.cronFormatHint('0 9 * * *')}
          </p>
        </div>

        {/* Delivery Channel */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            {s.deliveryChannel}
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            {Object.entries(channels).map(([key, ch]) => (
              <button
                key={key}
                type="button"
                className={`btn btn-sm ${form.delivery_channel === key ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setForm((fm) => ({ ...fm, delivery_channel: key }))}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                <Icon name={ch.icon} size={14} />
                {ch.label}
              </button>
            ))}
          </div>
        </div>

        {/* Save */}
        <button
          onClick={onSave}
          disabled={saving || !form.title.trim() || !form.prompt.trim()}
          className="btn btn-primary w-full"
          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 4 }}
        >
          {saving ? (
            <span style={{ width: 16, height: 16, border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
          ) : (
            <Icon name="check" size={16} />
          )}
          {s.save}
        </button>
      </div>
    </Modal>
  )
}
