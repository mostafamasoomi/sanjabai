'use client'

import { Modal } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import type { ModelCatalogItem } from '@/types/catalog'
import { type Task, type TaskForm, DELIVERY_CHANNELS, CRON_PRESETS } from '../types'

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
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingTask ? 'ویرایش تسک' : 'ایجاد تسک جدید'}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Title */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            عنوان <span className="text-danger">*</span>
          </label>
          <input
            className="input"
            value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            placeholder="مثلاً: خلاصه روزانه اخبار"
          />
        </div>

        {/* Description */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            توضیحات
          </label>
          <textarea dir="rtl"
            className="input"
            rows={2}
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="توضیح کوتاه درباره این تسک..."
            style={{ resize: 'vertical' }}
          />
        </div>

        {/* Prompt */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            پرامپت <span className="text-danger">*</span>
          </label>
          <textarea dir="rtl"
            className="input"
            rows={5}
            value={form.prompt}
            onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
            placeholder="پرامپتی که قرار است اجرا شود..."
            style={{ resize: 'vertical', direction: 'ltr', textAlign: 'left', fontFamily: 'var(--font-mono)' }}
          />
        </div>

        {/* Model */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            مدل
          </label>
          {availableModels.length > 0 ? (
            <select
              className="input cursor-pointer"
              value={form.model}
              onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
            >
              {/* Empty value = sentinel: backend picks the cheapest
                  available model at run time (backend/tasks.py). */}
              <option value="">انتخاب خودکار (پیشنهاد سیستم)</option>
              {availableModels.map((m) => (
                <option key={m.id} value={m.id}>{m.displayName}</option>
              ))}
            </select>
          ) : (
            <div className="input" style={{ color: 'var(--text-muted)', cursor: 'default' }}>
              {catalogLoading ? 'در حال دریافت فهرست مدل‌ها...' : 'مدلی در دسترس نیست — به‌صورت خودکار انتخاب می‌شود'}
            </div>
          )}
        </div>

        {/* Cron Expression */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            زمان‌بندی (Cron Expression)
          </label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {CRON_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                className={`btn btn-sm ${form.cron_expression === preset.value ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setForm((f) => ({ ...f, cron_expression: preset.value }))}
                style={{ fontSize: 11 }}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <input
            className="input"
            value={form.cron_expression}
            onChange={(e) => setForm((f) => ({ ...f, cron_expression: e.target.value }))}
            placeholder="0 9 * * *"
            style={{ direction: 'ltr', textAlign: 'left', fontFamily: 'var(--font-mono)' }}
          />
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            فرمت: دقیقه ساعت روز ماه ماه روز_هفته — مثال: <code>0 9 * * *</code> = هر روز ساعت ۹ صبح
          </p>
        </div>

        {/* Delivery Channel */}
        <div>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
            کانال ارسال نتیجه
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            {Object.entries(DELIVERY_CHANNELS).map(([key, ch]) => (
              <button
                key={key}
                type="button"
                className={`btn btn-sm ${form.delivery_channel === key ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setForm((f) => ({ ...f, delivery_channel: key }))}
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
          ذخیره
        </button>
      </div>
    </Modal>
  )
}
