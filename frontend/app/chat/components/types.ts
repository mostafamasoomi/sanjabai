export type Message = { role: 'user' | 'assistant' | 'system'; content: string; id: string }

export type UsageStats = { promptTokens: number; completionTokens: number; totalTokens: number; estimatedCost: number }

export type Conversation = {
  id: string
  title: string
  model: string
  created_at: string
  updated_at: string
}

export type ConversationDetail = Conversation & {
  messages: { role: string; content: string }[]
}

export type Assistant = {
  id: number
  name: string
  description: string
  system_prompt: string
  model_id: string | null
  icon: string | null
  is_public: boolean
  user_id: number
}