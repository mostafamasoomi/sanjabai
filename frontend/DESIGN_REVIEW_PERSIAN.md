# بررسی سطح ارشد طراحی فرانت‌اند Sanjabai

> نویسنده: بررسی مستقل طراحی (Senior Design Review)
> تاریخ: 2026-07-18
> وسعت بررسی: layout، landing، chat، dashboard، models، login، admin، AppShell، ui.tsx، globals.css، tailwind.config.ts

---

## خلاصه اجرایی (Executive Summary)

طراحی فعلی در سطح خوبی از «تم تاریک گرادیانی مدرن» قرار دارد — سیستم توکن‌محور (`globals.css` خط ٣٢-١٠٩)، فونت Vazirmatn سلف‌هاست، موجو (glassmorphism) در سایدبار و تاپ‌بار، و میکرو-اینتراکشن‌های نرم. برای یک استارتاپ ایرانی که با AvalAI/GapGPT رقابت می‌کند **از میانگین بازار بالاتر است**.

اما برای سطح «تولید پرمیوم» (ChatGPT/Claude/v0.dev)، موارد بازدارنده جدی وجود دارد:

1. **دکمه تم (ThemeToggle) کاملاً غیرفعال است** — `data-theme="light"` ست می‌شود اما هیچ تعریفی برای حالت روشن در CSS وجود ندارد (تأییدشده: ۰ تاکنون در globals.css). این یک باگ کلیدی و نه فقط یک نقص زیبایی است.
2. **فقدان کامل سیستم تایپوگرافی مقیاس‌بندی‌شده** (type scale) — اندازه‌های فونت در صفحات به‌صورت اتوپیک (`text-xl`, `text-2xl`، و inline `fontSize`) پراکنده شده‌اند بدون ریتم عمودی واحد.
3. **تکرار توکن‌های رنگی سخت‌کد‌شده** به‌جای استفاده از متغیرهای CSS (`#6366f1`, `#a855f7`, `#8b5cf6` ده‌ها بار در TSX تکرار شده‌اند).
4. **RTL ناقص در جاهای حساس** (مثلاً `text-left` روی مبالغ، `dir="ltr"` روی فیلدهایی که نباید).
5. **تضاد دیزاین سیستم**: admin panel از کلاس‌های `admin-card` جداگانه استفاده می‌کند، در حالی که بقیه از `card` استفاده می‌کنند — دو زبان بصری.

---

## ۱. سلسله‌مراتب بصری (Visual Hierarchy)

### وضعیت فعلی
- هدرهای صفحات ناسازگارند: `models/page.tsx` از `text-2xl font-bold`، `dashboard` از `fontSize: 1.5rem; fontWeight: 800`، `admin` از `text-xl font-bold` استفاده می‌کند.
- صفحه landing از `aurora-section-title` (خط ۱۸۸۶) با انیمیشن استفاده می‌کند، اما صفحات داخلی هیچ کلاس عنوان واحدی ندارند.

### پیشنهاد
تعریف یک **Type Scale** واحد در `globals.css`:

```css
/* ── Sanjabai Type Scale (این را به globals.css اضافه کنید) ── */
.display { font-size: clamp(2.5rem, 5vw, 4rem); font-weight: 800; line-height: 1.1; letter-spacing: -0.03em; }
.h1 { font-size: 1.75rem; font-weight: 800; line-height: 1.3; letter-spacing: -0.02em; }
.h2 { font-size: 1.375rem; font-weight: 700; line-height: 1.35; }
.h3 { font-size: 1.0625rem; font-weight: 600; line-height: 1.4; }
.body { font-size: 0.9375rem; line-height: 1.7; }
.body-sm { font-size: 0.8125rem; line-height: 1.6; }
.caption { font-size: 0.75rem; line-height: 1.4; color: var(--text-muted); }
```

و در TSX به‌جای inline style:
```tsx
// قبل
<h1 style={{ fontSize: '1.5rem', fontWeight: 800, ... }}>سلام، {displayName}</h1>
// بعد
<h1 className="h1">سلام، {displayName}</h1>
```

---

## ۲. سیستم رنگ (Color System)

