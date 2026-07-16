export const runtime = 'nodejs'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const upstream = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
    const auth = request.headers.get('Authorization') || ''

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    }
    if (auth) headers['Authorization'] = auth

    const res = await fetch(`${upstream}/v1/compare`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })

    const data = await res.json()
    return new Response(JSON.stringify(data), {
      status: res.status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch (e) {
    return new Response(JSON.stringify({ detail: 'compare proxy failed' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}