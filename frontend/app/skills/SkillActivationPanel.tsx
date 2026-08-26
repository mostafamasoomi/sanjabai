'use client'

import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { skillActivationPanelStrings } from './SkillActivationPanel.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Skill activation — until today "skill" meant a prompt-template library:
   POST /skills/{id}/use rendered the template and handed the string back to
   the caller, and the word never reached the model. A backend change (in
   parallel with this component) makes an "active" skill something the chat
   pipeline injects into every message. This panel is the only place a user
   can switch that on or off, so it is also the only place that can be
   honest about the cost: an active skill is added to every message and the
   user pays token cost for it on every single turn, not once.

   Server contract (backend, built in parallel — see NEXT-SESSION.md):
     GET    /api/skills/active        -> [{ id, title, title_fa, position, enabled }]
     POST   /api/skills/{id}/activate -> activates; 400 (Persian `detail`) once
                                          the user already has MAX_ACTIVE_SKILLS
                                          active — that message is shown
                                          verbatim, never paraphrased here.
     DELETE /api/skills/{id}/activate -> deactivates.

   Self-contained (own fetch, own auth via useAuth()) so the page.tsx edit
   stays a one-line `<SkillActivationPanel />` insert — that file is already
   over the repo's 500-line cap.
   ═══════════════════════════════════════════════════════════════════════════ */

type ActiveSkill = {
  id: number
  title: string
  title_fa: string
  position: number
  enabled: boolean
}

/** Mirrors the backend's cap (see contract above). Only used here for the
 *  proactive "you're at the cap" disabled state and the "x از y" readout —
 *  the server is the actual enforcement; a stale value here just means a
 *  round trip that comes back with the real (verbatim) 400 message. */
const MAX_ACTIVE_SKILLS = 3

export default function SkillActivationPanel() {
  const { token } = useAuth()
  const lang = useLang()
  const s = skillActivationPanelStrings(lang)
  const f = fmt(lang)

  const [skills, setSkills] = useState<ActiveSkill[]>([])
  const [loading, setLoading] = useState(true)
  const [loadFailed, setLoadFailed] = useState(false)
  const [pending, setPending] = useState<Set<number>>(new Set())

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setLoadFailed(false)
    try {
      const res = await apiFetch('/api/skills/active', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('bad status')
      const data = await res.json()
      const list: ActiveSkill[] = Array.isArray(data) ? data : []
      list.sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
      setSkills(list)
    } catch {
      setLoadFailed(true)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    load()
  }, [load])

  const activeCount = skills.filter((s) => s.enabled).length

  const toggle = async (skill: ActiveSkill) => {
    if (!token || pending.has(skill.id)) return
    const wasEnabled = skill.enabled
    const nextEnabled = !wasEnabled

    setPending((prev) => new Set(prev).add(skill.id))
    // Optimistic update — rolled back below on any failure.
    setSkills((prev) => prev.map((s) => (s.id === skill.id ? { ...s, enabled: nextEnabled } : s)))

    try {
      const res = await apiFetch(`/api/skills/${skill.id}/activate`, {
        method: nextEnabled ? 'POST' : 'DELETE',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      })

      if (!res.ok) {
        // The backend's 400 (cap reached) carries a Persian `detail` — that
        // exact sentence is what gets shown, never a paraphrase of it.
        let detail = ''
        try {
          const body = await res.json()
          if (typeof body?.detail === 'string' && body.detail.trim()) detail = body.detail.trim()
        } catch {
          /* non-JSON error body — fall through to the generic message */
        }
        setSkills((prev) => prev.map((s) => (s.id === skill.id ? { ...s, enabled: wasEnabled } : s)))
        toast(
          detail || (nextEnabled ? s.toggleFailedEnable : s.toggleFailedDisable),
          'error',
        )
        return
      }

      toast(nextEnabled ? s.toggleSuccessEnable : s.toggleSuccessDisable, 'success')
    } catch {
      setSkills((prev) => prev.map((s) => (s.id === skill.id ? { ...s, enabled: wasEnabled } : s)))
      toast(s.serverError, 'error')
    } finally {
      setPending((prev) => {
        const next = new Set(prev)
        next.delete(skill.id)
        return next
      })
    }
  }

  if (!token) return null

  return (
    <div className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
        <div className="flex items-center gap-2">
          <Icon name="cpu" size={18} className="text-[var(--accent)]" />
          <h2 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {s.heading}
          </h2>
        </div>
        {!loading && !loadFailed && skills.length > 0 && (
          <span className="badge">
            {s.activeBadge(f.num(activeCount), f.num(MAX_ACTIVE_SKILLS))}
          </span>
        )}
      </div>

      {/* ── Honesty notice — the whole point of this feature ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.5rem',
          padding: '0.65rem 0.85rem',
          borderRadius: 'var(--radius-md)',
          background: 'var(--accent-dim)',
          fontSize: '0.75rem',
          color: 'var(--text-secondary)',
          lineHeight: 1.7,
        }}
      >
        <Icon name="info" size={15} className="text-[var(--accent)]" style={{ flexShrink: 0, marginTop: '0.1rem' }} />
        <span>
          {s.noticeBefore}<strong>{s.noticeStrong}</strong>{s.noticeAfter}
        </span>
      </div>

      {/* ── Loading ── */}
      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ width: '100%', height: '2.75rem', borderRadius: 'var(--radius-md)' }} />
          ))}
        </div>
      )}

      {/* ── Load error ── */}
      {!loading && loadFailed && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.75rem',
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-hover)',
            fontSize: '0.8125rem',
            color: 'var(--text-secondary)',
          }}
        >
          <span>{s.loadErrorText}</span>
          <button className="btn btn-sm" onClick={load}>
            <Icon name="refresh" size={14} />
            {s.retry}
          </button>
        </div>
      )}

      {/* ── Empty state — user has no skills at all ── */}
      {!loading && !loadFailed && skills.length === 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '1.5rem 1rem',
            textAlign: 'center',
          }}
        >
          <Icon name="sparkles" size={28} className="text-[var(--text-muted)]" style={{ opacity: 0.4 }} />
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            {s.emptyText}
          </p>
          <a
            href="#top"
            onClick={(e) => {
              e.preventDefault()
              window.scrollTo({ top: 0, behavior: 'smooth' })
            }}
            className="btn btn-sm btn-primary"
          >
            <Icon name="plus" size={14} />
            {s.createFromTop}
          </a>
        </div>
      )}

      {/* ── Skill toggle list ── */}
      {!loading && !loadFailed && skills.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          {skills.map((skill) => {
            const atCap = !skill.enabled && activeCount >= MAX_ACTIVE_SKILLS
            const isPending = pending.has(skill.id)
            return (
              <div
                key={skill.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '0.75rem',
                  padding: '0.6rem 0.85rem',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--bg-hover)',
                  opacity: atCap ? 0.6 : 1,
                }}
              >
                <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {skill.title_fa || skill.title}
                </span>
                <button
                  className={`profile-toggle ${skill.enabled ? 'active' : ''}`}
                  role="switch"
                  aria-checked={skill.enabled}
                  aria-label={`${skill.enabled ? s.disableAction : s.enableAction} ${skill.title_fa || skill.title}`}
                  disabled={isPending || (atCap && !skill.enabled)}
                  title={atCap && !skill.enabled ? s.capHint(f.num(MAX_ACTIVE_SKILLS)) : undefined}
                  onClick={() => toggle(skill)}
                  style={isPending ? { opacity: 0.5, cursor: 'wait' } : undefined}
                >
                  <span className="profile-toggle-knob" />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
