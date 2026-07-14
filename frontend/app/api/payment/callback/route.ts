import { NextRequest, NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://multiai-multiai_api-1:8000'

export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url)
    const authority = url.searchParams.get('Authority')
    const status = url.searchParams.get('Status')

    const r = await fetch(`${API}/payment/callback?Authority=${authority}&Status=${status}`)
    const data = await r.json()

    // Redirect to wallet page
    if (data.redirect) {
      return NextResponse.redirect(new URL('/wallet?payment=success', request.url))
    }

    return NextResponse.json(data, { status: r.status })
  } catch {
    return NextResponse.redirect(new URL('/wallet?payment=error', request.url))
  }
}