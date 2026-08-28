'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { smartModeSectionStrings } from './SmartModeSection.strings'

/* ───────────────────────────────────────────────────────────────────────────
   Smart mode, documented for API-key consumers.

   The capability has worked for API keys since it shipped -- /v1/smart-chat
   takes `_get_user_id`, the same dependency that accepts a session cookie or
   an `sk-` key -- but this page said nothing about it, so it was invisible to
   exactly the audience that would use it from code.

   Header names, values and precedence are code, not prose: they stay Latin
   and untranslated in both languages, like every other identifier on this
   page. Only the surrounding explanation is translated.

   No claim here names a number or a feature-flag state. Whether a mode is
   available to a given account is server-side and can change; the honest
   contract is the one written below -- the RESPONSE header reports what
   actually ran, and an unavailable mode degrades silently to the rules.
   ─────────────────────────────────────────────────────────────────────────── */

const REQUEST_HEADER = 'X-Smart-Mode: auto | router | combo:<id>'
const FORCE_HEADER = 'X-Smart-Model: <public_id>'
const ENDPOINT = 'POST /v1/smart-chat'

function Mono({ children }: { children: string }) {
  return (
    <code style={{
      fontSize: 13, fontWeight: 600, direction: 'ltr',
      fontFamily: 'var(--font-mono)', color: 'var(--text-primary)',
    }}>
      {children}
    </code>
  )
}

function Row({ name, desc }: { name: string; desc: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <Mono>{name}</Mono>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>{desc}</p>
    </div>
  )
}

export function SmartModeSection() {
  const lang = useLang()
  const s = smartModeSectionStrings(lang)

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="sparkles" size={16} className="text-accent" />
        <h2 className="card-title">{s.title}</h2>
      </div>

      <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 14px' }}>{s.intro}</p>

      <div style={{
        padding: '16px 18px', borderRadius: 10, border: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{s.requestHeaderTitle}</div>
          <Mono>{ENDPOINT}</Mono>
          <div style={{ marginTop: 6 }}><Mono>{REQUEST_HEADER}</Mono></div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '8px 0 0' }}>{s.requestHeaderDesc}</p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.modesTitle}</div>
          <Row name="auto" desc={s.modeAuto} />
          <Row name="router" desc={s.modeRouter} />
          <Row name="combo:<id>" desc={s.modeCombo} />
        </div>
      </div>

      <div style={{
        marginTop: 14, padding: '16px 18px', borderRadius: 10,
        border: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', gap: 10,
      }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.responseTitle}</div>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>{s.responseDesc}</p>
        <Row name="X-Smart-Mode" desc={s.respMode} />
        <Row name="X-Smart-Model" desc={s.respModel} />
      </div>

      <div style={{
        marginTop: 14, padding: '16px 18px', borderRadius: 10,
        border: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', gap: 6,
      }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.forceTitle}</div>
        <Mono>{FORCE_HEADER}</Mono>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>{s.forceDesc}</p>
      </div>
    </div>
  )
}
