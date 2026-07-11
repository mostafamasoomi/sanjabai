export interface SSEEvent {
  event?: string
  data?: string
}

export function parseSSE(text: string): SSEEvent[] {
  const events: SSEEvent[] = []
  let current: SSEEvent = {}

  for (const line of text.split(/\r?\n/)) {
    const t = line.trim()
    if (!t) {
      if (current.event || current.data) events.push(current)
      current = {}
      continue
    }
    const idx = t.indexOf(':')
    if (idx < 0) continue
    const field = t.slice(0, idx).trim()
    const value = t.slice(idx + 1).trim()
    if (field === 'data') current.data = value
    if (field === 'event') current.event = value
  }
  if (current.event || current.data) events.push(current)
  return events
}
