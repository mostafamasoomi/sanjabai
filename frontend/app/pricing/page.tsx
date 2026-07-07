export default function PricingPage() {
 const plans = [
  { name: 'رایگان', price: '۰', tokens: '۱۰۰K', features: ['دسترسی به مدل‌های کوچک', 'هر روز ۱۰۰ هزار توکن'] },
  { name: 'پایه', price: '۱۹۹,۰۰۰', tokens: '۱M', features: ['دسترسی به مدل‌های پیشرفته', 'هر ماه ۱ میلیون توکن', 'پشتیبانی ایمیلی'] },
  { name: 'حرفه‌ای', price: '۵۹۹,۰۰۰', tokens: '۵M', features: ['اولویت در صف', 'هر ماه ۵ میلیون توکن', 'پشتیبانی اختصاصی'] }
 ]
 return (
  <main className="min-h-screen bg-white p-6">
   <div className="mx-auto max-w-4xl">
    <h1 className="text-2xl font-bold mb-6">پلن‌ها و قیمت‌ها</h1>
    <div className="grid gap-4 sm:grid-cols-3">
     {plans.map((p) => (
      <div key={p.name} className="rounded-2xl border p-5">
       <div className="text-sm text-gray-500">پلن {p.name}</div>
       <div className="text-3xl font-bold mt-2">{p.price} <span className="text-xs text-gray-500">تومان</span></div>
       <ul className="mt-4 space-y-2 text-sm text-gray-700">
        {p.features.map((f) => (<li key={f}>• {f}</li>))}
       </ul>
       <button className="mt-5 w-full rounded-xl bg-gray-900 text-white py-2 text-sm">انتخاب پلن</button>
      </div>
     ))}
    </div>
   </div>
  </main>
 )
}
