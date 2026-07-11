import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://multiai-multiai_api-1:8000'

export async function GET(request: Request) {
  try {
    const auth = request.headers.get('Authorization') || ''
    const res = await fetch(`${API}/wallet`, { headers: { Authorization: auth } })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ balance: 0 })
  }
}