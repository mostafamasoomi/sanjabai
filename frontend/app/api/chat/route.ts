export const runtime = 'nodejs'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const upstream = process.env.NEXT_PUBLIC_API_URL || 'http://multiai-multiai_api-1:8000'
    const auth = request.headers.get('Authorization') || ''

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': body.stream ? 'text/event-stream' : 'application/json',
    }
    if (auth) headers['Authorization'] = auth

    const res = await fetch(`${upstream}/v1/chat/completions`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })

    // For streaming, pass through the raw response
    if (body.stream) {
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
    return new Response(JSON.stringify({ detail: 'chat proxy failed' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}