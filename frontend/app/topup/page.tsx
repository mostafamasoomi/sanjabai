export default function TopUpPage() {
 return (
  <main className="min-h-screen bg-white p-6">
   <div className="mx-auto max-w-xl rounded-2xl border p-6">
    <h1 className="text-2xl font-bold mb-2">شارژ کیف پول</h1>
    <p className="text-sm text-gray-600 mb-6">مبلغ مورد نظر را انتخاب کنید:</p>
    <div className="grid grid-cols-2 gap-3">
     {[50000, 100000, 200000, 500000].map((amount) => (
      <div key={amount} className="rounded-2xl border p-4 flex items-center justify-between">
       <div>
        <div className="font-bold">{amount.toLocaleString('fa-IR')}</div>
        <div className="text-xs text-gray-500">تومان</div>
       </div>
       <button className="rounded-xl bg-gray-900 text-white px-3 py-2 text-sm">انتخاب</button>
      </div>
     ))}
    </div>
   </div>
  </main>
 )
}
