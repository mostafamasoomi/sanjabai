# S8 — World-Class UI Design & Competitive Analysis

**Author:** Senior Product Designer (S8)  
**Date:** 2026-07-16  
**Scope:** Chat UX redesign — competitive analysis, feature design, component architecture, micro-interactions  
**Sources:** S1–S7 audits, `frontend/app/chat/page.tsx` (1074 lines), `globals.css` (2786 lines), `styles-chat-sidebar.css` (348 lines)  
**Current UX Score:** 4.5/10 (per S3 Frontend UX Audit)

---

## 1. Competitive Matrix

### 1.1 Feature Comparison

| Feature | ChatGPT | Claude | DeepSeek | Perplexity | Grok | **Multiai Now** | **Multiai Target** |
|---------|---------|--------|----------|------------|------|-----------------|-------------------|
| **Markdown rendering** | ✅ Full | ✅ Full | ✅ Full | ✅ Full | ✅ Full | ❌ Raw text | ✅ Full + RTL |
| **Syntax highlighting** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ + copy button |
| **Model picker** | ✅ Rich cards | ✅ Toggle | N/A (1 model) | N/A | ✅ Toggle | ❌ `<select>` | ✅ Card grid + search |
| **Conversation folders** | ❌ | ✅ Projects | ❌ | ✅ Threads | ❌ | ❌ | ✅ Folders + search |
| **Message edit/retry** | ✅ Both | ✅ Both | ✅ Retry | ✅ Both | ✅ Both | ⚠️ Retry only | ✅ Both |
| **Branching** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | Phase 3 |
| **Canvas/Artifacts** | ✅ Canvas | ✅ Artifacts | ❌ | ❌ | ❌ | ❌ | ✅ Artifacts |
| **File attachments** | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ Basic | ✅ Multi-file + preview |
| **Web search** | ✅ | ✅ Search | ✅ | ✅ Core | ✅ Real-time | ✅ Toggle | ✅ With citations |
| **Voice input** | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ Web Speech API |
| **Custom assistants** | ✅ GPTs | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ Enhanced |
| **Real-time cost** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ Live IRT counter |
| **Keyboard shortcuts** | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ Enter only | ✅ Full suite |
| **RTL/Persian** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ Native |
| **Multi-model** | ❌ (GPT only) | ❌ (Claude only) | ❌ (DS only) | ❌ | ❌ (Grok only) | ✅ 10+ | ✅ 15+ |
| **Dark theme** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ Enhanced |
| **Streaming cursor** | ✅ Blink | ✅ Blink | ✅ Fade | ✅ | ✅ | ❌ | ✅ Blink + speed |
| **Conversation search** | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ FTS |
| **Prompt templates** | ❌ | ❌ | ❌ | ✅ | ❌ | ⚠️ 4 presets | ✅ Library |

### 1.2 Multiai's Unique Advantages

These are the **moats** — no competitor has them:

1. **Multi-model platform** — 15+ models from 8+ providers in one interface. ChatGPT has GPT, Claude has Claude. Multiai has everything.
2. **Persian-first RTL** — No global competitor serves Persian natively. This is the primary market differentiator.
3. **Iran-accessible** — No VPN needed, local payment (Zarinpal), IRT pricing.
4. **Smart Mode** — Auto-selects the best model per prompt. Unique to Multiai.

### 1.3 Critical Gaps vs Every Competitor

The S3 audit identified these correctly. The product is **5 years behind** on two fundamentals:

1. **No Markdown rendering** — Every single AI response is raw text. Code blocks, tables, lists, bold — all invisible. This is the #1 priority.
2. **No syntax highlighting** — Developers will not use a chat tool that can't display code.

---

## 2. Vision Statement

> **Multiai is the Persian ChatGPT — but better, because it has every model.**

A user opens Multiai. They see a sleek dark interface in Persian. They pick a model from a beautiful card grid (or let Smart Mode choose). They type a question. The response streams back with rich markdown, syntax-highlighted code with copy buttons, and a blinking cursor showing tokens/sec. The live cost counter updates in Tomans. They switch models mid-conversation to compare. They organize conversations in folders. They use keyboard shortcuts for everything. They think: "This is what ChatGPT would be if it spoke Farsi and had every model."

