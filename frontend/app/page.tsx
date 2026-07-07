import Link from 'next/link'
export default function Home() {
 return (
  <main className="min-h-screen bg-white flex items-center justify-center p-6">
   <div className="w-full max-w-sm rounded-2xl border p-6 shadow-sm">
    <h1 className="text-2xl font-bold mb-2">ورود به پلتفرم</h1>
    <p className="text-sm text-gray-600 mb-6">شماره موبایل خود را وارد کنید.</p>
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); alert('درحال اتصال به سرویس OTP...') }}>
     <input className="w-full rounded-xl border px-3 py-2 text-left" placeholder="09xxxxxxxxx" />
     <button type="submit" className="w-full rounded-xl bg-gray-900 text-white py-2 text-sm">دریافت کد</button>
    </form>
    <p className="text-xs text-gray-500 mt-4"><Link className="underline" href="/pricing">قیمت‌ها</Link> · <Link className="underline" href="/dashboard">داشبورد</Link></p>
   </div>
  </main>
 )
}
