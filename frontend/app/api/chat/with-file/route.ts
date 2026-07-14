export const runtime = 'nodejs'

/* Proxy multipart chat-with-file to the backend /v1/chat/with-file.
   Mirrors /api/chat streaming SSE passthrough. */
export async function POST(request: Request) {
  try {
    const form = await request.formData()
    const file = form.get('file')
    const model = (form.get('model') as string) || ''
    const messages = (form.get('messages') as string) || '[]'
    const stream = (form.get('stream') as string) === 'true'
    const auth = request.headers.get('Authorization') || ''
    const upstream = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

    const fd = new FormData()
    if (file) fd.append('file', file)
    fd.append('model', model)
    fd.append('messages', messages)
    fd.append('stream', stream ? 'true' : 'false')

    const headers: Record<string, string> = {
      Accept: stream ? 'text/event-stream' : 'application/json',
    }
    if (auth) headers['Authorization'] = auth

    const res = await fetch(`${upstream}/v1/chat/with-file`, {
      method: 'POST',
      headers,
      body: fd,
    })

    if (stream && res.ok) {
      return new Response(res.body, {
        status: res.status,
        headers: {
          'Content-Type': res.headers.get('content-type') || 'text/event-stream',
          'Cache-Control': 'no-cache, no-transform',
          'Connection': 'keep-alive',
          'X-Accel-Buffering': 'no',
        },
      })
    }

    const data = await res.json().catch(() => ({}))
    return new Response(JSON.stringify(data), {
      status: res.status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch (e) {
    return new Response(JSON.stringify({ detail: 'file chat proxy failed' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}
