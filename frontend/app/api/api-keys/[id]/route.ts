import { NextRequest, NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export async function DELETE(request: NextRequest, { params }: { params: { id: string } }) {
  try {
    const auth = request.headers.get('authorization') || ''
    const r = await fetch(`${API}/api-keys/${params.id}`, {
      method: 'DELETE',
      headers: { Authorization: auth },
    })
    const data = await r.json()
    return NextResponse.json(data, { status: r.status })
  } catch {
    return NextResponse.json({ detail: 'service unavailable' }, { status: 502 })
  }
}