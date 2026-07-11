'use client'

import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Multiai Landing — Aurora v2
   Conversion-first, trust-building, fast.
   ═══════════════════════════════════════════════════════════════════════════ */

const FEATURES = [
  { icon: 'models' as const, title: 'همه مدل‌ها، یک پنل', desc: 'Claude، GPT، Gemini، DeepSeek و ده‌ها مدل دیگر — بدون نیاز به چند اکانت' },
  { icon: 'dashboard' as const, title: 'مدیریت هوشمند مصرف', desc: 'داشبورد لحظه‌ای، سقف مصرف و هشدار — کنترل کامل روی بودجه' },
  { icon: 'pricing' as const, title: 'قیمت‌گذاری شفاف', desc: 'تعرفه ریالی، پیش‌نمایش هزینه قبل از ارسال — بدون هزینه پنهان' },
  { icon: 'security' as const, title: 'امن و مستقل', desc: 'سرورهای اختصاصی، بدون وابستگی به تحریم — داده‌های شما محفوظ است' },
  { icon: 'code' as const, title: 'API آماده', desc: 'OpenAI-compatible — در ۲ دقیقه کلید API بسازید و متصل شوید' },
  { icon: 'chat' as const, title: 'فارسی واقعی', desc: 'رابط کاملاً فارسی، پشتیبانی از زبان فارسی در تمام مدل‌ها' },
]

const STEPS = [
  { icon: 'profile' as const, title: 'ثبت‌نام', desc: 'در ۳۰ ثانیه حساب بسازید' },
  { icon: 'wallet' as const, title: 'شارژ', desc: 'کیف پول ریالی خود را شارژ کنید' },
  { icon: 'chat' as const, title: 'چت', desc: 'با بهترین مدل‌ها گفتگو کنید' },
  { icon: 'dashboard' as const, title: 'مدیریت', desc: 'مصرف و هزینه را پیگیری کنید' },
]

const FAQ = [
  { q: 'Multiai چه فرقی با ChatGPT دارد؟', a: 'Multiai یک پلتفرم یکپارچه است — به ChatGPT، Claude، Gemini و ده‌ها مدل دیگر از یک پنل دسترسی دارید، با قیمت ریالی و بدون نیاز به VPN.' },
  { q: 'آیا نیاز به VPN دارم؟', a: 'خیر. تمام ارتباطات از طریق زیرساخت اختصاصی و داخلی مسیریابی می‌شود.' },
  { q: 'هزینه استفاده چقدر است؟', a: 'تعرفه‌ها از ۵۰۰ تومان به ازای ۱ میلیون توکن شروع می‌شود. هزینه دقیق را قبل از ارسال هر درخواست می‌بینید.' },
  { q: 'اطلاعات من امن است؟', a: 'بله. تمام ارتباطات رمزنگاری شده و داده‌ها روی سرورهای اختصاصی ذخیره می‌شوند. تحت هیچ شرایطی با شرکت‌های ثالث به اشتراک گذاشته نمی‌شوند.' },
  { q: 'چطور API key بسازم؟', a: 'بعد از ثبت‌نام، از بخش «کلید API» یک کلید جدید بسازید. endpoint ما با OpenAI-compatible است و کد نمونه برای cURL، Python و JavaScript آماده داریم.' },
]

/* ═══════════════════════════════════════════════════════════════════════════
   Hero
   ═══════════════════════════════════════════════════════════════════════════ */

function Hero({ isLoggedIn }: { isLoggedIn: boolean }) {
  return (
    <section className="relative text-center py-12 md:py-20 overflow-hidden">
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-[500px] h-[500px] rounded-full bg-[var(--accent)]/5 blur-[100px]" />
      </div>

      <div className="relative inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--bg-surface)] mb-8 text-sm">
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--positive)] opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[var(--positive)]" />
        </span>
        <span className="text-[var(--text-secondary)]">در دسترس همگان — بدون VPN</span>
      </div>

      <h1 className="relative text-4xl sm:text-5xl md:text-6xl font-extrabold leading-tight tracking-tight">
        <span className="text-gradient">هوش مصنوعی</span>
        <br />
        <span>برای همه، به زبان فارسی</span>
      </h1>

      <p className="relative text-base sm:text-lg text-[var(--text-secondary)] mt-6 max-w-xl mx-auto leading-relaxed">
        یک پنل، تمام مدل‌های هوش مصنوعی — Claude، GPT، Gemini، DeepSeek و ده‌ها مدل دیگر.
        بدون VPN، با قیمت ریالی و پشتیبانی کامل فارسی.
      </p>

      <div className="relative flex flex-col sm:flex-row gap-3 justify-center mt-8">
        <Link href={isLoggedIn ? '/chat' : '/signup'} className="btn btn-primary btn-lg text-base px-8 py-3 shadow-[var(--shadow-glow)]">
          {isLoggedIn ? 'شروع چت' : 'شروع رایگان'}
          <Icon name="arrowRight" size={18} />
        </Link>
        <Link href="/models" className="btn btn-secondary btn-lg text-base px-8 py-3">
          مشاهده مدل‌ها
        </Link>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Features
   ═══════════════════════════════════════════════════════════════════════════ */

