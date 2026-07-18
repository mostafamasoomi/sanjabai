"use client"
import { useState, useEffect } from "react"

// ponytail: recharts barrel optimization breaks build, stub until fixed
export default function AdminCharts({ data }: { data?: any }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] p-6">
      <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-4">نمودار مصرف</h3>
      <div className="text-center text-[var(--text-muted)] py-8">
        نمودارها در آپدیت بعدی فعال میشوند
      </div>
    </div>
  )
}
