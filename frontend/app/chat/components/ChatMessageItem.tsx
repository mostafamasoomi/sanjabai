'use client'

import { memo } from 'react'
import { Icon } from '@/components/ui/Icon'
import MarkdownRenderer from './MarkdownRenderer'
import { CopyIcon, CheckIcon } from './Icons'
import type { Message } from './types'

export type ChatMessageItemProps = {
  msg: Message
  index: number
  isLast: boolean
  streaming: boolean
  userAvatar: string
  copiedId: string | null
  onCopy: (id: string, content: string) => void
  onRetry: (index: number) => void
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
}: ChatMessageItemProps) {
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
          <span className={streaming && isLast ? 'streaming-cursor' : ''}>
            <MarkdownRenderer content={msg.content} />
          </span>
        ) : (
          <div className="chat-bubble-content chat-bubble-plain">{msg.content}</div>
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