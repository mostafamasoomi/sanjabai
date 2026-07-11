import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://multiai-multiai_api-1:8000'

export async function POST(request: Request) {
  try {
    const auth = request.headers.get('Authorization') || ''
    const body = await request.json()
    const res = await fetch(`${API}/wallet/topup`, {
      method: 'POST',
      headers: { Authorization: auth, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ detail: 'failed' }, { status: 500 })
  }
}