---

## 3. The 15 Must-Have Features for WOW MVP

Ordered by impact × effort. Features 1–5 are **launch blockers**. Features 6–10 are **week-2 essentials**. Features 11–15 are **polish**.

### TIER 1 — Launch Blockers (Without these, don't ship)

#### F1. Rich Markdown Rendering + Syntax Highlighting
**Impact: CRITICAL | Effort: 2-3 hours | Deps: react-markdown, rehype-highlight, remark-gfm**

- Install `react-markdown` + `rehype-highlight` + `remark-gfm` + `rehype-raw`
- Replace `<div className="chat-bubble-content">{msg.content}</div>` with `<ReactMarkdown>` component
- Code blocks: dark theme (one-dark-pro or custom matching Aurora), language badge, per-block copy button
- Tables: styled with Aurora design tokens, horizontal scroll on overflow
- Inline code: styled with `--bg-overlay` background
- Links: `--accent` color, `target="_blank"` with icon
- RTL handling: markdown content stays LTR for code/English, RTL for Persian text. Use `dir="auto"` on paragraph elements.
- Images in markdown: max-width 100%, lazy loading, lightbox on click

```tsx
// Target component structure
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import rehypeRaw from 'rehype-raw'

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight, rehypeRaw]}
      components={{
        code({ node, inline, className, children, ...props }) {
          if (inline) return <code className="inline-code" {...props}>{children}</code>
          return <CodeBlock className={className} {...props}>{children}</CodeBlock>
        },
        a({ children, href, ...props }) {
          return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}<ExternalLinkIcon /></a>
        },
        table({ children, ...props }) {
          return <div className="table-scroll"><table {...props}>{children}</table></div>
        },
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

function CodeBlock({ className, children }: { className?: string; children: React.ReactNode }) {
  const [copied, setCopied] = useState(false)
  const lang = className?.replace('language-', '') || ''
  const text = String(children).replace(/\n$/, '')
  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-lang">{lang}</span>
        <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) }}>
          {copied ? <CheckIcon /> : <CopyIcon />}
        </button>
      </div>
      <code className={className}>{children}</code>
    </div>
  )
}
```

CSS additions to `globals.css`:
```css
/* Syntax highlighting — Aurora dark */
.hljs { background: var(--bg-overlay); color: var(--text-primary); padding: var(--space-4); border-radius: var(--radius-md); }
.hljs-keyword { color: #c678dd; }
.hljs-string { color: #98c379; }
.hljs-number { color: #d19a66; }
.hljs-comment { color: #5c6370; font-style: italic; }
.hljs-function { color: #61afef; }
.hljs-built_in { color: #e5c07b; }

.code-block { position: relative; margin: var(--space-3) 0; border-radius: var(--radius-md); overflow: hidden; }
.code-block-header { display: flex; justify-content: space-between; align-items: center; padding: var(--space-2) var(--space-3); background: rgba(0,0,0,0.3); font-size: 12px; color: var(--text-muted); }
.code-lang { text-transform: uppercase; letter-spacing: 0.05em; }
.inline-code { background: var(--bg-overlay); padding: 2px 6px; border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 0.9em; }
.table-scroll { overflow-x: auto; margin: var(--space-3) 0; }
.markdown-content table { border-collapse: collapse; width: 100%; }
.markdown-content th, .markdown-content td { border: 1px solid var(--border); padding: var(--space-2) var(--space-3); text-align: start; }
.markdown-content th { background: var(--bg-elevated); font-weight: 700; }
.markdown-content a { color: var(--accent); text-decoration: none; }
.markdown-content a:hover { text-decoration: underline; }
.markdown-content img { max-width: 100%; border-radius: var(--radius-md); }
.markdown-content blockquote { border-inline-start: 3px solid var(--accent); padding-inline-start: var(--space-4); color: var(--text-secondary); margin: var(--space-3) 0; }
.markdown-content ul, .markdown-content ol { padding-inline-start: var(--space-6); }
.markdown-content li { margin: var(--space-1) 0; }
.markdown-content h1, .markdown-content h2, .markdown-content h3 { margin-top: var(--space-4); margin-bottom: var(--space-2); }
```

