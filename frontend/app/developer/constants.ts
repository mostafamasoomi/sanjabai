// Shared Persian message for the (expected-rare) CSRF-rejection path — the
// backend returns 403 with "هدر X-Requested-With ارسال نشده" if a mutating
// request ever reaches it without the header apiFetch adds automatically.
export const FORBIDDEN_MESSAGE = 'درخواست شما رد شد (خطای امنیتی). لطفاً صفحه را تازه‌سازی کرده و دوباره تلاش کنید.'

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
export const RATE_LIMITS = [
  { plan: 'رایگان / بدون اشتراک', requests: '۳۰ درخواست در دقیقه' },
  { plan: 'پایه (pro)', requests: '۱۲۰ درخواست در دقیقه' },
  { plan: 'سازمانی (enterprise)', requests: '۳۰۰ درخواست در دقیقه' },
]

export const ENDPOINTS = [
  {
    method: 'POST',
    path: '/v1/chat/completions',
    desc: 'ارسال درخواست چت — سازگار با OpenAI',
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
    desc: 'دریافت لیست مدل‌های موجود',
    body: null,
  },
]
