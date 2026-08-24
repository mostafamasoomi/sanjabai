import { memo } from 'react'
import { Icon } from '@/components/ui/Icon'
import MarkdownRenderer from './MarkdownRenderer'
import { getTruncationStatus } from '../finishReason'
import type { Message } from '../chatTypes'
import { CopyIcon, CheckIcon } from './ChatIcons'

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
}: ChatMessageItemProps) {
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
              <span>مدل بدون تولید متن به محدودیت طول رسید.</span>
              <button type="button" onClick={() => onRetry(index)} className="chat-truncated-btn">
                تلاش دوباره
              </button>
            </div>
          ) : (
            <div className="chat-truncated-bar" role="status">
              <span>این پاسخ به‌خاطر محدودیت طول ناتمام ماند.</span>
              <button type="button" onClick={() => onContinue(index)} className="chat-truncated-btn">
                ادامه بده
              </button>
            </div>
          )
        )}
        {msg.role === 'assistant' && msg.content && !streaming && (
          <div className="chat-actions">
            <button
              onClick={() => onCopy(msg.id, msg.content)}
              className="chat-action-btn"
              title="کپی"
            >
              {copiedId === msg.id ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
              {copiedId === msg.id ? 'کپی شد' : 'کپی'}
            </button>
            {index > 0 && (
              <button onClick={() => onRetry(index)} className="chat-action-btn" title="تلاش مجدد">
                <Icon name="refresh" size={13} />
                تلاش مجدد
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