#### F2. Rich Card-Based Model Picker
**Impact: CRITICAL | Effort: 4-6 hours | Deps: none (CSS + existing useCatalog)**

Replace the native `<select>` with a searchable card grid. The existing `useCatalog()` hook already provides all data needed: `displayName`, `provider`, `contextWindow`, `pricing`, `capabilities`, `recommendedFor`.

```
┌─────────────────────────────────────────────┐
│  🔍 جستجوی مدل...                  [✕]    │
├─────────────────────────────────────────────┤
│  ⭐ پیشنهادی                                │
│  ┌─────────────────────────────────────────┐│
│  │ 🧠 MiMo V2.5          [openai]    ★   ││
│  │ مناسب برای گفتگوی عمومی · 32K ctx     ││
│  │ ۱,۰۰۰ تومان/۱M توکن ورودی            ││
│  └─────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────┐│
│  │ 💎 Gemini Flash        [google]        ││
│  │ مناسب برای تحلیل · 128K ctx           ││
│  │ ۵۰۰ تومان/۱M توکن ورودی              ││
│  └─────────────────────────────────────────┘│
│                                             │
│  همه مدل‌ها (15)                            │
│  ┌─ Grok 4              [xai]      ───────┐│
│  ┌─ Mistral Large        [mistral]  ───────┐│
│  ┌─ DeepSeek V3          [deepseek] ───────┘│
└─────────────────────────────────────────────┘
```

Component: `ModelPicker.tsx`
- Modal/dropdown triggered by clicking current model name in topbar
- Search input filters by name, provider, capability
- "Recommended" section: models where `recommendedFor` includes common use cases
- Each card: model name (LTR), provider badge, context window, price/token, capability tags
- Current selection has accent border + checkmark
- Keyboard nav: arrow keys to navigate, Enter to select, Escape to close
- Persist selection to `localStorage` (fix the S2 bug where model resets on refresh)
- Group by provider in "All Models" section

#### F3. Streaming Cursor + Token Speed
**Impact: HIGH | Effort: 1-2 hours | Deps: none**

The streaming implementation works (SSE, AbortController, cancel button) but has zero visual feedback.

Add:
1. **Blinking cursor** at the end of streaming text — a simple `|` character with CSS animation
2. **Token speed indicator** — calculate `tokens / elapsed_seconds`, show as "42 tok/s" in the message footer
3. **Smooth scroll** — use `scrollIntoView({ behavior: 'smooth' })` on each token batch instead of jumping

```css
.streaming-cursor::after {
  content: '▋';
  animation: blink 0.8s infinite;
  color: var(--accent);
  margin-inline-start: 2px;
}
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
```

#### F4. Message Edit + Regenerate
**Impact: HIGH | Effort: 2-3 hours | Deps: none**

Current state: only "Copy" and "Retry" on the last assistant message.

Add:
- **Edit button** on user messages — inline edit (replace content with textarea, save re-sends from that point)
- **Regenerate button** on all assistant messages — re-sends the preceding user message with the same model
- Both buttons use the existing `retry` pattern — just slice messages and re-call `sendMessage`

#### F5. Conversation Search + Date Grouping
**Impact: HIGH | Effort: 2-3 hours | Deps: none**

Current sidebar: flat list, no search, no pagination, no grouping.

Add:
- Search input at top of sidebar — filters conversations by title (client-side for now, backend FTS later)
- Date group headers: "امروز" / "دیروز" / "این هفته" / "این ماه" / "قدیمی‌تر"
- Pin to top — long-press or button, stored in localStorage initially

### TIER 2 — Week 2 Essentials

#### F6. Keyboard Shortcuts
**Impact: MEDIUM | Effort: 2-3 hours | Deps: none**

