"use client"
export default function ModelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
 return (
  <select value={value} onChange={e => onChange(e.target.value)} className="rounded-xl border px-3 py-2 text-sm focus:outline-none focus:ring-2">
   <option value="gpt-4o-mini">GPT-4o mini</option>
   <option value="gpt-4o">GPT-4o</option>
   <option value="claude-3.5-sonnet">Claude 3.5</option>
  </select>
 )
}
