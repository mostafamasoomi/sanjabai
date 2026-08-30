import { useCatalog, priceBand, PRICE_BAND_LABEL } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import MarkdownRenderer from '@/app/chat/components/MarkdownRenderer'
import { comparePageStrings } from '../page.strings'
import { type CompareTurn } from '../hooks/useCompareSessions'
import { type Side } from '../hooks/useCompareConversation'

/* One side's scrollable turn list -- split out of page.tsx purely to stay
   under the house 500-line cap (see that file's header comment). Reuses
   `.chat-row`/`.chat-bubble*` (globals.css, global to the whole app, not
   chat-specific) for each turn bubble, same idiom
   app/chat/components/ChatMessageItem.tsx uses, and `.compare-*` (also
   globals.css) for the per-turn stats/badges row, unchanged from the
   page's original single-shot layout. */

function formatElapsed(sec: number): string {
  if (sec < 1) return `${(sec * 1000).toFixed(0)}ms`
  return `${sec.toFixed(1)}s`
}

type CompareResultPanelProps = {
  side: Side
  model: ModelCatalogItem | null
  label: string
  thread: CompareTurn[]
  isPending: boolean
  sessionActive: boolean
  canSend: boolean
  onSendSide: (side: Side) => void
}

export default function CompareResultPanel({
  side, model, label, thread, isPending, sessionActive, canSend, onSendSide,
}: CompareResultPanelProps) {
  const lang = useLang()
  const s = comparePageStrings(lang)
  const f = fmt(lang)
  const { models } = useCatalog()

  return (
    <div className="compare-panel">
      {/* Panel header */}
      <div className="compare-panel-header">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'var(--accent-dim)' }}>
            <Icon name="models" size={16} className="text-[var(--accent)]" />
          </div>
          <div className="min-w-0">
            {model ? (
              <>
                <span className="compare-model-name" dir="ltr">{model.displayName}</span>
                {/* PRICE_BAND_LABEL (lib/useCatalog.ts) is a hardcoded
                    Persian record outside this directory's allowed scope --
                    it renders Persian even in the English UI. See the i18n
                    handoff report. */}
                <span className="compare-model-provider">{PRICE_BAND_LABEL[priceBand(model, models)]}</span>
              </>
            ) : label ? (
              <span className="compare-model-name" dir="ltr">{label}</span>
            ) : (
              <span className="text-sm text-[var(--text-muted)]">{s.noModelSelected}</span>
            )}
          </div>
        </div>

        {/* Per-side "send only here" button -- only once a session exists
            (a solo-target continue call needs an id to continue), per the
            owner's explicit shared-composer + per-side-buttons design (no
            target selector). */}
        {sessionActive && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => onSendSide(side)}
            disabled={!canSend}
            title={side === 'a' ? s.sendToA : s.sendToB}
          >
            <Icon name="send" size={14} />
            {side === 'a' ? s.sendToA : s.sendToB}
          </button>
        )}
      </div>

      {/* Content area — scrollable per-side turn list */}
      <div className="compare-content" style={{ maxHeight: '32rem', overflowY: 'auto' }}>
        {thread.length === 0 && !isPending ? (
          <div className="compare-placeholder">
            <Icon name="compare" size={24} className="text-[var(--text-muted)]" />
            <span className="text-sm text-[var(--text-muted)]">{s.placeholder}</span>
          </div>
        ) : (
          <div className="chat-messages" style={{ padding: 0 }}>
            {thread.map((turn, i) => (
              <div key={i} className={`chat-row ${turn.role === 'user' ? 'chat-row-user' : 'chat-row-assistant'}`}>
                <div className={`chat-bubble ${turn.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'}`}>
                  {turn.role === 'user' ? (
                    <div className="chat-bubble-content chat-bubble-plain">{turn.content}</div>
                  ) : turn.error ? (
                    <div className="chat-bubble-content" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--danger)' }}>
                      <Icon name="close" size={16} />
                      {/* turn.error is a backend-sourced error message
                          (Persian only for now) -- see the i18n handoff
                          report. */}
                      <span className="text-sm">{turn.error}</span>
                    </div>
                  ) : (
                    <div className="chat-bubble-content">
                      <div className="compare-markdown">
                        <MarkdownRenderer content={turn.content} />
                      </div>
                      {(turn.elapsed != null || turn.faster || turn.cheaper) && (
                        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-3)', marginTop: '0.5rem' }}>
                          {(turn.faster || turn.cheaper) && (
                            <div className="compare-badges">
                              {turn.faster && <span className="compare-badge compare-badge-fast" title={s.faster}>⚡ {s.faster}</span>}
                              {turn.cheaper && <span className="compare-badge compare-badge-cheap" title={s.cheaper}>💰 {s.cheaper}</span>}
                            </div>
                          )}
                          {turn.elapsed != null && (
                            <div className="compare-stat">
                              <span className="compare-stat-label">{s.time}</span>
                              <span className={`compare-stat-value ${turn.faster ? 'compare-stat-winner' : ''}`}>{formatElapsed(turn.elapsed)}</span>
                            </div>
                          )}
                          {turn.input_tokens != null && (
                            <div className="compare-stat">
                              <span className="compare-stat-label">{s.tokensInput}</span>
                              <span className="compare-stat-value num">{f.num(turn.input_tokens)}</span>
                            </div>
                          )}
                          {turn.output_tokens != null && (
                            <div className="compare-stat">
                              <span className="compare-stat-label">{s.tokensOutput}</span>
                              <span className="compare-stat-value num">{f.num(turn.output_tokens)}</span>
                            </div>
                          )}
                          {turn.cost != null && (
                            <div className="compare-stat">
                              <span className="compare-stat-label">{s.cost}</span>
                              {/* Toman via f.price — no page-local ÷1000
                                  formatter, no "IRT" label on a divided
                                  value (that was the old 10x-style trap). */}
                              <span className={`compare-stat-value ${turn.cheaper ? 'compare-stat-winner' : ''}`}>{f.price(turn.cost)}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isPending && (
              <div className="chat-row chat-row-assistant">
                <div className="chat-bubble chat-bubble-ai">
                  <div className="chat-typing">
                    <span /><span /><span />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
