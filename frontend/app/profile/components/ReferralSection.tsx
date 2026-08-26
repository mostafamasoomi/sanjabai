'use client'

import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { referralSectionStrings } from './ReferralSection.strings'

type ReferralSectionProps = {
  user: any
}

export default function ReferralSection({ user }: ReferralSectionProps) {
  const lang = useLang()
  const s = referralSectionStrings(lang)

  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon name="gift" size={16} className="text-accent" />
        <h2 className="card-title">
          {s.title}
        </h2>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
        {/* No monetary promise here any more: the referral bonus was removed
            when wallet credit was restricted to the payment gateway and admin
            only. The link still records who invited whom, so the attribution
            is real -- the reward is not, and must not be advertised. */}
        {s.intro}
      </p>
      {user?.referral_code && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label className="profile-input-label">{s.yourCode}</label>
            <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
              <code className="apikeys-code-block flex-1">
                {user.referral_code}
              </code>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(user.referral_code || '')
                  toast(s.codeCopied, 'success')
                }}
                className="btn btn-secondary btn-sm"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                <Icon name="copy" size={14} />
                {s.copy}
              </button>
            </div>
          </div>
          <div>
            <label className="profile-input-label">{s.yourLink}</label>
            <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
              <code className="apikeys-code-block" style={{ flex: 1, fontSize: 11 }}>
                {typeof window !== 'undefined' ? `${window.location.origin}/signup?ref=${user.referral_code}` : ''}
              </code>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(`${window.location.origin}/signup?ref=${user.referral_code}`)
                  toast(s.linkCopied, 'success')
                }}
                className="btn btn-secondary btn-sm"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                <Icon name="copy" size={14} />
                {s.copy}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
