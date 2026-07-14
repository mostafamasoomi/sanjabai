import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

async function proxy(request: Request, method: string, path: string, body?: any) {
  const auth = request.headers.get('Authorization') || ''
  const headers: Record<string, string> = { Authorization: auth }
  if (body) headers['Content-Type'] = 'application/json'
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}

export async function GET(request: Request) {
  try { return await proxy(request, 'GET', '/assistants') }
  catch { return NextResponse.json([], { status: 200 }) }
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    return await proxy(request, 'POST', '/assistants', body)
  } catch { return NextResponse.json({ detail: 'failed' }, { status: 500 }) }
}
