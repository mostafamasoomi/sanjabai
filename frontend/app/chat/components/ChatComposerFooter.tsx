import { Num, faNum } from '@/lib/format'
import { type ModelCatalogItem } from '@/types/catalog'
import type { UsageStats } from '../chatTypes'
import { LOW_BALANCE_TOMAN } from '../chatHelpers'

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
  return (
    <div className="chat-composer-footer">
      <span className="chat-composer-status">
        {streaming ? (
          <span className="chat-streaming-dot">در حال تولید...</span>
        ) : (
          `${model?.displayName ?? 'منتظر انتخاب مدل'} — ${smartMode ? '🧠 Smart Mode' : 'آماده'}`
        )}
      </span>
      <span className="chat-shortcuts-hint">
        <kbd>Ctrl+N</kbd> چت جدید · <kbd>Esc</kbd> توقف
      </span>
      {/* ── Pre-send cost estimate ─────────────────────────── */}
      {preSendEstimate && !streaming && (
        <span className="cost-estimate">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
          </svg>
          ~<Num value={preSendEstimate.tokens} unit="توکن" />
          <span className="cost-estimate-sep">·</span>
          ~<Num value={preSendEstimate.cost} decimals={1} unit="تومان" />
        </span>
      )}
      {usageStats.totalTokens > 0 && (
        <span className="usage-badge" title={`پرامپت: ${faNum(usageStats.promptTokens)} | پاسخ: ${faNum(usageStats.completionTokens)}`}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          <Num value={usageStats.totalTokens} unit="توکن" />
          {/* The cost span was dir="ltr" with a Persian unit, which put
              "تومان" on the wrong side of the amount. */}
          <Num className="usage-cost" value={usageStats.estimatedCost} unit="تومان" />
          {streaming && tokensPerSec > 0 && (
            <Num className="usage-tps" value={tokensPerSec} unit="tok/s" />
          )}
        </span>
      )}
      {/* ── Wallet balance / warning ────────────────────────── */}
      {walletBalance !== null && walletBalance < LOW_BALANCE_TOMAN && (
        <a href="/wallet" className="wallet-warning" title="موجودی کم — شارژ کنید">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          موجودی کم
        </a>
      )}
      {walletBalance !== null && walletBalance >= LOW_BALANCE_TOMAN && (
        <span className="wallet-balance-inline">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 18v1c0 1.1-.9 2-2 2H5c-1.11 0-2-.9-2-2V5c0-1.1.89-2 2-2h14c1.1 0 2 .9 2 2v1h-9c-1.11 0-2 .9-2 2v8c0 1.1.89 2 2 2h9zm-9-2h10V8H12v8z"/>
          </svg>
          <Num value={walletBalance} unit="تومان" />
        </span>
      )}
      {/* ── Prompt Library button ───────────────────────────── */}
      <a href="/prompts" className="prompt-lib-btn" title="کتابخانه پرامپت">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
        پرامپت‌ها
      </a>
      <span className="text-[10px] text-[var(--text-muted)]">
        {inputLength > 0 && `${faNum(inputLength)} کاراکتر`}
      </span>
    </div>
  )
}
