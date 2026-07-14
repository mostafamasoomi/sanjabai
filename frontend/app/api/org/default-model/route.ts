import { NextResponse } from 'next/server'

/**
 * Proxy for the organisation default model endpoint.
 * Public — no auth required.
 */
const API = process.env.NEXT_PUBLIC_API_URL || 'http://multiai-multiai_api-1:8000'
export const runtime = 'nodejs'

export async function GET() {
  try {
    const res = await fetch(`${API}/org/default-model`, { cache: 'no-store' })
    if (!res.ok) {
      return NextResponse.json({ default_model: null }, { status: 200 })
    }
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ default_model: null }, { status: 200 })
  }
}
