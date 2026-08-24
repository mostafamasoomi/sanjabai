'use client'

import { useAuth } from '@/lib/auth'
import { Skeleton } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { ApiKeyRevealModal } from '@/components/ApiKeyRevealModal'
import { useApiKeys } from './hooks/useApiKeys'
import { ApiInfoCard } from './components/ApiInfoCard'
import { ApiKeysSection } from './components/ApiKeysSection'
import { CodeExamplesSection } from './components/CodeExamplesSection'
import { EndpointDocsSection } from './components/EndpointDocsSection'

/* ═══════════════════════════════════════════════════════════════════════════
   Developer API Page

   API key CRUD lives in ./hooks/useApiKeys, static reference data (rate
   limits, code samples, endpoint docs) in ./constants, and each card below
   is its own presentational component under ./components — this file only
   owns the auth gate and wiring.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function DeveloperPage() {
  const { token, user, loading: authLoading } = useAuth()
  const {
    keys,
    newKeyName,
    setNewKeyName,
    keyLoading,
    revokingId,
    rotatingId,
    reveal,
    setReveal,
    createKey,
    rotateKey,
    revokeKey,
  } = useApiKeys(token, !authLoading && !!user)

  if (authLoading) {
    return (
      <div style={{ padding: '24px 0' }}>
        <Skeleton height="2rem" width="300px" className="mb-6" />
        <Skeleton height="180px" className="mb-4" />
        <Skeleton height="120px" className="mb-4" />
      </div>
    )
  }

  return (
    <div style={{ padding: '24px 0' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 12,
          background: 'linear-gradient(135deg, var(--accent-hover), var(--accent-fill))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="code" size={20} style={{ color: 'var(--text-on-accent)' }} />
        </div>
        <div>
          <h1 className="page-title">
            پلتفرم توسعه‌دهندگان
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>
            API سازگار با OpenAI برای ادغام در اپلیکیشن‌های شما
          </p>
        </div>
      </div>

      <ApiInfoCard />

      {user && (
        <ApiKeysSection
          keys={keys}
          newKeyName={newKeyName}
          setNewKeyName={setNewKeyName}
          keyLoading={keyLoading}
          onCreate={createKey}
          revokingId={revokingId}
          rotatingId={rotatingId}
          onRotate={rotateKey}
          onRevoke={revokeKey}
        />
      )}

      <CodeExamplesSection />

      <EndpointDocsSection />

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <ApiKeyRevealModal
        open={reveal !== null}
        rawKey={reveal?.key ?? null}
        isRotation={reveal?.isRotation ?? false}
        onAcknowledge={() => setReveal(null)}
      />
    </div>
  )
}
