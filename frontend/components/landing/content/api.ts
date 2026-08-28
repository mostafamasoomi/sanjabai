import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { useLandingOverrides, applyModuleOverride } from '@/lib/landingOverrides'
import { API_BASE_URL } from './constants'

/* ── API section ──────────────────────────────────────────────────────────── */

const FA = {
  points: [
    'همان مسیرهای /v1/chat/completions و /v1/embeddings',
    'پاسخ استریمی با Server-Sent Events',
    'کلید اختصاصی برای هر سرویس، با سقف مصرف جداگانه',
  ],

  /** Keyed by the code-sample language tab; only the demo message content
   *  differs by UI language, the code itself is language-neutral syntax. */
  codeSamples: {
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
  } as Record<string, string>,
}

const EN: typeof FA = {
  points: [
    'The same /v1/chat/completions and /v1/embeddings routes',
    'Streamed responses over Server-Sent Events',
    'A dedicated key per service, each with its own usage cap',
  ],

  codeSamples: {
    Python: `import os

from openai import OpenAI

client = OpenAI(
    base_url="${API_BASE_URL}",
    api_key=os.environ["SANJABAI_API_KEY"],
)

stream = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": "Hello!"}],
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
  messages: [{ role: "user", content: "Hello!" }],
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
      { "role": "user", "content": "Hello!" }
    ],
    "stream": true
  }'`,
  },
}

const apiContentFor = dict(FA, EN)

/** Resolves the API section copy for a language, applying any admin-stored
 *  override. */
function useApiContent(lang: Lang) {
  const overrides = useLandingOverrides()
  return applyModuleOverride('api', lang, apiContentFor(lang), overrides)
}

export const apiContent = useApiContent

/** Today's static FA/EN values — admin editor placeholders only, see the
 *  matching comment in hero.ts. */
export const apiStaticDefaults = { fa: FA, en: EN }
