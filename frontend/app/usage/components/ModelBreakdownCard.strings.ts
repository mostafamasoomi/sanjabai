import { dict } from '@/lib/i18n'

const FA = {
  title: 'مصرف به تفکیک مدل',
  calls: (n: string) => `(${n} درخواست)`,
  input: (v: string) => `ورودی: ${v}`,
  output: (v: string) => `خروجی: ${v}`,
  avgPerCall: (v: string) => `میانگین: ${v} توکن/درخواست`,
  costPerCall: (v: string) => `هزینه/درخواست: ${v}`,
}

const EN: typeof FA = {
  title: 'Usage by model',
  calls: (n) => `(${n} calls)`,
  input: (v) => `Input: ${v}`,
  output: (v) => `Output: ${v}`,
  avgPerCall: (v) => `Avg: ${v} tokens/call`,
  costPerCall: (v) => `Cost/call: ${v}`,
}

export const modelBreakdownCardStrings = dict(FA, EN)
