'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { toast, EmptyState, Skeleton } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { useCatalog } from '@/lib/useCatalog'
import { type Task, type Execution, type TaskForm } from './types'
import TaskCard from './components/TaskCard'
import TaskFormModal from './components/TaskFormModal'
import ExecutionHistoryModal from './components/ExecutionHistoryModal'

/* ═══════════════════════════════════════════════════════════════════════════
   Scheduled Tasks Page
   ═══════════════════════════════════════════════════════════════════════════ */

export default function TasksPage() {
  const { token, user, loading: authLoading } = useAuth()
  const { models: catalogModels, loading: catalogLoading } = useCatalog()
  // Cheapest currently-available model first, mirroring the backend's own
  // _default_model() resolution (backend/tasks.py) so the preselected value
  // matches what an empty model field would resolve to anyway. Never a
  // hardcoded id: a prior version defaulted to 'mimo-v2.5' and silently
  // broke every task when that model went into maintenance.
  const availableModels = useMemo(
    () =>
      catalogModels
        .filter((m) => m.availability === 'available')
        .slice()
        .sort((a, b) => (a.pricing.inputPerMillion + a.pricing.outputPerMillion) - (b.pricing.inputPerMillion + b.pricing.outputPerMillion)),
    [catalogModels],
  )
  const defaultModelId = availableModels[0]?.id ?? ''
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)
  const [form, setForm] = useState<TaskForm>({
    title: '', description: '', prompt: '', model: '',
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
      title: '', description: '', prompt: '', model: defaultModelId,
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
      const r = await apiFetch(url, {
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
      const r = await apiFetch(`/api/tasks/${task.id}/toggle`, {
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
      const r = await apiFetch(`/api/tasks/${task.id}/run`, {
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
      const r = await apiFetch(`/api/tasks/${task.id}`, {
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
      <div style={{ padding: '24px 0' }}>
        {authLoading ? (
          <div>
            <Skeleton height="2rem" width="200px" className="mb-4" />
            {[1, 2, 3].map((i) => (
              <div key={i} className="card" style={{ marginBottom: 12, padding: 20 }}>
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
    <div style={{ padding: '24px 0' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 12,
            background: 'linear-gradient(135deg, var(--accent), var(--accent-hover, var(--accent)))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon name="calendar" size={20} style={{ color: 'var(--text-on-accent)' }} />
          </div>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>
              تسک‌های زمان‌بندی شده
            </h1>
            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>
              اجرای خودکار پرامپت‌ها طبق زمان‌بندی
            </p>
          </div>
        </div>
        <button onClick={openCreate} className="btn btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
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
            <div key={i} className="card" style={{ marginBottom: 12, padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              runningTaskId={runningTaskId}
              deletingId={deletingId}
              onToggle={toggleTask}
              onRun={runTask}
              onEdit={openEdit}
              onDelete={deleteTask}
              onHistory={showHistory}
            />
          ))}
        </div>
      )}

      <TaskFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        editingTask={editingTask}
        form={form}
        setForm={setForm}
        saving={saving}
        onSave={saveTask}
        availableModels={availableModels}
        catalogLoading={catalogLoading}
      />

      <ExecutionHistoryModal
        open={historyModalOpen}
        onClose={() => { setHistoryModalOpen(false); setExecutions([]) }}
        taskTitle={historyTaskTitle}
        executions={executions}
      />

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
