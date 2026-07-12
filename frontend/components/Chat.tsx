"use client"
import { useState, useEffect, useCallback } from "react"
import { useCatalog } from "@/lib/useCatalog"

export default function Chat({ user_id = 1 }: { user_id?: number }) {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: "assistant", content: "سلام، چطور میتونم کمک کنم؟" },
  ])
  const [input, setInput] = useState("")
  const [model, setModel] = useState("")
  const { models, loading: catalogLoading } = useCatalog()
  const [loading, setLoading] = useState(false)
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)

  useEffect(() => {
    if (!model && models.length > 0) setModel(models[0].id)
  }, [models, model])

  const copyMessage = useCallback(async (idx: number, content: string) => {
    await navigator.clipboard.writeText(content)
    setCopiedIdx(idx)
    setTimeout(() => setCopiedIdx(null), 2000)
  }, [])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim() || !model) return
    const next = [...messages, { role: "user", content: input }]
    setMessages(next)
    setInput("")
    setLoading(true)
    try {
      const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
      const res = await fetch(`${base}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model, messages: next, user_id, stream: true }),
      })
      if (!res.ok) throw new Error(String(res.status))
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      setMessages((m) => [...m, { role: "assistant", content: "" }])
      let acc = ""
      while (true) {
        const { value, done } = await reader!.read()
        if (done) break
        const chunk = decoder.decode(value)
        const events = chunk
          .split(/\r?\n/)
          .reduce<{ data?: string }>((acc, line) => {
            const t = line.trim()
            if (!t) return acc
            if (t.startsWith("data:")) {
              acc.data = t.slice(5).trim()
            }
            return acc
          }, {})
        if (events.data && events.data !== "[DONE]") {
          try {
            const obj = JSON.parse(events.data || "")
            const delta = obj.choices?.[0]?.delta?.content
            if (delta) acc += delta
          } catch {}
        }
        setMessages((m) => {
          const copy = [...m]
          copy[copy.length - 1] = { role: "assistant", content: acc || "" }
          return copy
        })
      }
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: "خطا در ارتباط" }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="chat-page">
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-row ${m.role === "user" ? "chat-row-user" : "chat-row-assistant"}`}>
            {m.role === "assistant" && (
              <div className="chat-avatar chat-avatar-ai">AI</div>
            )}
            <div className={`chat-bubble ${m.role === "user" ? "chat-bubble-user" : "chat-bubble-ai"}`}>
              {m.role === "assistant" && loading && i === messages.length - 1 && !m.content ? (
                <div className="chat-typing">
                  <span /><span /><span />
                </div>
              ) : (
                <div className="chat-bubble-content">{m.content}</div>
              )}
              {m.role === "assistant" && m.content && !loading && (
                <div className="chat-actions">
                  <button
                    onClick={() => copyMessage(i, m.content)}
                    className="chat-action-btn"
                    title="کپی"
                  >
                    {copiedIdx === i ? "✓ کپی شد" : "کپی"}
                  </button>
                </div>
              )}
            </div>
            {m.role === "user" && (
              <div className="chat-avatar chat-avatar-user">U</div>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={onSubmit} className="chat-composer">
        <div className="chat-composer-box">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="پیام خود را بنویسید..."
            className="chat-composer-input"
          />
          <button
            disabled={loading || !model}
            className="btn btn-primary btn-icon rounded-xl shrink-0"
          >
            ارسال
          </button>
        </div>
        <div className="chat-composer-footer">
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="model-select"
          >
            {catalogLoading && (
              <option value="" disabled>
                در حال بارگذاری...
              </option>
            )}
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.displayName}
              </option>
            ))}
          </select>
        </div>
      </form>
    </div>
  )
}
