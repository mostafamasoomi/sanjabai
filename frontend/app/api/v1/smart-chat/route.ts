export const runtime = 'nodejs'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const upstream = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
    const auth = request.headers.get('Authorization') || ''
    const smartModel = request.headers.get('X-Smart-Model') || ''

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': body.stream ? 'text/event-stream' : 'application/json',
    }
    if (auth) headers['Authorization'] = auth
    if (smartModel) headers['X-Smart-Model'] = smartModel

    const res = await fetch(`${upstream}/v1/smart-chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })

    // For streaming, pass through the raw response
    if (body.stream && res.ok) {
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

    const data = await res.json()
    return new Response(JSON.stringify(data), {
      status: res.status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch (e) {
    return new Response(JSON.stringify({ detail: 'smart-chat proxy failed' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}
