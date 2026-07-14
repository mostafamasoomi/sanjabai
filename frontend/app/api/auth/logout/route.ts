import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export async function POST(request: Request) {
  try {
    const auth = request.headers.get('Authorization') || ''
    const res = await fetch(`${API}/auth/logout`, {
      method: 'POST',
      headers: { Authorization: auth },
    })
    return NextResponse.json({ status: 'ok' }, { status: res.status })
  } catch {
    return NextResponse.json({ status: 'ok' })
  }
}