Implement a global shortcut system with a help modal (`Ctrl+/` or `?`).

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` / `Cmd+N` | New chat |
| `Ctrl+K` / `Cmd+K` | Open model picker (already exists as search, wire it) |
| `Ctrl+Shift+C` | Copy last assistant message |
| `Ctrl+/` | Show keyboard shortcuts modal |
| `Escape` | Cancel streaming / close modal / close picker |
| `Ctrl+↑` / `Ctrl+↓` | Navigate conversations in sidebar |
| `@` in input | Mention model/assistant (autocomplete) |

Implementation: single `useEffect` with `document.addEventListener('keydown', ...)` in the chat page. Use a `Map<string, () => void>` for dispatch. Don't add a library — this is 50 lines of code.

#### F7. File Attachment Enhancements
**Impact: MEDIUM | Effort: 3-4 hours | Deps: none**

Current: single file, accept list limited, no preview.

Add:
- **Drag & drop** — `onDragOver`/`onDrop` on the chat area, visual drop zone indicator
- **Multi-file** — change `attachedFile` from single to array
- **File preview** — show image thumbnails, PDF icon, text file first lines
- **File size indicator** — show size next to filename
- **Progress indicator** — upload progress bar during send

#### F8. Voice Input
**Impact: MEDIUM | Effort: 2-3 hours | Deps: none (Web Speech API)**

Use the browser's built-in `SpeechRecognition` API. No backend changes needed.

```tsx
function useVoiceInput(lang = 'fa-IR') {
  const [listening, setListening] = useState(false)
  const [supported] = useState(() => 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window)
  const recognitionRef = useRef<any>(null)

  const start = useCallback((onResult: (text: string) => void) => {
    if (!supported) return
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    const recognition = new SR()
    recognition.lang = lang
    recognition.continuous = false
    recognition.interimResults = true
    recognition.onresult = (e: any) => {
      const text = Array.from(e.results).map((r: any) => r[0].transcript).join('')
      onResult(text)
    }
    recognition.onend = () => setListening(false)
    recognition.onerror = () => setListening(false)
    recognition.start()
    recognitionRef.current = recognition
    setListening(true)
  }, [supported, lang])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
    setListening(false)
  }, [])

  return { listening, supported, start, stop }
}
```

UI: microphone button in the input bar. Pulsing animation when listening. Transcribed text appears in the textarea in real-time.

#### F9. Conversation Folders
**Impact: MEDIUM | Effort: 4-6 hours | Deps: backend endpoint for folder CRUD**

- Sidebar sections: "دسته‌بندی‌ها" (Folders) above the conversation list
- Default folders: "همه" (All), "ستاره‌دار" (Starred)
- User can create/rename/delete folders
- Drag conversation into folder (or right-click → move)
- Backend: add `folder_id` column to conversations table, new `/folders` endpoints

#### F10. Real-Time Cost Display
**Impact: MEDIUM | Effort: 2-3 hours | Deps: model pricing data already in useCatalog**

- Show model price per 1M tokens (input/output) in the model picker
- Live cost counter during streaming: update `estimatedCost` using actual model pricing instead of the hardcoded `totalTokens * 0.000002`
- Show cost in IRT (تومان) with Persian number formatting
- Show wallet balance below the input bar, warn when low

### TIER 3 — Polish (Week 3+)

#### F11. Empty State Redesign
**Impact: LOW-MEDIUM | Effort: 2-3 hours | Deps: none**

Current: 4 static preset cards + generic welcome.

Redesign:
- Animated gradient background (CSS only, using Aurora accent colors)
- Model-aware suggestions: if Gemini selected, suggest "تصویر تحلیل کن" (image analysis). If DeepSeek, suggest "مسئله ریاضی حل کن" (math).
- Example conversations: 2-3 clickable examples that pre-fill the input
- Capability badges: show what the selected model can do (chat, code, vision, etc.)

#### F12. Conversation Export (Fix Broken)
**Impact: LOW | Effort: 1-2 hours | Deps: backend export endpoint exists**

Per S2 audit, `/api/conversations/[id]/export` frontend route doesn't exist (404). Create it:
- `frontend/app/api/conversations/[id]/export/route.ts`
- Proxy to backend with auth header
- Support formats: JSON, Markdown, Plain Text

#### F13. Web Search Citations
**Impact: LOW-MEDIUM | Effort: 4-6 hours | Deps: backend changes**

Currently web search is a toggle that adds `web_search: true` to the request. No citation display.

Add:
- Parse citation data from the stream (if backend provides it)
- Show sources below the response as clickable cards with favicon, title, snippet
- Perplexity-style inline citations: `[1]`, `[2]` markers in the text linking to source cards

#### F14. Micro-Interactions & Animation Plan
**Impact: LOW | Effort: 3-4 hours | Deps: none**

All animations use existing CSS custom properties (`--motion-fast`, `--motion-normal`, `--motion-slow`).

| Interaction | Animation | CSS |
|-------------|-----------|-----|
| Message send | Slide up + fade in | `@keyframes slideIn { from { opacity: 0; transform: translateY(10px) } }` |
| Streaming cursor | Blink | `@keyframes blink` (see F3) |
| Copy success | Green flash on button | `background: var(--positive)` for 300ms |
| Model picker open | Scale + fade | `transform: scale(0.95) → 1; opacity: 0 → 1` |
| Sidebar item hover | Background transition | `transition: background var(--motion-fast)` |
| Typing indicator | Three-dot wave | Already exists, keep it |
| Error shake | Horizontal shake | `@keyframes shake { 0%,100% { transform: translateX(0) } 25% { transform: translateX(-4px) } 75% { transform: translateX(4px) } }` |
| Button press | Scale down | `:active { transform: scale(0.97) }` |
| New conversation | Fade in from top | `@keyframes fadeSlideIn` |
| Scroll-to-bottom button | Bounce on appear | `@keyframes bounce { 0% { transform: translateY(0) } 50% { transform: translateY(-4px) } }` |

#### F15. Accessibility (a11y) Baseline
**Impact: LOW | Effort: 2-3 hours | Deps: none**

- `role="log"` on messages container
- `aria-live="polite"` on streaming message area
- `aria-label` on all icon-only buttons
- Focus trap in mobile drawer
- Skip-to-content link
- Tab order: sidebar toggle → model picker → messages → input → send

---

## 4. Component Architecture

### 4.1 Current State (Problem)

`chat/page.tsx` is a **1074-line monolith** with 25+ `useState` hooks, inline SVGs, API calls, streaming logic, conversation CRUD, file upload, export, mobile detection, and UI rendering all in one component. The S9 audit correctly identified this needs decomposition.

### 4.2 Target Architecture

```
app/chat/
├── page.tsx                    # Thin shell: layout + providers (< 100 lines)
├── components/
│   ├── ChatArea.tsx            # Message list + input bar
│   ├── MessageList.tsx         # Scrollable message container
│   ├── MessageItem.tsx         # Single message (user or assistant)
│   ├── MarkdownRenderer.tsx    # react-markdown wrapper + code blocks
│   ├── CodeBlock.tsx           # Syntax-highlighted code with copy
│   ├── InputBar.tsx            # Textarea + file attach + voice + send
│   ├── ModelPicker.tsx         # Rich card-based model selector
│   ├── CostDisplay.tsx         # Live token/cost counter
│   ├── ConversationSidebar.tsx # Sidebar shell
│   ├── ConversationList.tsx    # Filtered/grouped conversation items
│   ├── ConversationSearch.tsx  # Search input
│   ├── EmptyState.tsx          # Welcome + presets + suggestions
│   └── KeyboardShortcuts.tsx   # Shortcut handler + help modal
├── hooks/
│   ├── useChat.ts              # Messages, streaming, send, retry, edit
│   ├── useConversations.ts     # CRUD, search, folders, pin
│   ├── useModelPicker.ts       # Selection, persistence, search/filter
│   └── useVoiceInput.ts        # SpeechRecognition wrapper
└── styles/
    └── chat.css                # Chat-specific styles (extract from globals.css)
