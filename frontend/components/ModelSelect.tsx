"use client"
import { useCatalog } from "@/lib/useCatalog"
export default function ModelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
 const { models, loading } = useCatalog()
 return (
  <select value={value} onChange={e => onChange(e.target.value)} className="rounded-xl border px-3 py-2 text-sm focus:outline-none focus:ring-2">
   {loading && <option value="" disabled>در حال بارگذاری...</option>}
   {models.map(m => (
    <option key={m.id} value={m.id}>{m.displayName}</option>
   ))}
  </select>
 )
}
