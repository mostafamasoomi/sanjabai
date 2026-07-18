'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'

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

const DOC_TYPES = [
  {
    id: 'pptx' as DocType,
    label: 'PowerPoint',
    icon: '📊',
    desc: 'ارائه حرفه‌ای با اسلایدهای زیبا',
    color: '#E74C3C',
  },
  {
    id: 'docx' as DocType,
    label: 'Word',
    icon: '📄',
    desc: 'سند متنی با ساختار حرفه‌ای',
    color: '#2B579A',
  },
  {
    id: 'mdx' as DocType,
    label: 'Markdown Slides',
    icon: '📝',
    desc: 'اسلاید Markdown (Marp/reveal.js)',
    color: '#00B4D8',
  },
]

export default function DocumentsPage() {
  const { token } = useAuth()
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
      .then(r => r.json())
      .then(d => setHistory(d.documents || []))
      .catch(() => {})
      .finally(() => setLoadingHistory(false))
  }, [token])

  const handleGenerate = async () => {
    if (!prompt.trim() || !token) return
    setGenerating(true)
    setError('')
    setResult(null)

    try {
      const res = await fetch('/v1/documents/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ prompt: prompt.trim(), type: docType }),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.error?.message || 'خطا در تولید سند')
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
      setError(e instanceof Error ? e.message : 'خطای ناشناخته')
    } finally {
      setGenerating(false)
    }
  }

  const handleDelete = async (docId: string) => {
    if (!token) return
    try {
      await fetch(`/v1/documents/${docId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      setHistory(prev => prev.filter(d => d.id !== docId))
    } catch {}
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString('fa-IR', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  const suggestions = [
    'یک ارائه درباره آینده هوش مصنوعی بساز',
    'گزارش تحلیلی بازار ارز دیجیتال',
    'مقاله درباره بهترین شیوه‌های توسعه نرم‌افزار',
    'ارائه معرفی استارتاپ Multiai',
    'سند نقشه راه محصول ۱۴۰۵',
  ]

  // Auth gate — documents require login
  if (!token) {
    return (
      <div className="flex justify-center items-center min-h-[60vh]" dir="rtl">
        <div className="card" style={{ textAlign: 'center', padding: '48px 32px', maxWidth: 400 }}>
          <h2 className="text-xl font-bold mb-2">سندساز</h2>
          <p className="text-muted mb-6">
            برای ساخت پاورپوینت، ورد یا اسلاید با هوش مصنوعی، ابتدا وارد حساب خود شوید.
          </p>
 <a href="/login" className="btn btn-lg btn-primary inline-flex items-center gap-2" >
            ورود / ثبت‌نام
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="page-container" dir="rtl">
      <div className="content-wrapper">
        {/* Header */}
        <div className="section-header">
          <h1 className="page-title">
            <span style={{ fontSize: '1.5em' }}>📝</span> تولید سند با هوش مصنوعی
          </h1>
          <p className="page-subtitle">
            ارائه PowerPoint، سند Word یا اسلاید Markdown با یک پرامپت بسازید
          </p>
        </div>

        {/* Format selector */}
 <div className="card mb-6" >
          <div className="card-header">نوع سند</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
            {DOC_TYPES.map(dt => (
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
 <div className="card mb-6" >
          <div className="card-header">توضیحات سند</div>
          <textarea dir="rtl"
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="توضیح دهید چه سندی می‌خواهید... مثال: یک ارائه ۱۰ اسلایدی درباره آینده AI"
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
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => setPrompt(s)}
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
                {s}
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
              در حال تولید سند...
            </span>
          ) : (
            `ساخت ${DOC_TYPES.find(d => d.id === docType)?.label}`
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
            <div className="flex items-center gap-4 mb-4">
              <span style={{ fontSize: '2.5rem' }}>
                {DOC_TYPES.find(d => d.id === result.type)?.icon}
              </span>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.25rem' }}>{result.title}</h3>
                <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                  {result.type === 'pptx' && `${result.slides_count} اسلاید`}
                  {result.type === 'docx' && `${result.sections_count} بخش`}
                  {result.type === 'mdx' && `${result.slides_count} اسلاید`}
                  {' · '}
                  {formatSize(result.file_size)}
                  {' · '}
                  {result.generation_time} ثانیه
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
              ⬇️ دانلود فایل
            </a>
          </div>
        )}

        {/* History */}
        <div className="card">
          <div className="card-header">
            سوابق تولید
            {loadingHistory && <span style={{ fontSize: '0.8rem', marginRight: '0.5rem' }}>...</span>}
          </div>
          {history.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
              هنوز سندی تولید نشده
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
                    <span className="text-2xl">
                      {DOC_TYPES.find(d => d.id === doc.type)?.icon}
                    </span>
                    <div>
                      <div className="font-medium">{doc.title}</div>
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