```

### 4.3 Extraction Strategy (Ponytail-Compliant)

Don't refactor all at once. Extract incrementally as each feature is built:

1. **F1 (Markdown)**: Extract `MarkdownRenderer.tsx` + `CodeBlock.tsx` from `ChatMessageItem`
2. **F2 (Model Picker)**: Extract `ModelPicker.tsx` from the inline `<select>`
3. **F3 (Streaming Cursor)**: Modify `ChatMessageItem` — 5-line change, no extraction needed
4. **F4 (Edit/Regenerate)**: Extract `useChat.ts` hook — move `sendMessage`, `retry`, `cancel` out of the page
5. **F5 (Search)**: Extract `ConversationSearch.tsx` + modify `ConversationSidebar.tsx`

After F1–F5, the main page should be under 400 lines. Continue extracting as features land.

### 4.4 State Management (No New Libraries)

Current: 25+ `useState` in one component. Target: 3 custom hooks.

```
useChat() → messages, streaming, sendMessage, retry, editMessage, regenerate, cancel, usageStats
useConversations() → list, activeId, search, folders, CRUD, load, save
useModelPicker() → selected, search, filtered, persist, groups
```

No Redux, no Zustand, no Jotai. React hooks + `useCallback` + `useRef` are sufficient at this scale. The S9 audit agrees.

---

## 5. Micro-Interaction Plan

### 5.1 Send Flow

```
User types → [auto-grow textarea] → Press Enter
  → Input fades out (150ms)
  → User message slides up (250ms, ease-out)
  → Typing indicator appears (3-dot wave)
  → First token arrives → indicator replaced by message
  → Blinking cursor at end of text
  → Tokens stream in with smooth scroll
  → Token speed shown: "42 tok/s" (updates every 500ms)
  → Stream ends → cursor disappears
  → Cost updates: "۱,۲۳۴ توکن · ~۲,۵۰۰ تومان"
  → Copy + Regenerate + Edit buttons fade in (150ms)
