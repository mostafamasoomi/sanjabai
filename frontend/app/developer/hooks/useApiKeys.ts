import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { FORBIDDEN_MESSAGE } from '../constants'
import { type ApiKeyInfo } from '../types'

/** Fetches/creates/rotates/revokes the user's API keys. `ready` gates the
    initial fetch until auth has resolved and a user is present, matching
    the page's previous `!authLoading && user` effect condition. */
export function useApiKeys(token: string | null, ready: boolean) {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])
  const [newKeyName, setNewKeyName] = useState('')
  const [keyLoading, setKeyLoading] = useState(false)
  const [revokingId, setRevokingId] = useState<number | null>(null)
  const [rotatingId, setRotatingId] = useState<number | null>(null)
  // Full raw key only ever lives here, right after create/rotate — never derived from the key list.
  const [reveal, setReveal] = useState<{ key: string; isRotation: boolean } | null>(null)

  const headers = useCallback(() => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }), [token])

  const fetchKeys = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch('/api/api-keys', { headers: headers() })
      if (r.ok) {
        const data = await r.json()
        // Backend may return array or paginated {items: [...]} format
        setKeys(Array.isArray(data) ? data : (data?.items ?? []))
      } else {
        toast('خطا در دریافت کلیدهای API', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    }
  }, [token, headers])

  useEffect(() => {
    if (ready) fetchKeys()
  }, [ready, fetchKeys])

  const createKey = async () => {
    if (!newKeyName.trim()) {
      toast('نام کلید را وارد کنید', 'error')
      return
    }
    setKeyLoading(true)
    try {
      const r = await apiFetch('/api/api-keys', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ name: newKeyName }),
      })
      if (r.status === 403) { toast(FORBIDDEN_MESSAGE, 'error'); return }
      const data = await r.json()
      if (r.ok) {
        setReveal({ key: data.key, isRotation: false })
        setNewKeyName('')
        fetchKeys()
      } else {
        toast(data.detail || 'خطا', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    } finally {
      setKeyLoading(false)
    }
  }

  const rotateKey = async (id: number) => {
    if (!confirm('با چرخاندن این کلید، کلید فعلی بلافاصله از کار می‌افتد و باید کلید جدید را در همه جا جایگزین کنید. ادامه می‌دهید؟')) return
    setRotatingId(id)
    try {
      const r = await apiFetch(`/api/api-keys/${id}/rotate`, {
        method: 'POST', headers: headers(),
      })
      if (r.status === 403) { toast(FORBIDDEN_MESSAGE, 'error'); return }
      const data = await r.json()
      if (r.ok) {
        setReveal({ key: data.key, isRotation: true })
        fetchKeys()
      } else {
        toast(data.detail || 'خطا', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    } finally {
      setRotatingId(null)
    }
  }

  const revokeKey = async (id: number) => {
    if (!confirm('آیا از غیرفعال کردن این کلید مطمئن هستید؟')) return
    setRevokingId(id)
    try {
      const r = await apiFetch(`/api/api-keys/${id}`, {
        method: 'DELETE', headers: headers(),
      })
      if (r.status === 403) { toast(FORBIDDEN_MESSAGE, 'error'); return }
      if (r.ok) {
        toast('کلید غیرفعال شد', 'success')
        fetchKeys()
      }
    } catch {
      toast('خطا', 'error')
    } finally {
      setRevokingId(null)
    }
  }

  return {
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
  }
}
