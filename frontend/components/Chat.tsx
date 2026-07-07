"use client"
import { useState } from "react"
export default function Chat({ user_id = 1 }: { user_id?: number }) {
 const [messages, setMessages] = useState([{ role: "assistant", content: "سلام، چطور می‌تونم کمک کنم؟" }])
 const [input, setInput] = useState("")
 const [model, setModel] = useState("gpt-4o-mini")
 const [loading, setLoading] = useState(false)
 async function onSubmit(e: React.FormEvent) {
  e.preventDefault(); if (!input.trim()) return
  const next = [...messages, { role: "user", content: input }]
  setMessages(next); setInput(""); setLoading(true)
  try {
   const base = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
   const res = await fetch(`${base}/v1/chat/completions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model, messages: next, user_id, stream: true }) })
   if (!res.ok) throw new Error(String(res.status))
   const reader = res.body?.getReader(); const decoder = new TextDecoder()
   setMessages(m => [...m, { role: "assistant", content: "" }])
   let acc = ""
   while (true) {
    const { value, done } = await reader!.read(); if (done) break
    const chunk = decoder.decode(value)
    const events = chunk.split(/\r?\n/).reduce<{data?:string}>((acc, line) => { const t = line.trim(); if (!t) return acc; if (t.startsWith("data:")) { acc.data = t.slice(5).trim() } return acc }, {})
    if (events.data && events.data !== "[DONE]") { try {
      const obj = JSON.parse(events.data || ""); const delta = obj.choices?.[0]?.delta?.content; if (delta) acc += delta
    } catch {} }
    setMessages(m => { const copy = [...m]; copy[copy.length-1] = { role: "assistant", content: acc || "" }; return copy })
   }
  } catch { setMessages(m => [...m, { role: "assistant", content: "خطا در ارتباط" }]) }
  finally { setLoading(false) }
 }
 return (
  <div className="flex h-[calc(100vh-4rem)] flex-col border rounded-2xl overflow-hidden">
   <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-white">{messages.map((m,i) => (
    <div key={i} className={m.role==="user"?"text-left":"text-right"}>
     <span className={"inline-block rounded-2xl px-3 py-2 text-sm " + (m.role==="user"?"bg-blue-600 text-white":"bg-gray-100 text-gray-900")}>{m.content || "..."}</span>
    </div>
   ))}</div>
   <form onSubmit={onSubmit} className="border-t p-3 flex gap-2 bg-white">
    <input value={input} onChange={e=>setInput(e.target.value)} placeholder="پیام خود را بنویسید..." className="flex-1 rounded-xl border px-3 py-2 text-sm focus:outline-none focus:ring-2" />
    <select value={model} onChange={e=>setModel(e.target.value)} className="rounded-xl border px-2 text-sm">
     <option value="gpt-4o-mini">GPT-4o mini</option>
     <option value="gpt-4o">GPT-4o</option>
     <option value="claude-3.5-sonnet">Claude 3.5</option>
    </select>
    <button disabled={loading} className="rounded-xl bg-gray-900 text-white px-4 text-sm py-2 disabled:opacity-50">ارسال</button>
   </form>
  </div>
 )
}
