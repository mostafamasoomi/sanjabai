'use client'

import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { type Task, DELIVERY_CHANNELS, describeCron, formatDateTime } from '../types'

export default function TaskCard({
  task,
  runningTaskId,
  deletingId,
  onToggle,
  onRun,
  onEdit,
  onDelete,
  onHistory,
}: {
  task: Task
  runningTaskId: number | null
  deletingId: number | null
  onToggle: (task: Task) => void
  onRun: (task: Task) => void
  onEdit: (task: Task) => void
  onDelete: (task: Task) => void
  onHistory: (task: Task) => void
}) {
  const ch = DELIVERY_CHANNELS[task.delivery_channel] || DELIVERY_CHANNELS.dashboard

  return (
    <div className="card" style={{
      padding: '18px 20px',
      opacity: task.is_active ? 1 : 0.7,
      transition: 'opacity 0.2s',
    }}>
      {/* Top row: title + toggle */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {task.title}
          </h3>
          <span className="badge badge-accent" style={{ fontSize: 11, flexShrink: 0 }}>
            {task.model}
          </span>
        </div>
        <button
          onClick={() => onToggle(task)}
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
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>
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
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <Icon name="history" size={12} />
          اجرا: {faNum(task.run_count)} بار
        </span>
        {task.last_run_at && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <Icon name="clock" size={12} />
            آخرین اجرا: {formatDateTime(task.last_run_at)}
          </span>
        )}
        {task.next_run_at && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <Icon name="calendar" size={12} />
            اجرای بعدی: {formatDateTime(task.next_run_at)}
          </span>
        )}
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          onClick={() => onRun(task)}
          disabled={runningTaskId === task.id}
          className="btn btn-primary btn-sm"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          {runningTaskId === task.id ? (
            <span style={{ width: 12, height: 12, border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
          ) : (
            <Icon name="send" size={13} />
          )}
          اجرا
        </button>
        <button
          onClick={() => onHistory(task)}
          className="btn btn-ghost btn-sm"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          <Icon name="history" size={13} />
          تاریخچه
        </button>
        <button
          onClick={() => onEdit(task)}
          className="btn btn-ghost btn-sm"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          <Icon name="settings" size={13} />
          ویرایش
        </button>
        <button
          onClick={() => onDelete(task)}
          disabled={deletingId === task.id}
          className="btn btn-ghost btn-sm"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--danger)' }}
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
}
