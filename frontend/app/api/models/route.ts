import { NextResponse } from 'next/server'
const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
export const runtime = 'nodejs';
export async function GET() {
  try {
    const res = await fetch(`${API}/v1/models`, { cache: 'no-store' });
    if (!res.ok) return NextResponse.json({ error: `upstream ${res.status}` }, { status: 200 });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e: any) {
    return NextResponse.json({ object: 'list', data: [], err: String(e?.message || e) }, { status: 200 });
  }
}
