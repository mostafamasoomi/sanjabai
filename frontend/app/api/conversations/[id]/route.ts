import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const auth = request.headers.get('Authorization') || ''
    const { id } = await params
    const res = await fetch(`${API}/conversations/${id}`, { headers: { Authorization: auth } })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch { return NextResponse.json({ detail: 'failed' }, { status: 500 }) }
}

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const auth = request.headers.get('Authorization') || ''
    const { id } = await params
    const body = await request.json()
    const res = await fetch(`${API}/conversations/${id}`, {
      method: 'PUT',
      headers: { Authorization: auth, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return NextResponse.json({ status: 'ok' }, { status: res.status })
  } catch { return NextResponse.json({ detail: 'failed' }, { status: 500 }) }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const auth = request.headers.get('Authorization') || ''
    const { id } = await params
    const res = await fetch(`${API}/conversations/${id}`, {
      method: 'DELETE',
      headers: { Authorization: auth },
    })
    return NextResponse.json({ status: 'ok' }, { status: res.status })
  } catch { return NextResponse.json({ detail: 'failed' }, { status: 500 }) }
}