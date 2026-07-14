import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://multiai-multiai_api-1:8000'

export async function GET(request: Request) {
  try {
    const auth = request.headers.get('Authorization') || ''
    // Forward cookies from the browser request so cookie-based auth works as fallback
    const cookies = request.headers.get('Cookie') || ''
    const res = await fetch(`${API}/auth/me`, {
      headers: {
        Authorization: auth,
        ...(cookies ? { Cookie: cookies } : {}),
      },
    })
    const data = await res.json()
    const response = NextResponse.json(data, { status: res.status })
    // Forward Set-Cookie from backend (e.g. refreshed session cookie TTL)
    const setCookie = res.headers.get('set-cookie')
    if (setCookie) {
      response.headers.set('Set-Cookie', setCookie)
    }
    return response
  } catch {
    return NextResponse.json({ detail: 'failed' }, { status: 500 })
  }
}