import { Num } from '@/lib/format'
import { useLang, type Lang } from '@/components/LanguageToggle'
import { fmt, type Formatters } from '@/lib/i18n'
import { type ModelCatalogItem } from '@/types/catalog'
import type { UsageStats } from '../chatTypes'
import { LOW_BALANCE_TOMAN } from '../chatHelpers'
import { chatComposerFooterStrings } from './ChatComposerFooter.strings'

/**
 * `<Num>` (lib/format.tsx) always renders Persian digits -- correct for the
 * Persian UI, wrong once the panel is English (see lib/i18n.ts's header
 * comment). In Persian this stays byte-identical to the original `<Num>`
 * call; in English it falls back to a plain span through `fmt(lang)`, which
 * needs no bidi isolation because the whole page is already LTR by then.
 */
function Amount({ lang, f, value, kind, decimals, className }: {
  lang: Lang
  f: Formatters
  value: number | null | undefined
  kind: 'token' | 'toman' | 'tps'
  decimals?: number
  className?: string
}) {
  if (lang === 'fa') {
    const faStrings = chatComposerFooterStrings('fa')
    const unit = kind === 'token' ? faStrings.tokenUnit : kind === 'toman' ? faStrings.tomanUnit : 'tok/s'
    return <Num className={className} value={value} unit={unit} decimals={decimals} />
  }
  const classes = className ? `num ${className}` : 'num'
  if (kind === 'toman') {
    return <span className={classes}>{f.price(value, { decimals })}</span>
  }
  const unit = kind === 'token' ? chatComposerFooterStrings(lang).tokenUnit : 'tok/s'
  return <span className={classes}>{f.num(value, { decimals })} {unit}</span>
}

type ChatComposerFooterProps = {
  streaming: boolean
  model: ModelCatalogItem | null
  smartMode: boolean
  preSendEstimate: { tokens: number; cost: number } | null
  usageStats: UsageStats
  tokensPerSec: number
  walletBalance: number | null
  inputLength: number
}

export default function ChatComposerFooter({
  streaming, model, smartMode, preSendEstimate, usageStats, tokensPerSec, walletBalance, inputLength,
}: ChatComposerFooterProps) {
  const lang = useLang()
  const s = chatComposerFooterStrings(lang)
  const f = fmt(lang)
  return (
    <div className="chat-composer-footer">
      <span className="chat-composer-status">
        {streaming ? (
          <span className="chat-streaming-dot">{s.generating}</span>
        ) : (
          `${model?.displayName ?? s.waitingForModel} — ${smartMode ? '🧠 Smart Mode' : s.ready}`
        )}
      </span>
      <span className="chat-shortcuts-hint">
        <kbd>Ctrl+N</kbd> {s.newChatShortcut} · <kbd>Esc</kbd> {s.stopShortcut}
      </span>
      {/* ── Pre-send cost estimate ─────────────────────────── */}
      {preSendEstimate && !streaming && (
        <span className="cost-estimate">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
          </svg>
          ~<Amount lang={lang} f={f} value={preSendEstimate.tokens} kind="token" />
          <span className="cost-estimate-sep">·</span>
          ~<Amount lang={lang} f={f} value={preSendEstimate.cost} decimals={1} kind="toman" />
        </span>
      )}
      {usageStats.totalTokens > 0 && (
        <span className="usage-badge" title={s.promptCompletionTitle(f.num(usageStats.promptTokens), f.num(usageStats.completionTokens))}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          <Amount lang={lang} f={f} value={usageStats.totalTokens} kind="token" />
          {/* The cost span was dir="ltr" with a Persian unit, which put
              "تومان" on the wrong side of the amount. */}
          <Amount lang={lang} f={f} className="usage-cost" value={usageStats.estimatedCost} kind="toman" />
          {streaming && tokensPerSec > 0 && (
            <Amount lang={lang} f={f} className="usage-tps" value={tokensPerSec} kind="tps" />
          )}
        </span>
      )}
      {/* ── Wallet balance / warning ────────────────────────── */}
      {walletBalance !== null && walletBalance < LOW_BALANCE_TOMAN && (
        <a href="/wallet" className="wallet-warning" title={s.lowBalanceTitle}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          {s.lowBalance}
        </a>
      )}
      {walletBalance !== null && walletBalance >= LOW_BALANCE_TOMAN && (
        <span className="wallet-balance-inline">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 18v1c0 1.1-.9 2-2 2H5c-1.11 0-2-.9-2-2V5c0-1.1.89-2 2-2h14c1.1 0 2 .9 2 2v1h-9c-1.11 0-2 .9-2 2v8c0 1.1.89 2 2 2h9zm-9-2h10V8H12v8z"/>
          </svg>
          <Amount lang={lang} f={f} value={walletBalance} kind="toman" />
        </span>
      )}
      {/* ── Prompt Library button ───────────────────────────── */}
      <a href="/prompts" className="prompt-lib-btn" title={s.promptLibraryTitle}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
        {s.promptLibrary}
      </a>
      <span className="text-[10px] text-[var(--text-muted)]">
        {inputLength > 0 && s.characters(f.num(inputLength))}
      </span>
    </div>
  )
}
