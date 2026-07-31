import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001'

export const runtime = 'nodejs'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function proxy(req: Request, params: any) {
  const pathStr = params.path.join('/')
  const backendUrl = `${API}/${pathStr}`

  const url = new URL(req.url)
  const targetUrl = `${backendUrl}${url.search ? '?' + url.searchParams.toString() : ''}`

  const headers = new Headers()
  const passHeaders = ['authorization', 'content-type', 'cookie', 'x-requested-with']
  for (const h of passHeaders) {
    const v = req.headers.get(h)
    if (v) headers.set(h, v)
  }

  const init: RequestInit = {
    method: req.method,
    headers,
  }

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    init.body = await req.arrayBuffer()
  }

  try {
    const res = await fetch(targetUrl, init)
    const resHeaders = new Headers()
    const ct = res.headers.get('content-type')
    if (ct) resHeaders.set('content-type', ct)
    const sc = res.headers.get('set-cookie')
    if (sc) resHeaders.set('set-cookie', sc)

    return new NextResponse(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers: resHeaders,
    })
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 })
  }
}

export async function GET(req: Request, ctx: any) { return proxy(req, ctx.params) }
export async function POST(req: Request, ctx: any) { return proxy(req, ctx.params) }
export async function PUT(req: Request, ctx: any) { return proxy(req, ctx.params) }
export async function DELETE(req: Request, ctx: any) { return proxy(req, ctx.params) }