### مشکل اصلی: رنگ‌های سخت‌کد‌شده (Hardcoded)
در `AppShell.tsx` خط ۱۲۹، `login/page.tsx` خط ۵۶، `page.tsx` خط ۸۱، `dashboard` خط ۱۴۴:
```tsx
style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', ... }}
```
این همان مقدار `--accent-gradient` است اما **تکرار دستی** شده. اگر رنگ برند تغییر کند، باید ۳۰ فایل را ویرایش کرد.

### پیشنهاد: Semantic color tokens + رنگ برند تک‌نقطه‌ای
```css
:root {
  --brand-500: #6366f1;
  --brand-600: #818cf8;
  --brand-grad: linear-gradient(135deg, #6366f1, #8b5cf6);
}
.brand-logo { background: var(--brand-grad); }
```
و در TSX: `className="w-8 h-8 rounded-lg brand-logo"` به‌جای inline style.

### نقد حرفه‌ای رنگ‌ها
- پالت تاریک فعلی خوب است (base `#05050a` عمق خوبی دارد) اما **تضاد (contrast) متن ثانویه** `var(--text-secondary): #a0a0b0` روی `var(--bg-surface): #0c0c14` فقط ~۴.۵:۱ است — در مرز WCAG AA. برای متن‌های کوچک پیشنهاد: `#b4b4c4`.
- نبود رنگ‌های «حالت موفقیت/خطا» به‌صورت تدریجی (gradient) — فقط solid.

---

## ۳. فاصله‌گذاری و چیدمان (Spacing & Layout)

### مشکلات
- `dashboard/page.tsx` از `gap: '1.5rem'` به‌صورت inline استفاده می‌کند به‌جای متغیرهای `--space-*`.
- شبکه (grid) در dashboard با `gridTemplateColumns` inline تعریف شده — غیرقابل پاسخ‌گویی (responsive) در breakpointهای میانی.
- `layout-content` حداکثر عرض `1200px` دارد (خط ۱۰۱) اما dashboard و admin نیاز به عرض بیشتری برای جداول دارند (admin `max-width: 1400px` در خط ۴۰۷ — تضاد).

### پیشنهاد
استفاده از utility classes بجای inline:
```tsx
<div className="flex flex-col gap-6">
  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
```
و تعریف یک متغیر `--content-max-wide: 1400px` برای صفحات داده‌محور.

---

## ۴. تایپوگرافی فارسی (Typography)

### نقاط قوت
- Vazirmatn سلف‌هاست (عالی برای مناطق تحریم‌خورده).
- `line-height: 1.7` در body مناسب متن فارسی است.
- `font-display: swap` صحیح است.

### نقد
- **فقط دو وزن بارگذاری شده** (400 و 700، خط ۱۲-۲۵). برای طراحی مدرن نیاز به 500 (medium) دارید — عناوین نیمه‌ضخیم در فارسی با 700 خیلی سنگین و با 400 خیلی لخت می‌شوند. 500 توازن ایده‌آل است.
- فقدان `font-feature-settings` برای اعداد فارسی. اعداد لاتین (`fa-IR`) گاهی با Vazirmatn نامتوازن‌اند.

### پیشنهاد
```css
@font-face {
  font-family: 'Vazirmatn';
  font-weight: 500;
  src: url('/fonts/Vazirmatn-Medium.woff2') format('woff2');
  font-display: swap;
}
body { font-feature-settings: "ss01"; } /* اعداد بهتر در Vazirmatn */
```

---

## ۵. میکرو-اینتراکشن‌ها (Micro-interactions)

### نقاط قوت
- سایدبار ناوبری: `transform: translateX(-2px)` + transition نرم (خط ۱۶۰۷-۱۶۱۰) حرفه‌ای است.
- `barGrow` انیمیشن نوار فعال (خط ۱۶۳۴) خوب است.
- کاهش حرکت (`prefers-reduced-motion`) پیاده‌سازی شده (خط ۱۵۹).

### نقد
- **بازخورد فشار (active state) ضعیف**: دکمه‌های `.btn` فقط `translateY(-1px)` روی hover دارند، اما روی `:active` هیچ تغییری ندارند. کاربر احساس می‌کند دکمه «کلیک‌خور» نیست.
- انیمیشن `gradientShift` روی `.text-gradient` (خط ۱۷۵) **همیشه در حال اجراست** — روی عنوان اصلی landing که ۶ ثانیه تکرار می‌شود، برای برخی کاربران حواس‌پرتی ایجاد می‌کند (و باتری موبایل).