```

### 5.2 Model Switch

```
Click model name in topbar
  → Picker slides down from topbar (250ms, scale 0.95→1)
  → Search input auto-focused
  → Type to filter → cards animate in/out (150ms)
  → Click card → accent border + checkmark
  → Picker closes (150ms)
  → Model name updates in topbar with subtle highlight flash
```

### 5.3 Conversation Switch

```
Click conversation in sidebar
  → Current messages fade out (150ms)
  → Loading skeleton appears (pulse animation)
  → New messages fade in (250ms)
  → Sidebar item highlighted
```

### 5.4 Error States

```
API error → error message slides down below input bar (250ms)
  → Red left border + danger icon
  → "تلاش مجدد" button inline
  → Shake animation on the error container
  → Auto-dismiss after 10s (fade out)

Balance error → special card replaces input bar
  → Wallet balance + "افزایش موجودی" button
  → Pulsing warning icon
```

---

## 6. RTL & Persian-First Design Details

### 6.1 CSS Logical Properties (Mandatory)

Every new component must use logical properties. The S3 audit flagged specific violations:

```css
/* WRONG — physical properties */
margin-left: 8px;
padding-right: 16px;
border-left: 1px solid;
left: 0;

/* RIGHT — logical properties */
margin-inline-start: 8px;
padding-inline-end: 16px;
border-inline-start: 1px solid;
inset-inline-start: 0;
```

### 6.2 Bidirectional Text Handling

- Model names, code, numbers: always `dir="ltr"` (already done in most places)
- Chat bubbles: `dir="auto"` — browser detects language direction
- Markdown content: `dir="auto"` on each paragraph/block
- Input textarea: `dir="auto"` — user can type in either direction

### 6.3 Persian Number Formatting

```tsx
function toPersianNum(n: number): string {
  return n.toLocaleString('fa-IR').replace(/٬/g, '،')
}
// 1234 → "۱٬۲۳۴" (Persian thousands separator is ، not ٬)
// Actually: (1234).toLocaleString('fa-IR') → "۱٬۲۳۴"
```

Use this everywhere: cost display, token count, conversation count, date formatting.

### 6.4 Vazirmatn Font

Already self-hosted in `globals.css` with `@font-face`. Good. Ensure:
- `font-weight: 400` for body text
- `font-weight: 700` for headings, labels, buttons
- Monospace: `JetBrains Mono` for code (already defined as `--font-mono`)

---

## 7. CSS Architecture Additions to globals.css

The existing Aurora v2 design system is solid (2786 lines, well-organized CSS custom properties). Add these sections:

```css
/* ── Chat-specific additions ─────────────────────────────────────────── */

