'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/lib/auth'
import { toast, Modal, EmptyState, Skeleton, Tabs } from '@/components/ui'
import { Icon, type IconName } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Scheduled Tasks Page
   ═══════════════════════════════════════════════════════════════════════════ */

type Task = {
  id: number
  title: string
  description: string
  prompt: string
  model: string
  cron_expression: string
  is_active: boolean
  last_run_at: string | null
  next_run_at: string | null
  run_count: number
  last_result: string | null
  delivery_channel: string
  created_at: string
}

type Execution = {
  id: number
  status: string
  result: string
  tokens_used: number
  cost_toman: number
  error: string | null
  started_at: string
  completed_at: string | null
}

type TaskForm = {
  title: string
  description: string
  prompt: string
  model: string
  cron_expression: string
  delivery_channel: string
}

const MODELS = ['mimo-v2.5', 'gpt-5.6-luna', 'claude-sonnet-4', 'qwen3-coder-480b']

const DELIVERY_CHANNELS: Record<string, { label: string; icon: IconName }> = {
  dashboard: { label: 'داشبورد', icon: 'dashboard' },
  email: { label: 'ایمیل', icon: 'mail' },
  telegram: { label: 'تلگرام', icon: 'chat' },
}

const CRON_PRESETS = [
  { label: 'هر روز ساعت ۹ صبح', value: '0 9 * * *' },
  { label: 'هر روز ساعت ۱۲ شب', value: '0 0 * * *' },
  { label: 'هر ساعت', value: '0 * * * *' },
  { label: 'هر ۶ ساعت', value: '0 */6 * * *' },
  { label: 'هر هفته (دوشنبه)', value: '0 9 * * 1' },
  { label: 'هر ماه اول', value: '0 9 1 * *' },
]

function describeCron(expr: string): string {
  if (!expr) return '—'
  const presets = CRON_PRESETS.find((p) => p.value === expr)
  if (presets) return presets.label
  const parts = expr.split(' ')
  if (parts.length !== 5) return expr
  const [min, hour, dom, mon, dow] = parts
  if (dom === '*' && mon === '*' && dow === '*') {
    if (hour !== '*' && min !== '*') return `هر روز ساعت ${hour}:${min.padStart(2, '0')}`
    if (hour !== '*') return `هر ساعت`
    return `هر ${min} دقیقه`
  }
  if (dow !== '*') {
    const days: Record<string, string> = {
      '0': 'یکشنبه', '1': 'دوشنبه', '2': 'سه‌شنبه', '3': 'چهارشنبه',
      '4': 'پنجشنبه', '5': 'جمعه', '6': 'شنبه',
    }
    const day = days[dow] || dow
    if (hour !== '*') return `هر ${day} ساعت ${hour}:${min.padStart(2, '0')}`
    return `هر ${day}`
  }
  return expr
}

