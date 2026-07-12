import { NextResponse } from 'next/server'

/**
 * Proxy for the live model catalog.
 *
 * The browser-facing catalog contract is the backend `/catalog/models` endpoint,
 * which returns the approved `ModelCatalogItem[]` shape
 * ({ data, generatedAt, source }). The backend `/v1/models` endpoint is only a raw
 * LiteLLM passthrough and does NOT contain the fields the UI needs
 * (displayName, provider, contextWindow, capabilities, availability, pricing), so it
 * is intentionally not used here.
 *
 * Mirrors the existing proxy convention in app/api/models/route.ts — always responds
 * 200 so the client can degrade to an empty/error state gracefully.
 */
const API = process.env.NEXT_PUBLIC_API_URL || 'http://multiai-multiai_api-1:8000'
export const runtime = 'nodejs'

export async function GET() {
  try {
    const res = await fetch(`${API}/catalog/models`, { cache: 'no-store' })
    if (!res.ok) {
      return NextResponse.json({ data: [], source: 'unavailable' }, { status: 200 })
    }
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (e: any) {
    return NextResponse.json(
      { data: [], source: 'unavailable', err: String(e?.message || e) },
      { status: 200 },
    )
  }
}