/* Markdown rendered content */
.chat-bubble-content { line-height: 1.7; }
.chat-bubble-content > *:first-child { margin-top: 0; }
.chat-bubble-content > *:last-child { margin-bottom: 0; }

/* Streaming animation */
.streaming-cursor::after { content: '▋'; animation: blink 0.8s step-end infinite; color: var(--accent); }
@keyframes blink { 50% { opacity: 0; } }

/* Message entrance */
@keyframes messageSlideIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.chat-row { animation: messageSlideIn var(--motion-normal) ease-out; }

/* Model picker */
.model-picker { position: absolute; top: calc(100% + 4px); inset-inline-start: 0; width: 380px; max-height: 480px; background: var(--bg-elevated); border: 1px solid var(--border-strong); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); overflow: hidden; z-index: 100; animation: pickerSlideDown var(--motion-normal) ease-out; }
@keyframes pickerSlideDown { from { opacity: 0; transform: translateY(-4px) scale(0.98); } }
.model-card { display: flex; flex-direction: column; gap: var(--space-1); padding: var(--space-3) var(--space-4); cursor: pointer; transition: background var(--motion-fast); }
.model-card:hover { background: var(--bg-hover); }
.model-card.selected { background: var(--accent-dim); border-inline-start: 2px solid var(--accent); }
.model-card .provider-badge { font-size: 11px; padding: 2px 6px; border-radius: var(--radius-full); background: var(--bg-overlay); color: var(--text-muted); }
.model-card .capability-tag { font-size: 10px; padding: 1px 5px; border-radius: var(--radius-full); background: var(--accent-dim); color: var(--accent); }

/* Voice input button */
.voice-btn { position: relative; }
.voice-btn.listening { color: var(--danger); }
.voice-btn.listening::before { content: ''; position: absolute; inset: -4px; border-radius: 50%; border: 2px solid var(--danger); animation: voicePulse 1.5s infinite; }
@keyframes voicePulse { 0% { transform: scale(1); opacity: 1; } 100% { transform: scale(1.5); opacity: 0; } }

/* Drag & drop zone */
.drop-zone-active { border: 2px dashed var(--accent); background: var(--accent-dim); }