function formatDateTime(s: string | null): string {
  if (!s) return '—'
  return new Date(s).toLocaleString('fa-IR', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  success: { label: 'موفق', color: 'badge-positive' },
  failed: { label: 'ناموفق', color: 'badge-danger' },
  running: { label: 'در حال اجرا', color: 'badge-warning' },
}

export default function TasksPage() {
  const { token, user, loading: authLoading } = useAuth()
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)
  const [form, setForm] = useState<TaskForm>({
    title: '', description: '', prompt: '', model: MODELS[0],
    cron_expression: '0 9 * * *', delivery_channel: 'dashboard',
  })
  const [saving, setSaving] = useState(false)
  const [executions, setExecutions] = useState<Execution[]>([])
  const [historyModalOpen, setHistoryModalOpen] = useState(false)
  const [historyTaskTitle, setHistoryTaskTitle] = useState('')
  const [runningTaskId, setRunningTaskId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const headers = useCallback(() => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }), [token])

  const fetchTasks = useCallback(async () => {
    if (!token) return
    try {
      setLoading(true)
      const r = await fetch('/api/tasks', { headers: headers() })
      if (r.ok) {
        const data = await r.json()
        // Backend may return array or paginated {items: [...]} format
        setTasks(Array.isArray(data) ? data : (data?.items ?? []))
      }
    } catch {
      toast('خطا در دریافت تسک‌ها', 'error')
    } finally {
      setLoading(false)
    }
  }, [token, headers])

  useEffect(() => {
    if (!authLoading && user) fetchTasks()
  }, [authLoading, user, fetchTasks])

  const openCreate = () => {
    setEditingTask(null)
    setForm({
      title: '', description: '', prompt: '', model: MODELS[0],
      cron_expression: '0 9 * * *', delivery_channel: 'dashboard',
    })
    setModalOpen(true)
  }

  const openEdit = (task: Task) => {
    setEditingTask(task)
    setForm({
      title: task.title,
      description: task.description || '',
      prompt: task.prompt,
      model: task.model,
      cron_expression: task.cron_expression,
      delivery_channel: task.delivery_channel || 'dashboard',
    })
    setModalOpen(true)
  }

  const saveTask = async () => {
    if (!form.title.trim() || !form.prompt.trim()) {
      toast('عنوان و پرامپت الزامی هستند', 'error')
      return
    }
    setSaving(true)
    try {
      const url = editingTask ? `/api/tasks/${editingTask.id}` : '/api/tasks'
      const method = editingTask ? 'PUT' : 'POST'
      const r = await fetch(url, {
        method,
        headers: headers(),
        body: JSON.stringify(form),
      })
      if (r.ok) {
        toast(editingTask ? 'تسک بروزرسانی شد' : 'تسک جدید ایجاد شد', 'success')
        setModalOpen(false)
        fetchTasks()
      } else {
        const data = await r.json().catch(() => ({}))
        toast(data.detail || 'خطا در ذخیره تسک', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    } finally {
      setSaving(false)
    }
  }

  const toggleTask = async (task: Task) => {
    try {
      const r = await fetch(`/api/tasks/${task.id}/toggle`, {
        method: 'POST', headers: headers(),
      })
      if (r.ok) {
        toast(task.is_active ? 'تسک غیرفعال شد' : 'تسک فعال شد', 'success')
        fetchTasks()
      }
    } catch {
      toast('خطا', 'error')
    }
  }

  const runTask = async (task: Task) => {
    setRunningTaskId(task.id)
    try {
      const r = await fetch(`/api/tasks/${task.id}/run`, {
        method: 'POST', headers: headers(),
      })
      if (r.ok) {
        toast('تسک با موفقیت اجرا شد', 'success')
        fetchTasks()
      } else {
        toast('خطا در اجرای تسک', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    } finally {
      setRunningTaskId(null)
    }
  }

  const deleteTask = async (task: Task) => {
    if (!confirm(`آیا از حذف «${task.title}» مطمئن هستید؟`)) return
    setDeletingId(task.id)
    try {
      const r = await fetch(`/api/tasks/${task.id}`, {
        method: 'DELETE', headers: headers(),
      })
      if (r.ok) {
        toast('تسک حذف شد', 'success')
        fetchTasks()
      }
    } catch {
      toast('خطا', 'error')
    } finally {
      setDeletingId(null)
    }
  }

  const showHistory = async (task: Task) => {
    setHistoryTaskTitle(task.title)
    setHistoryModalOpen(true)
    try {
      const r = await fetch(`/api/tasks/${task.id}/executions`, { headers: headers() })
      if (r.ok) {
        const data = await r.json()
        // Backend may return array or paginated {items: [...]} format
        setExecutions(Array.isArray(data) ? data : (data?.items ?? []))
      }
    } catch {
      toast('خطا در دریافت تاریخچه', 'error')
    }
  }

  if (authLoading || (!user && !authLoading)) {
    return (
      <div className="py-6">
        {authLoading ? (
          <div>
            <Skeleton height="2rem" width="200px" className="mb-4" />
            {[1, 2, 3].map((i) => (
 <div key={i} className="card mb-3 p-5" >
                <Skeleton height="1.2rem" className="mb-3" />
                <Skeleton height="0.9rem" width="60%" className="mb-2" />
                <Skeleton height="0.9rem" width="40%" />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon="lock" title="برای مشاهده تسک‌ها وارد شوید" description="ابتدا باید وارد حساب خود شوید." />
        )}
      </div>
    )
  }

  return (
    <div className="py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2.5">
          <div style={{
            width: 40, height: 40, borderRadius: 12,
            background: 'linear-gradient(135deg, var(--accent), var(--accent-hover, var(--accent)))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon name="calendar" size={20} className="text-[var(--text-on-accent)]" />
          </div>
          <div>
            <h1 className="text-[22px] font-bold text-primary leading-tight">
              تسک‌های زمان‌بندی شده
            </h1>
            <p className="text-[13px] text-muted mt-0.5">
              اجرای خودکار پرامپت‌ها طبق زمان‌بندی
            </p>
          </div>
        </div>
 <button onClick={openCreate} className="btn btn-primary inline-flex items-center gap-1.5" >
          <Icon name="plus" size={16} />
          ایجاد تسک جدید
        </button>
      </div>

      {/* Info card */}
      <div className="card" style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '14px 18px', marginBottom: 20,
        background: 'linear-gradient(135deg, var(--bg-elev), var(--bg-surface, var(--bg-elev)))',
        border: '1px solid var(--border)',
      }}>
        <Icon name="info" size={18} className="text-accent shrink-0" />
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.7 }}>
          تسک‌ها به صورت خودکار طبق زمان‌بندی اجرا می‌شوند و نتیجه در داشبورد نمایش داده می‌شود.
        </p>
      </div>

      {/* Loading skeletons */}
      {loading ? (
        <div>
          {[1, 2, 3].map((i) => (
 <div key={i} className="card mb-3 p-5" >
              <div className="flex justify-between items-center mb-3">
                <Skeleton height="1.2rem" width="200px" />
                <Skeleton height="1.5rem" width="50px" />
              </div>
              <Skeleton height="0.9rem" width="60%" className="mb-2" />
              <Skeleton height="0.9rem" width="40%" />
            </div>
          ))}
        </div>
      ) : tasks.length === 0 ? (
        <EmptyState
          icon="calendar"
          title="هنوز تسکی ایجاد نشده"
          description="اولین تسک زمان‌بندی شده خود را بسازید تا پرامپت‌ها به صورت خودکار اجرا شوند."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {tasks.map((task) => {
            const ch = DELIVERY_CHANNELS[task.delivery_channel] || DELIVERY_CHANNELS.dashboard
            return (
              <div key={task.id} className="card" style={{
                padding: '18px 20px',
                opacity: task.is_active ? 1 : 0.7,
                transition: 'opacity 0.2s',
              }}>
                {/* Top row: title + toggle */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <div className="flex items-center gap-2.5 min-w-0">
                    <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {task.title}
                    </h3>
 <span className="badge badge-accent text-[11px] shrink-0" >
                      {task.model}
                    </span>
                  </div>
                  <button
                    onClick={() => toggleTask(task)}
                    style={{
                      width: 44, height: 24, borderRadius: 12,
                      background: task.is_active ? 'var(--positive)' : 'var(--border)',
                      border: 'none', cursor: 'pointer', position: 'relative',
                      transition: 'background 0.2s', flexShrink: 0,
                    }}
                    title={task.is_active ? 'غیرفعال کردن' : 'فعال کردن'}
                  >
                    <span style={{
                      width: 18, height: 18, borderRadius: '50%',
                      background: 'var(--text-on-accent)', position: 'absolute', top: 3,
                      left: task.is_active ? 3 : 23,
                      transition: 'left 0.2s',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                    }} />
                  </button>
                </div>

                {/* Cron + badges */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10, alignItems: 'center' }}>
                  <span className="inline-flex items-center gap-1 text-xs text-muted">
                    <Icon name="clock" size={12} />
                    {describeCron(task.cron_expression)}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', direction: 'ltr', fontFamily: 'var(--font-mono)' }}>
                    {task.cron_expression}
                  </span>
                  <span className="badge" style={{
                    background: task.is_active ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                    color: task.is_active ? 'var(--positive)' : 'var(--danger)',
                    fontSize: 11,
                  }}>
                    {task.is_active ? 'فعال' : 'غیرفعال'}
                  </span>
                  <span className="badge" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, background: 'var(--bg-surface, var(--bg-elev))' }}>
                    <Icon name={ch.icon} size={11} />
                    {ch.label}
                  </span>
                </div>

                {/* Description */}
                {task.description && (
                  <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 10px', lineHeight: 1.6 }}>
                    {task.description}
                  </p>
                )}

                {/* Stats row */}
                <div className="flex flex-wrap gap-4 text-xs text-muted mb-3">
                  <span className="inline-flex items-center gap-1">
                    <Icon name="history" size={12} />
                    اجرا: {task.run_count.toLocaleString('fa-IR')} بار
                  </span>
                  {task.last_run_at && (
                    <span className="inline-flex items-center gap-1">
                      <Icon name="clock" size={12} />
                      آخرین اجرا: {formatDateTime(task.last_run_at)}
                    </span>
                  )}
                  {task.next_run_at && (
                    <span className="inline-flex items-center gap-1">
                      <Icon name="calendar" size={12} />
                      اجرای بعدی: {formatDateTime(task.next_run_at)}
                    </span>
                  )}
                </div>

                {/* Action buttons */}
                <div className="flex gap-2 flex-wrap">
                  <button
                    onClick={() => runTask(task)}
                    disabled={runningTaskId === task.id}
                    className="btn btn-primary btn-sm"
                    className="inline-flex items-center gap-1"
                  >
                    {runningTaskId === task.id ? (
                      <span style={{ width: 12, height: 12, border: '2px solid var(--text-on-accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
                    ) : (
                      <Icon name="send" size={13} />
                    )}
                    اجرا
                  </button>
                  <button
                    onClick={() => showHistory(task)}
                    className="btn btn-ghost btn-sm"
                    className="inline-flex items-center gap-1"
                  >
                    <Icon name="history" size={13} />
                    تاریخچه
                  </button>
                  <button
                    onClick={() => openEdit(task)}
                    className="btn btn-ghost btn-sm"
                    className="inline-flex items-center gap-1"
                  >
                    <Icon name="settings" size={13} />
                    ویرایش
                  </button>
                  <button
                    onClick={() => deleteTask(task)}
                    disabled={deletingId === task.id}
                    className="btn btn-ghost btn-sm"
                    className="inline-flex items-center gap-1 text-danger"
                  >
                    {deletingId === task.id ? (
                      <span style={{ width: 12, height: 12, border: '2px solid var(--danger)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
                    ) : (
                      <Icon name="trash" size={13} />
                    )}
                    حذف
                  </button>
                </div>

                {/* Last result preview */}
                {task.last_result && (
                  <div style={{
                    marginTop: 12, padding: '10px 14px', borderRadius: 8,
                    background: 'var(--bg-surface, var(--bg-elev))',
                    fontSize: 12, color: 'var(--text-secondary)',
                    fontFamily: 'var(--font-mono)', direction: 'ltr', textAlign: 'left',
                    maxHeight: 60, overflow: 'hidden', lineHeight: 1.6,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  }}>
                    {task.last_result.slice(0, 200)}{task.last_result.length > 200 ? '...' : ''}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingTask ? 'ویرایش تسک' : 'ایجاد تسک جدید'}
      >
        <div className="flex flex-col gap-4">
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
              placeholder="پرامپتی که قرار است اجرا شود...&#10;از {variable} برای متغیرها استفاده کنید"
              style={{ resize: 'vertical', direction: 'ltr', textAlign: 'left', fontFamily: 'var(--font-mono)' }}
            />
            <p className="text-[11px] text-muted mt-1">
              از {'{variable}'} برای جایگذاری متغیرها در زمان اجرا استفاده کنید.
            </p>
          </div>

          {/* Model */}
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
              مدل
            </label>
            <select
              className="input cursor-pointer"
              value={form.model}
              onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
            >
              {MODELS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>

          {/* Cron Expression */}
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
              زمان‌بندی (Cron Expression)
            </label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {CRON_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  type="button"
                  className={`btn btn-sm ${form.cron_expression === preset.value ? 'btn-primary' : 'btn-ghost'}`}
                  onClick={() => setForm((f) => ({ ...f, cron_expression: preset.value }))}
                  className="text-[11px]"
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
            <p className="text-[11px] text-muted mt-1">
              فرمت: دقیقه ساعت روز ماه ماه روز_هفته — مثال: <code>0 9 * * *</code> = هر روز ساعت ۹ صبح
            </p>
          </div>

          {/* Delivery Channel */}
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
              کانال ارسال نتیجه
            </label>
            <div className="flex gap-2">
              {Object.entries(DELIVERY_CHANNELS).map(([key, ch]) => (
                <button
                  key={key}
                  type="button"
                  className={`btn btn-sm ${form.delivery_channel === key ? 'btn-primary' : 'btn-ghost'}`}
                  onClick={() => setForm((f) => ({ ...f, delivery_channel: key }))}
                  className="inline-flex items-center gap-1"
                >
                  <Icon name={ch.icon} size={14} />
                  {ch.label}
                </button>
              ))}
            </div>
          </div>

          {/* Save */}
          <button
            onClick={saveTask}
            disabled={saving || !form.title.trim() || !form.prompt.trim()}
            className="btn btn-primary w-full"
            className="inline-flex items-center justify-center gap-1.5 mt-1"
          >
            {saving ? (
              <span style={{ width: 16, height: 16, border: '2px solid var(--text-on-accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
            ) : (
              <Icon name="check" size={16} />
            )}
            ذخیره
          </button>
        </div>
      </Modal>

      {/* Execution History Modal */}
      <Modal
        open={historyModalOpen}
        onClose={() => { setHistoryModalOpen(false); setExecutions([]) }}
        title={`تاریخچه اجرا — ${historyTaskTitle}`}
      >
        {executions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
            <Icon name="history" size={32} className="mb-2" />
            <p>هنوز اجرایی ثبت نشده است</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {executions.map((ex) => {
              const st = STATUS_MAP[ex.status] || { label: ex.status, color: 'badge-accent' }
              return (
                <div key={ex.id} style={{
                  padding: '12px 14px', borderRadius: 8,
                  border: '1px solid var(--border)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span className={`badge ${st.color}`} className="text-[11px]">{st.label}</span>
                    <span className="text-[11px] text-muted">
                      {formatDateTime(ex.started_at)}
                    </span>
                  </div>
                  {ex.error && (
                    <p style={{ fontSize: 12, color: 'var(--danger)', margin: '4px 0', direction: 'ltr', fontFamily: 'var(--font-mono)' }}>
                      {ex.error}
                    </p>
                  )}
                  {ex.result && (
                    <div style={{
                      fontSize: 12, color: 'var(--text-secondary)', direction: 'ltr', textAlign: 'left',
                      fontFamily: 'var(--font-mono)', maxHeight: 60, overflow: 'hidden',
                      lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                    }}>
                      {ex.result.slice(0, 200)}{ex.result.length > 200 ? '...' : ''}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                    {ex.tokens_used > 0 && (
                      <span>{ex.tokens_used.toLocaleString('fa-IR')} توکن</span>
                    )}
                    {ex.cost_toman > 0 && (
                      <span>{ex.cost_toman.toLocaleString('fa-IR')} تومان</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Modal>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
