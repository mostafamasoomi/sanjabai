const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const auth = request.headers.get('Authorization') || ''
    const { id } = await params
    const url = new URL(request.url)
    const format = url.searchParams.get('format') || 'json'

    const res = await fetch(`${API}/conversations/${id}/export?format=${format}`, {
      headers: { Authorization: auth },
    })

    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: 'export failed' }))
      return new Response(JSON.stringify(data), {
        status: res.status,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    // Pass through the file response
    const contentType = res.headers.get('content-type') || 'application/json'
    const body = await res.arrayBuffer()
    return new Response(body, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': res.headers.get('content-disposition') || '',
      },
    })
  } catch {
    return new Response(JSON.stringify({ detail: 'export proxy failed' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}