/* Cost display */
.cost-display { font-size: 12px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.cost-display .live { color: var(--accent); }
```

---

## 8. Implementation Priority & Dependencies

```
Week 1 (Launch Blockers):
  Day 1-2: F1 (Markdown + Syntax Highlighting) — transforms the product overnight
  Day 2-3: F2 (Rich Model Picker) — leverages the multi-model advantage
  Day 3:   F3 (Streaming Cursor) — 1-hour quick win
  Day 4-5: F4 (Edit + Regenerate) — expected by every user
  Day 5:   F5 (Search + Date Grouping) — usability at scale

Week 2 (Essentials):
  Day 1:   F6 (Keyboard Shortcuts) — power user retention
  Day 2:   F8 (Voice Input) — wow factor, 2-hour implementation
  Day 2-3: F7 (File Attachments) — multi-file + drag-drop
  Day 3-4: F10 (Real-Time Cost) — trust builder
  Day 4-6: F9 (Folders) — needs backend work

Week 3 (Polish):
  Day 1-2: F11 (Empty State) + F12 (Export Fix) — quick wins
  Day 2-3: F14 (Animations) — refinement pass
  Day 3-4: F13 (Web Citations) — if backend supports it
  Day 4:   F15 (Accessibility) — baseline compliance
```

### Dependency Graph

```
F1 (Markdown) ────────────── no deps, start immediately
F2 (Model Picker) ────────── no deps, start immediately
F3 (Streaming Cursor) ────── no deps, start immediately
F4 (Edit/Regenerate) ─────── no deps, but benefits from F1
F5 (Search) ──────────────── no deps
F6 (Shortcuts) ───────────── no deps
F7 (File Attachments) ────── no deps
F8 (Voice) ───────────────── no deps
F9 (Folders) ─────────────── backend: add folder_id to conversations
F10 (Cost) ───────────────── no deps (pricing data in useCatalog)
F11–F15 ──────────────────── no critical deps
```

---

## 9. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| `react-markdown` bundle size (~40KB gzipped) | Medium | Low | Worth it. Lazy load with `next/dynamic` if needed |
| RTL breaks in markdown tables/lists | High | Medium | Test with Persian + English mixed content. Use `dir="auto"` |
| Model picker performance with 50+ models | Low | Low | Virtualize list if >30 models (react-window) |
| Web Speech API browser support | Medium | Medium | 94% global support. Graceful fallback: hide button if unsupported |
| Streaming cursor jank on slow connections | Medium | Low | Batch updates with `requestAnimationFrame` |
| Breaking existing chat during refactor | High | High | Extract incrementally. Each F-feature is independently shippable |

---

## 10. What We're NOT Building (Explicitly Deferred)

| Feature | Why Deferred | When to Revisit |
|---------|-------------|-----------------|
| Model compare/split-view | Complex UI, low initial demand | Phase 3, when >20 models work |
| Canvas/Artifacts (like Claude) | Needs backend runtime, major effort | Phase 4 |
| Conversation branching | UX complexity, niche use case | Phase 3 |
| Prompt template library | Needs curation/content, not just code | Phase 3 |
| Real-time collaboration | Massive complexity | Never (unless team grows) |
| Mobile app | Web-first, responsive covers 90% | After product-market fit |
| Custom themes/skins | Aurora v2 is good enough | After launch feedback |

---

## Appendix A: Existing Design Tokens (from globals.css)

For reference — these are the Aurora v2 tokens all new components must use:

```
Surfaces:    --bg-base (#05050a), --bg-surface (#0c0c14), --bg-elevated (#13131d), --bg-overlay (#1a1a26)
Text:        --text-primary (#f0f0f5), --text-secondary (#a0a0b0), --text-muted (#606070)
Accent:      --accent (#6366f1), --accent-hover (#818cf8), --accent-dim (rgba 12%), --accent-glow (rgba 25%)
Semantic:    --positive (#34d399), --warning (#fbbf24), --danger (#f87171), --info (#60a5fa)
Borders:     --border (white 6%), --border-strong (white 12%)
Motion:      --motion-fast (150ms), --motion-normal (250ms), --motion-slow (400ms)
Radii:       --radius-sm (6px), --radius-md (10px), --radius-lg (14px), --radius-xl (20px), --radius-full (9999px)
Typography:  --font-sans (Vazirmatn), --font-mono (JetBrains Mono)
Layout:      --sidebar-width (260px), --topbar-height (52px)
```

## Appendix B: Package Additions

Only 3 new packages needed for the entire feature set:

| Package | Size (gzip) | Used By | Replaces |
|---------|-------------|---------|----------|
| `react-markdown` | ~8KB | F1 | Manual `{msg.content}` rendering |
| `rehype-highlight` | ~3KB + highlight.js (~30KB) | F1 | No existing alternative |
| `remark-gfm` | ~5KB | F1 | No existing alternative |

Total: ~46KB gzipped. This is the cost of having markdown rendering — every competitor pays it. The `highlight.js` portion can be tree-shaken to only include languages we need (JS, Python, TypeScript, Go, Rust, SQL, Bash, HTML, CSS, JSON) which reduces it to ~15KB.

No other packages needed. Everything else (voice, shortcuts, drag-drop, animations) is vanilla JS/CSS.
