import { NextResponse } from 'next/server'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || '';

export async function GET() {
  try {
    const headers: Record<string, string> = {};
    if (ADMIN_TOKEN) headers['x-admin-token'] = ADMIN_TOKEN;
    const res = await fetch(`${API}/admin/pricing`, { headers });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json([], { status: 200 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (ADMIN_TOKEN) headers['x-admin-token'] = ADMIN_TOKEN;
    const res = await fetch(`${API}/admin/pricing`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json({ detail: 'failed' }, { status: 500 });
  }
}