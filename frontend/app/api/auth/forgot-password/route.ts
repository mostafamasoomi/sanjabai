import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const res = await fetch(`${API}/auth/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.status })
  } catch {
    // Both languages in one body, the same contract the Python backend uses
    // (backend/i18n.py): `detail` keeps the Persian under its original name
    // for every existing reader, `detail_en` is the sibling the client picks
    // when the UI is in English (lib/i18n.ts::detailFor). This route runs on
    // the server and has no access to the viewer's language, which is
    // precisely why it ships both rather than choosing.
    return NextResponse.json(
      { detail: 'خطا در ارتباط با سرور', detail_en: 'Could not reach the server' },
      { status: 500 },
    )
  }
}
