import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://multiai-multiai_api-1:8000'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    const response = NextResponse.json(data, { status: res.status })
    // Forward Set-Cookie from backend so the browser gets the session cookie
    // as a fallback auth mechanism alongside the localStorage token.
    const setCookie = res.headers.get('set-cookie')
    if (setCookie) {
      response.headers.set('Set-Cookie', setCookie)
    }
    return response
  } catch {
    return NextResponse.json({ detail: 'login failed' }, { status: 500 })
  }
}