import { API_BASE_URL } from './constants'

/* ── API section ──────────────────────────────────────────────────────────── */

export const API_POINTS = [
  'همان مسیرهای /v1/chat/completions و /v1/embeddings',
  'پاسخ استریمی با Server-Sent Events',
  'کلید اختصاصی برای هر سرویس، با سقف مصرف جداگانه',
] as const

export const CODE_SAMPLES: Record<string, string> = {
  Python: `import os

from openai import OpenAI

client = OpenAI(
    base_url="${API_BASE_URL}",
    api_key=os.environ["SANJABAI_API_KEY"],
)

stream = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": "سلام!"}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")`,

  JavaScript: `import OpenAI from "openai"

const client = new OpenAI({
  baseURL: "${API_BASE_URL}",
  apiKey: process.env.SANJABAI_API_KEY,
})

const stream = await client.chat.completions.create({
  model: "mistral-large",
  messages: [{ role: "user", content: "سلام!" }],
  stream: true,
})

for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "")
}`,

  cURL: `curl ${API_BASE_URL}/chat/completions \\
  -H "Authorization: Bearer $SANJABAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gemini-3.5-flash",
    "messages": [
      { "role": "user", "content": "سلام!" }
    ],
    "stream": true
  }'`,
}