function Features() {
  return (
    <section className="py-12">
      <div className="text-center mb-10">
        <h2 className="text-2xl md:text-3xl font-bold">چرا Multiai؟</h2>
        <p className="text-[var(--text-secondary)] mt-2 max-w-md mx-auto">
          پلتفرمی که تجربه کار با هوش مصنوعی را برای کاربران ایرانی متحول می‌کند
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {FEATURES.map((f) => (
          <div key={f.title} className="card card-interactive group">
            <div className="w-10 h-10 rounded-lg bg-[var(--accent-dim)] flex items-center justify-center mb-4 group-hover:bg-[var(--accent)]/20 transition-colors">
              <Icon name={f.icon} size={22} className="text-[var(--accent)]" />
            </div>
            <h3 className="font-bold text-base mb-1.5">{f.title}</h3>
            <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{f.desc}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   How it works
   ═══════════════════════════════════════════════════════════════════════════ */

function Steps() {
  return (
    <section className="py-12">
      <div className="text-center mb-10">
        <h2 className="text-2xl font-bold">چطور شروع کنم؟</h2>
        <p className="text-[var(--text-secondary)] mt-2">۴ قدم ساده تا دسترسی به هوش مصنوعی</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {STEPS.map((s, i) => (
          <div key={s.title} className="card card-interactive text-center relative">
            <div className="absolute -top-3 -right-3 w-8 h-8 rounded-full bg-[var(--accent)] flex items-center justify-center text-sm font-bold text-white">
              {i + 1}
            </div>
            <div className="w-12 h-12 rounded-xl bg-[var(--accent-dim)] flex items-center justify-center mx-auto mb-3">
              <Icon name={s.icon} size={24} className="text-[var(--accent)]" />
            </div>
            <h3 className="font-bold mb-1">{s.title}</h3>
            <p className="text-sm text-[var(--text-secondary)]">{s.desc}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   CTA Banner
   ═══════════════════════════════════════════════════════════════════════════ */

function CTABanner({ isLoggedIn }: { isLoggedIn: boolean }) {
  return (
    <section className="py-12">
      <div className="card text-center relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-[var(--accent)]/5 to-transparent" />
        <div className="relative">
          <h2 className="text-2xl font-bold mb-3">آماده شروع هستید؟</h2>
          <p className="text-[var(--text-secondary)] mb-6 max-w-md mx-auto">
            همین حالا ثبت‌نام کنید و به پیشرفته‌ترین مدل‌های هوش مصنوعی دسترسی پیدا کنید.
          </p>
          <Link href={isLoggedIn ? '/chat' : '/signup'} className="btn btn-primary btn-lg">
            {isLoggedIn ? 'رفتن به چت' : 'شروع رایگان'}
            <Icon name="arrowRight" size={18} />
          </Link>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   FAQ
   ═══════════════════════════════════════════════════════════════════════════ */

function FAQSection() {
  return (
    <section className="py-12">
      <div className="text-center mb-10">
        <h2 className="text-2xl font-bold">سوالات متداول</h2>
      </div>
      <div className="max-w-2xl mx-auto space-y-3">
        {FAQ.map((item) => (
          <details key={item.q} className="card group cursor-pointer">
            <summary className="font-medium text-sm flex items-center justify-between list-none">
              {item.q}
              <Icon name="arrowRight" size={16} className="text-[var(--text-muted)] group-open:rotate-90 transition-transform" />
            </summary>
            <p className="mt-3 text-sm text-[var(--text-secondary)] leading-relaxed">{item.a}</p>
          </details>
        ))}
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Page
   ═══════════════════════════════════════════════════════════════════════════ */

export default function LandingPage() {
  const { user } = useAuth()
  const isLoggedIn = !!user

  return (
    <>
      <Hero isLoggedIn={isLoggedIn} />
      <Features />
      <Steps />
      <CTABanner isLoggedIn={isLoggedIn} />
      <FAQSection />
      <footer className="text-center py-8 text-xs text-[var(--text-muted)] border-t border-[var(--border)]">
        Multiai — دسترسی به هوش مصنوعی برای همه
      </footer>
    </>
  )
}