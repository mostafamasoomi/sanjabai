import type { Lang } from '@/components/LanguageToggle'
import { developerConstantsStrings } from './constants.strings'

// Forbidden-request toast for the (expected-rare) CSRF-rejection path — the
// backend returns 403 with "هدر X-Requested-With ارسال نشده" if a mutating
// request ever reaches it without the header apiFetch adds automatically.
export function forbiddenMessage(lang: Lang): string {
  return developerConstantsStrings(lang).forbiddenMessage
}

// The code samples are code, not prose -- including the Persian message
// content inside them, which demonstrates a Persian chat request and is left
// untranslated per the i18n handoff spec (only the surrounding prose in
// CodeExamplesSection is translated).
export const CODE_EXAMPLES = {
  python: {
    label: 'Python',
    code: `from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://sanjabai.com/v1"
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "شما یک دستیار فارسی هستید."},
        {"role": "user", "content": "سلام! حالت چطوره؟"}
    ]
)

print(response.choices[0].message.content)`,
    install: 'pip install openai',
  },
  curl: {
    label: 'cURL',
    code: `curl https://sanjabai.com/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": "شما یک دستیار فارسی هستید."},
      {"role": "user", "content": "سلام! حالت چطوره؟"}
    ]
  }'`,
    install: null,
  },
  javascript: {
    label: 'JavaScript',
    code: `import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "YOUR_API_KEY",
  baseURL: "https://sanjabai.com/v1",
});

const response = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [
    { role: "system", content: "شما یک دستیار فارسی هستید." },
    { role: "user", content: "سلام! حالت چطوره؟" },
  ],
});

console.log(response.choices[0].message.content);`,
    install: 'npm install openai',
  },
}

// Real limits, read off backend/security.py — flat per-minute request caps
// keyed by subscription plan, not the "tokens/day" tiers this table used to
// show (those numbers existed nowhere in the backend; a daily token quota
// table exists in the schema but its enforcement is unreachable on the
// normal request path, so it is not a real limit and is not listed here).
export function rateLimits(lang: Lang) {
  return developerConstantsStrings(lang).rateLimits
}

export function endpoints(lang: Lang) {
  const desc = developerConstantsStrings(lang).endpointDescs
  // Falls back to the path itself (never fabricated prose) if a description
  // is ever missing for a language -- the map above is the source of truth.
  return ENDPOINT_DEFS.map((ep) => ({ ...ep, desc: desc[ep.path] ?? ep.path }))
}

// method/path/body are code -- Latin and untranslated in both languages.
// The "پیام شما" placeholder inside `body` is code-sample content, not
// prose, and is left untranslated per the i18n handoff spec.
const ENDPOINT_DEFS = [
  {
    method: 'POST',
    path: '/v1/chat/completions',
    body: `{
  "model": "gpt-4o",
  "messages": [
    { "role": "user", "content": "پیام شما" }
  ],
  "stream": false
}`,
  },
  {
    method: 'GET',
    path: '/v1/models',
    body: null,
  },
]
