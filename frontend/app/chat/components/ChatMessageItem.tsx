import { memo } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import MarkdownRenderer from './MarkdownRenderer'
import { getTruncationStatus } from '../finishReason'
import type { Message } from '../chatTypes'
import { CopyIcon, CheckIcon } from './ChatIcons'
import { chatMessageItemStrings } from './ChatMessageItem.strings'
import ToolCallChip from './ToolCallChip'
import ToolConfirmCard from './ToolConfirmCard'
import type { ToolStreamState } from '../hooks/useChatStream'

type ChatMessageItemProps = {
  msg: Message
  index: number
  isLast: boolean
  streaming: boolean
  userAvatar: string
  copiedId: string | null
  onCopy: (id: string, content: string) => void
  onRetry: (index: number) => void
  onContinue: (index: number) => void
  /** Tool activity the loop reported for THIS assistant turn. Undefined for
   *  every message today: nothing emits these events until the backend loop
   *  lands, and an ordinary message must render exactly as it always has. */
  toolEvents?: ToolStreamState
}

const ChatMessageItem = memo(function ChatMessageItem({
  msg,
  index,
  isLast,
  streaming,
  userAvatar,
  copiedId,
  onCopy,
  onRetry,
  onContinue,
  toolEvents,
}: ChatMessageItemProps) {
  const s = chatMessageItemStrings(useLang())
  // finishReason is only populated once this message's own stream finished
  // (see sendMessage in the parent), so this is naturally false while `msg`
  // is still the actively-streaming bubble -- no extra `!streaming` guard
  // needed here.
  const truncation = msg.role === 'assistant' ? getTruncationStatus(msg.finishReason, msg.content) : { truncated: false as const }
  return (
    <div className={`chat-row ${msg.role === 'user' ? 'chat-row-user' : 'chat-row-assistant'}`}>
      {msg.role === 'assistant' && (
        <div className="chat-avatar chat-avatar-ai">
          <Icon name="models" size={16} />
        </div>
      )}
      <div className={`chat-bubble ${msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'}`}>
        {msg.role === 'assistant' && streaming && isLast && !msg.content && (
          <div className="chat-typing">
            <span /><span /><span />
          </div>
        )}
        {msg.role === 'assistant' ? (
          <div className="chat-bubble-content">
            {/* Above the answer, in the order the loop produced them: the
                chips are what happened on the way to the text below. */}
            {toolEvents?.calls.map((c, i) => (
              <ToolCallChip key={`${c.name}-${i}`} name={c.name} status={c.status} />
            ))}
            {toolEvents?.confirm && (
              <ToolConfirmCard
                name={toolEvents.confirm.name}
                preview={toolEvents.confirm.preview}
              />
            )}
            <MarkdownRenderer content={msg.content} />
            {streaming && isLast && msg.content && (
              <div className="stream-cursor-line" aria-hidden="true">
                <span className="stream-cursor" />
              </div>
            )}
          </div>
        ) : (
          <div className="chat-bubble-content chat-bubble-plain">{msg.content}</div>
        )}
        {msg.role === 'assistant' && truncation.truncated && (
          truncation.empty ? (
            <div className="chat-truncated-bar chat-truncated-bar-empty" role="status">
              <span>{s.truncatedEmpty}</span>
              <button type="button" onClick={() => onRetry(index)} className="chat-truncated-btn">
                {s.retry}
              </button>
            </div>
          ) : (
            <div className="chat-truncated-bar" role="status">
              <span>{s.truncated}</span>
              <button type="button" onClick={() => onContinue(index)} className="chat-truncated-btn">
                {s.continue}
              </button>
            </div>
          )
        )}
        {msg.role === 'assistant' && msg.content && !streaming && (
          <div className="chat-actions">
            <button
              onClick={() => onCopy(msg.id, msg.content)}
              className="chat-action-btn"
              title={s.copy}
            >
              {copiedId === msg.id ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
              {copiedId === msg.id ? s.copied : s.copy}
            </button>
            {index > 0 && (
              <button onClick={() => onRetry(index)} className="chat-action-btn" title={s.retryAgain}>
                <Icon name="refresh" size={13} />
                {s.retryAgain}
              </button>
            )}
          </div>
        )}
      </div>
      {msg.role === 'user' && userAvatar && (
        <div className="chat-avatar chat-avatar-user">
          {userAvatar}
        </div>
      )}
    </div>
  )
})

export default ChatMessageItem
