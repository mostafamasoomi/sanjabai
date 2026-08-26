'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt, dirFor } from '@/lib/i18n'
import { documentsPageStrings } from './page.strings'

type DocType = 'pptx' | 'docx' | 'mdx'

interface GeneratedDoc {
  id: string
  type: DocType
  title: string
  filename: string
  file_size: number
  generation_time: number
  slides_count: number
  sections_count: number
  download_url: string
}

interface DocHistory {
  id: string
  type: DocType
  title: string
  prompt: string
  file_size: number
  created_at: string
}

const DOC_TYPE_META: Record<DocType, { icon: string; color: string }> = {
  pptx: { icon: '📊', color: '#E74C3C' },
  docx: { icon: '📄', color: '#2B579A' },
  mdx: { icon: '📝', color: '#00B4D8' },
}

function docTypes(s: ReturnType<typeof documentsPageStrings>) {
  return (Object.keys(DOC_TYPE_META) as DocType[]).map((id) => ({
    id,
    ...DOC_TYPE_META[id],
    label: s.docTypes[id].label,
    desc: s.docTypes[id].desc,
  }))
}

export default function DocumentsPage() {
  const { token } = useAuth()
  const lang = useLang()
  const s = documentsPageStrings(lang)
  const f = fmt(lang)
  const types = docTypes(s)
  const [prompt, setPrompt] = useState('')
  const [docType, setDocType] = useState<DocType>('pptx')
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<GeneratedDoc | null>(null)
  const [error, setError] = useState('')
  const [history, setHistory] = useState<DocHistory[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  // Load history
  useEffect(() => {
    if (!token) return
    setLoadingHistory(true)
    fetch('/v1/documents', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => {
        if (!r.ok) throw new Error('failed')
        return r.json()
      })
      .then(d => setHistory(d.documents || []))
      .catch(() => toast(s.historyLoadError, 'error'))
      .finally(() => setLoadingHistory(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const handleGenerate = async () => {
    if (!prompt.trim() || !token) return
    setGenerating(true)
    setError('')
    setResult(null)

    try {
      const res = await apiFetch('/v1/documents/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ prompt: prompt.trim(), type: docType }),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.error?.message || s.genericGenerateError)
      }

      const data: GeneratedDoc = await res.json()
      setResult(data)

      // Refresh history
      const histRes = await fetch('/v1/documents', {
        headers: { Authorization: `Bearer ${token}` },
      })
      const histData = await histRes.json()
      setHistory(histData.documents || [])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : s.unknownError)
    } finally {
      setGenerating(false)
    }
  }

  const handleDelete = async (docId: string) => {
    if (!token) return
    // Optimistic removal used to happen unconditionally, before checking the
    // response — a 404/500 from the backend still emptied the row out of the
    // list, so a failed delete looked successful. Remove only after `res.ok`,
    // and surface an error (with the row intact) otherwise.
    try {
      const res = await apiFetch(`/v1/documents/${docId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        setHistory(prev => prev.filter(d => d.id !== docId))
      } else {
        toast(s.deleteFailed, 'error')
      }
    } catch {
      toast(s.networkError, 'error')
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (iso: string) => f.date(iso, iso)

  const suggestions = s.suggestions

  // Auth gate — documents require login
  if (!token) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }} dir={dirFor(lang)}>
        <div className="card" style={{ textAlign: 'center', padding: '48px 32px', maxWidth: 400 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>{s.loginTitle}</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>
            {s.loginBody}
          </p>
          <a href="/login" className="btn btn-lg btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {s.loginCta}
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="page-container" dir={dirFor(lang)}>
      <div className="content-wrapper">
        {/* Header */}
        <div className="section-header">
          <h1 className="page-title">
            <span style={{ fontSize: '1.5em' }}>📝</span> {s.pageTitle}
          </h1>
          <p className="page-subtitle">
            {s.pageSubtitle}
          </p>
        </div>

        {/* Format selector */}
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">{s.docTypeCardHeader}</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
            {types.map(dt => (
              <button
                key={dt.id}
                onClick={() => setDocType(dt.id)}
                style={{
                  padding: '1.25rem',
                  border: `2px solid ${docType === dt.id ? dt.color : 'var(--border)'}`,
                  borderRadius: 'var(--radius-lg)',
                  background: docType === dt.id ? `${dt.color}10` : 'var(--surface)',
                  cursor: 'pointer',
                  textAlign: 'center',
                  transition: 'all 0.2s',
                }}
              >
                <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>{dt.icon}</div>
                <div style={{ fontWeight: 600, color: docType === dt.id ? dt.color : 'var(--text)' }}>
                  {dt.label}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                  {dt.desc}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Prompt input */}
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">{s.promptCardHeader}</div>
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder={s.promptPlaceholder}
            rows={4}
            style={{
              width: '100%',
              padding: '1rem',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg)',
              color: 'var(--text)',
              fontSize: '1rem',
              resize: 'vertical',
              fontFamily: 'var(--font-sans)',
            }}
          />

          {/* Suggestions */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.75rem' }}>
            {suggestions.map((suggestion, i) => (
              <button
                key={i}
                onClick={() => setPrompt(suggestion)}
                style={{
                  padding: '0.35rem 0.75rem',
                  border: '1px solid var(--border)',
                  borderRadius: '999px',
                  background: 'var(--surface)',
                  color: 'var(--text-muted)',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                }}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>

        {/* Generate button */}
        <button
          onClick={handleGenerate}
          disabled={!prompt.trim() || generating}
          style={{
            width: '100%',
            padding: '1rem',
            border: 'none',
            borderRadius: 'var(--radius-lg)',
            background: generating ? 'var(--border)' : 'var(--accent)',
            color: 'var(--text-on-accent)',
            fontSize: '1.1rem',
            fontWeight: 600,
            cursor: generating ? 'not-allowed' : 'pointer',
            marginBottom: '1.5rem',
            transition: 'all 0.2s',
          }}
        >
          {generating ? (
            <span>
              <span className="spinner" style={{ display: 'inline-block', marginLeft: '0.5rem' }} />
              {s.generating}
            </span>
          ) : (
            s.generateButton(types.find(d => d.id === docType)?.label ?? '')
          )}
        </button>

        {/* Error */}
        {error && (
          <div
            style={{
              padding: '1rem',
              border: '1px solid #E74C3C',
              borderRadius: 'var(--radius-md)',
              background: '#E74C3C10',
              color: '#E74C3C',
              marginBottom: '1.5rem',
            }}
          >
            ❌ {error}
          </div>
        )}

        {/* Result */}
        {result && (
          <div
            className="card"
            style={{
              marginBottom: '1.5rem',
              border: '2px solid var(--accent)',
              background: 'var(--accent)08',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
              <span style={{ fontSize: '2.5rem' }}>
                {types.find(d => d.id === result.type)?.icon}
              </span>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.25rem' }}>{result.title}</h3>
                <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                  {result.type === 'pptx' && s.slidesCount(f.num(result.slides_count))}
                  {result.type === 'docx' && s.sectionsCount(f.num(result.sections_count))}
                  {result.type === 'mdx' && s.slidesCount(f.num(result.slides_count))}
                  {' · '}
                  {formatSize(result.file_size)}
                  {' · '}
                  {s.seconds(f.num(result.generation_time))}
                </p>
              </div>
            </div>

            <a
              href={result.download_url}
              download
              style={{
                display: 'block',
                textAlign: 'center',
                padding: '0.85rem',
                borderRadius: 'var(--radius-md)',
                background: 'var(--accent)',
                color: 'var(--text-on-accent)',
                fontWeight: 600,
                textDecoration: 'none',
                fontSize: '1rem',
              }}
            >
              ⬇️ {s.download}
            </a>
          </div>
        )}

        {/* History */}
        <div className="card">
          <div className="card-header">
            {s.historyHeader}
            {loadingHistory && <span style={{ fontSize: '0.8rem', marginRight: '0.5rem' }}>...</span>}
          </div>
          {history.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
              {s.noHistory}
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {history.map(doc => (
                <div
                  key={doc.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.85rem',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--surface)',
                  }}
                >
                  <div className="flex items-center gap-3">
                    <span style={{ fontSize: '1.5rem' }}>
                      {types.find(d => d.id === doc.type)?.icon}
                    </span>
                    <div>
                      <div style={{ fontWeight: 500 }}>{doc.title}</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {formatDate(doc.created_at)} · {formatSize(doc.file_size)}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <a
                      href={`/v1/documents/${doc.id}/download`}
                      style={{
                        padding: '0.4rem 0.8rem',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)',
                        background: 'var(--bg)',
                        color: 'var(--text)',
                        textDecoration: 'none',
                        fontSize: '0.85rem',
                      }}
                    >
                      ⬇️
                    </a>
                    <button
                      onClick={() => handleDelete(doc.id)}
                      style={{
                        padding: '0.4rem 0.8rem',
                        border: '1px solid #E74C3C40',
                        borderRadius: 'var(--radius-sm)',
                        background: '#E74C3C10',
                        color: '#E74C3C',
                        cursor: 'pointer',
                        fontSize: '0.85rem',
                      }}
                    >
                      🗑️
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <style jsx>{`
        .spinner {
          width: 18px;
          height: 18px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: 'var(--text-on-accent)';
          border-radius: 50%;
          animation: spin 0.6s linear infinite;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