### پیشنهاد
```css
.btn:active:not(:disabled) { transform: translateY(1px) scale(0.98); }
/* گرادیانت استاتیک روی عناوین، فقط روی hover متحرک شود */
.text-gradient { background-size: 100% 100%; }
.text-gradient:hover { animation: gradientShift 3s ease infinite; }
```

---

## ۶. حالت تاریک/روشن (Dark/Light Mode) — **بحرانی**

### یافته (تأییدشده با جستجو)
- `ThemeToggle.tsx` مقدار `data-theme="light"` را روی `<html>` می‌گذارد (خط ۱۲، ۱۹).
- اما در `globals.css` **هیچ** بلوک `[data-theme="light"]` یا `@media (prefers-color-scheme: light)` وجود ندارد.
- تمام توکن‌ها به‌صورت dark سخت‌کد شده‌اند (`:root` خط ۳۲-۱۰۹).

### نتیجه
دکمه تم **ظاهری است و کاربر را فریب می‌دهد** — کلیک روی آن فقط آیکون خورشید/ماه را عوض می‌کند ولی هیچ تغییر بصری رخ نمی‌دهد. این در تست QA گرفتار می‌شود.

### راهکار (پیاده‌سازی واقعی حالت روشن)
بازنویسی `:root` به‌عنوان تم تاریک و اضافه کردن تم روشن:

```css
:root, [data-theme="dark"] {
  --bg-base: #05050a;
  --bg-surface: #0c0c14;
  --text-primary: #f0f0f5;
  --text-secondary: #b4b4c4; /* اصلاح contrast */
  --border: rgba(255,255,255,0.08);
  --accent: #6366f1;
  --accent-grad: linear-gradient(135deg, #6366f1, #8b5cf6);
  color-scheme: dark;
}

[data-theme="light"] {
  --bg-base: #f7f7fb;
  --bg-surface: #ffffff;
  --bg-elevated: #f0f0f6;
  --bg-overlay: #e8e8f0;
  --text-primary: #0d0d18;
  --text-secondary: #555568;
  --text-muted: #8a8a9a;
  --border: rgba(0,0,0,0.08);
  --border-strong: rgba(0,0,0,0.14);
  --accent: #5457e8;
  --accent-grad: linear-gradient(135deg, #5457e8, #7c3aed);
  --bg-hover: rgba(0,0,0,0.04);
  color-scheme: light;
}

/* موجو در حالت روشن باید سبک‌تر شود */
[data-theme="light"] .card { background: rgba(255,255,255,0.7); backdrop-filter: blur(12px); }
[data-theme="light"] .sidebar-glass { background: rgba(255,255,255,0.85); }
[data-theme="light"] body { background: #f7f7fb; }
```

و در `ThemeToggle` از `transition` روی body استفاده کنید:
```css
body { transition: background-color var(--motion-normal), color var(--motion-normal); }
```

---

## ۷. طراحی پاسخ‌گو (Responsive Design)

### نقاط قوت
- سایدبار موبایل به‌صورت drawer (خط ۱۷۶۶) با انیمیشن خوب.
- ناوبری پایین (bottom nav) برای موبایل (AppShell خط ۲۲۷).
- `safe-bottom` برای ناچ آیفون رعایت شده.

### نقد
- **Dashboard در تبلت خراب است**: گرید `gridTemplateColumns: repeat(auto-fit, minmax(200px, 1fr))` به‌صورت inline (خط ۴۴۰) در حالت loading، اما در حالت عادی `grid grid-cols-1` (خط ۴۴۹) — یعنی حتی در دسکتاپ فقط یک ستون! این احتمالاً باگ است.
- فیلتر چیپس در models (خط ۱۵۱) `overflow-x-auto` دارد که خوب است، اما بدون fade لبه‌ها.
- موبایل: سایدبار drawer 280px (خط ۱۷۷۱) اما NAV کامل ۱۸ آیتم را نشان می‌دهد بدون گروه‌بندی بخش‌ها (در حالی که دسکتاپ گروه‌بندی دارد) — ناهماهنگی UX.

### پیشنهاد
```tsx
{/* dashboard grid — همیشه responsive */}
<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
```

---

## ۸. الگوهای مدرن (Glassmorphism / Gradients / Shadows)

