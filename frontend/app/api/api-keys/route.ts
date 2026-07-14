import { NextRequest, NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export async function GET(request: NextRequest) {
  try {
    const auth = request.headers.get('authorization') || ''
    const r = await fetch(`${API}/api-keys`, { headers: { Authorization: auth } })
    const data = await r.json()
    return NextResponse.json(data, { status: r.status })
  } catch {
    return NextResponse.json({ detail: 'service unavailable' }, { status: 502 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const auth = request.headers.get('authorization') || ''
    const r = await fetch(`${API}/api-keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: auth },
      body: JSON.stringify(body),
    })
    const data = await r.json()
    return NextResponse.json(data, { status: r.status })
  } catch {
    return NextResponse.json({ detail: 'service unavailable' }, { status: 502 })
  }
}