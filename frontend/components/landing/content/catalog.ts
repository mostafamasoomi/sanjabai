/* ── Model marquee ────────────────────────────────────────────────────────────
   The real catalog from backend/litellm_config.yaml. Vendors whose mark is not
   in /public/ai simply render as a name — better than borrowing a logo that
   has nothing to do with the model. */

export const CATALOG = [
  { name: 'deepseek-v4-pro', logo: '/ai/deepseek.svg' },
  { name: 'mistral-large', logo: '/ai/mistralai.svg' },
  { name: 'gemini-3.5-flash', logo: '/ai/googlegemini.svg' },
  { name: 'llama-3.3-70b', logo: '/ai/meta.svg' },
  { name: 'gpt-oss-120b', logo: '/ai/openai.svg' },
  { name: 'tencent-hy3' },
  { name: 'mimo-v2.5' },
  { name: 'kimi-k2.7-code' },
  { name: 'deepseek-v4-flash', logo: '/ai/deepseek.svg' },
  { name: 'gemma-4-31b-it', logo: '/ai/googlegemini.svg' },
  { name: 'mistral-medium-3-5', logo: '/ai/mistralai.svg' },
  { name: 'agnes-2.0-flash' },
] as const
