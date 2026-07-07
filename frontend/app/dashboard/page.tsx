'use client'
import { useEffect, useState } from 'react'
import { getUsage } from '@/lib/api'
export default function DashboardPage() {
 const [usage, setUsage] = useState<{ total_spend: number; turns: number } | null>(null)
 const [error, setError] = useState('')
 useEffect(() => {
  getUsage(1).then(setUsage).catch(() => setError('خطا در دریافت اطلاعات'))
 }, [])
 return (
  <main className="min-h-screen bg-white p-6">
   <div className="mx-auto max-w-2xl">
    <h1 className="text-2xl font-bold mb-4">داشبورد کاربر</h1>
    {error && <p className="text-sm text-red-600">{error}</p>}
    {usage ? (
     <div className="grid grid-cols-2 gap-4">
      <div className="rounded-2xl border p-4">
       <div className="text-xs text-gray-500">هزینه ۳۰ روز</div>
       <div className="text-2xl font-bold">{String(usage.total_spend).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</div>
      </div>
      <div className="rounded-2xl border p-4">
       <div className="text-xs text-gray-500">تعداد مصاحبه‌ها</div>
       <div className="text-2xl font-bold">{String(usage.turns).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</div>
      </div>
     </div>
    ) : (<p className="text-sm text-gray-600">در حال بارگذاری...</p>)}
   </div>
  </main>
 )
}
