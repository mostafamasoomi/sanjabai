import { NextRequest, NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url)
    const authority = url.searchParams.get('Authority')
    const status = url.searchParams.get('Status')

    const r = await fetch(`${API}/payment/callback?Authority=${authority}&Status=${status}`)
    const data = await r.json()

    // `redirect` is not a success flag -- the backend sends it on BOTH the
    // success path and the failure path (backend/payment_endpoints.py:138
    // for failure, :211 for success), each already carrying the right query
    // string (`?payment=success` vs `?payment=failed`) and the right page
    // per payment type (wallet/plans/hermes order). Treating "has redirect"
    // as "succeeded" sent cancelled/failed payments to the success screen.
    // Follow the URL the backend computed instead of hardcoding one.
    if (data.redirect) {
      return NextResponse.redirect(data.redirect)
    }

    return NextResponse.json(data, { status: r.status })
  } catch {
    return NextResponse.redirect(new URL('/wallet?payment=error', request.url))
  }
}