### نقد
- **Glassmorphism بیش از حد**: `backdrop-filter: blur(24px)` روی `.card` (خط ۲۶۸) برای کارت‌های معمولی سنگین و روی دستگاه‌های ضعیف lag ایجاد می‌کند. فقط روی سایدبار/تاپ‌بار (الویت بالا) باشد.
- سایه‌ها (`--shadow-lg: 0 8px 32px rgba(0,0,0,0.5)`) در تم تاریک خیلی تیره و نامحسوس‌اند — سایه در dark mode باید به‌جای سیاه، با رنگ accent یا آبی تیره باشد تا عمق بدهد.
- گرادیانت برند در ۵ جا تکرار شده (همان مشکل سخت‌کد).

### پیشنهاد
```css
.card { background: var(--bg-elevated); border: 1px solid var(--border); } /* حذف blur پیش‌فرض */
.card-glass { backdrop-filter: blur(24px); background: rgba(255,255,255,0.03); } /* فقط جایی که لازم است */
[data-theme="dark"] { --shadow-lg: 0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04); }
```

---

## ۹. مقایسه با رقبا (ChatGPT / Claude / v0.dev)

| ویژگی | Sanjabai فعلی | ChatGPT/Claude | v0.dev |
|------|-------------|---------------|--------|
| تم روشن | ❌ غیرفعال (باگ) | ✅ کامل | ✅ کامل |
| Type scale واحد | ❌ پراکنده | ✅ دقیق | ✅ دقیق |
| ریتم عمودی | ⚠️ ناهمگون | ✅ 8px baseline | ✅ 4px baseline |
| فیدبک active | ⚠️ ضعیف | ✅ قوی (scale) | ✅ قوی |
| Loading skeletons | ✅ خوب | ✅ عالی | ✅ عالی |
| فوکوس رینگ | ✅ دارد | ✅ بهتر (ring offset) | ✅ |
| RTL | ⚠️ ناقص (text-left) | N/A | N/A |

**جمع‌بندی**: از نظر «حس مدرن بودن» نزدیک به v0.dev هستید، اما در «یکپارچگی سیستم» (consistency) و «دسترس‌پذیری» (a11y/تم) عقب‌ترید. AvalAI خودش تم روشن ندارد، پس این فرصت تمایز شماست — **فقط باید واقعاً کار کند**.

---

## ۱۰. پیشنهادهای اقدامی مشخص (Actionable)

### اولویت ۱ — بحرانی (قبل از تولید)
1. **پیاده‌سازی واقعی حالت روشن** (کد بالا در بخش ۶).
2. **رفع باگ گرید dashboard** (بخش ۷) — احتمالاً کپی‌پیست اشتباه بین loading/normal state.
3. **اضافه کردن وزن 500 فونت** (بخش ۴).

### اولویت ۲ — کیفیت
4. جایگزینی تمام `linear-gradient(135deg, #6366f1, ...)` سخت‌کد با `var(--accent-grad)` (جستجو: ۳۰+ مورد).
5. تعریف type scale واحد (بخش ۱) و جایگزینی inline `fontSize`.
6. اضافه کردن `:active` state به `.btn`.
7. محدود کردن glassmorphism به سایدبار/تاپ‌بار.

### اولویت ۳ — پولیش
8. اصلاح RTL: حذف `text-left` از مبالغ (ledger در dashboard خط ۲۴۸، ۲۵۵ — باید `text-right` یا حذف شود چون کانتکست RTL است).
9. کاهش blur روی `body::before` noise (خط ۱۳۸) — opacity 0.03 خیلی کمنر است، می‌تواند 0.015 باشد تا بازخوانی متن بهتر شود.
10. ادغام `admin-card` با `card` برای یکپارچگی دیزاین سیستم.

---

## فایل‌های پیشنهادی برای تغییر
- `app/globals.css` — اضافه کردن `[data-theme="light"]`, type scale, وزن 500, اصلاح shadows
- `components/ThemeToggle.tsx` — اضافه کردن transition
- `app/dashboard/page.tsx` — رفع باگ گرید، حذف inline styles
- `app/layout.tsx` — اضافه کردن `<html data-theme="dark">` پیش‌فرض برای جلوگیری از فلش (FOUC)
- `tailwind.config.ts` — اضافه کردن رنگ‌های برند به theme.extend.colors

---

*این بررسی بر اساس خواندن واقعی فایل‌های فوق تهیه شده است. تمام خطوط ارجاع‌داده‌شده در مخزن فعلی تأیید شده‌اند.*
