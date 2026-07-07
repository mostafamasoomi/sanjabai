const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
async function request(path: string, opts: RequestInit = {}) {
 const url = new URL(path, BASE)
 const res = await fetch(url.toString(), { ...opts, headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) } })
 if (!res.ok) { const t = await res.text().catch(() => ''); throw new Error(t || res.statusText) }
 const ct = res.headers.get('content-type') || ''
 return ct.includes('application/json') ? res.json() : res.text()
}
export async function sendChat(payload: { model: string; messages: Array<{ role: string; content: string }>; user_id: number; stream?: boolean }) {
 return request('/v1/chat/completions', { method: 'POST', body: JSON.stringify(payload) })
}
export async function getModels() { return request('/v1/models') }
export async function getUsage(user_id: number) { return request('/me/usage?user_id=' + encodeURIComponent(user_id)) }
export async function meter(payload: { user_id: number; model: string; prompt_tokens: number; completion_tokens: number }) {
 return request('/admin/meter', { method: 'POST', headers: { 'X-Internal-Token': process.env.NEXT_PUBLIC_INTERNAL_TOKEN || '' }, body: JSON.stringify(payload) })
}
