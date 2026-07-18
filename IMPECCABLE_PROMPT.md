# پرامپت برای ربات هرمس — اعمال impeccable روی Multiai Frontend

## زمینه
پروژه Multiai یه اپلیکیشن SaaS هست با:
- **Backend**: FastAPI (Python) + PostgreSQL 16 + Redis + LiteLLM
- **Frontend**: Next.js + React + Tailwind CSS
- **مسیر فرانتاند**: `/root/multiai/frontend/`
- **پورت فرانتاند**: 3003 (Docker container: multiai-multiai_frontend)
- **صفحات**: chat, dashboard, admin, assistants, models, documents, compare, login, onboarding, api-keys

## چی باید انجام بدی

### مرحله ۱: محیط رو بشناس
1. برو به `/root/multiai/frontend/`
2. ساختار پروژه رو بخون (`app/`, `components/`, `globals.css`)
3. فایل `.impeccable/skill/SKILL.md` رو بخون (skill impeccable نصبه)
4. `DESIGN.impeccable.md` و `PRODUCT.impeccable.md` رو بخون

### مرحله ۲: اولین audit
از skill impeccable استفاده کن و:
1. صفحات کلیدی (`chat`, `dashboard`, `admin`) رو اسکن کن برای anti-patterns
2. `globals.css` (113KB!) رو بررسی کن — ببین آیا:
   - Anti-pattern های شناخته شده (card-in-card, gray-on-color, purple-blue-gradient, inter-everything) هست
   - CSS بیش از حد/تکراری/مرده وجود داره
3. Tailwind config رو چک کن — آیا design token ها (رنگ، spacing، type scale) تعریف شدن
4. کامپوننت‌های UI رو بررسی کن (`components/ui/Icon.tsx` و بقیه)

### مرحله ۳: گزارش بنویس
یه فایل `DESIGN_AUDIT_MULTIAI.md` توی `/root/multiai/` بنویس شامل:
- Anti-patterns پیدا شده (با file:line و severity)
- پیشنهادات بهبود (با کد مثال)
- اولویت‌بندی (P0=critical, P1=high, P2=medium, P3=low)

### مرحله ۴: fix های P0 و P1
فقط critical و high severity ها رو fix کن:
- `globals.css` رو تمیز کن (CSS مرده/تکراری حذف کن)
- Anti-pattern های critical رو fix کن
- فایلها رو commit نکن (فقط گزارش + fix)

### مرحله ۵: گزارش نهایی
خلاصه‌ای از:
- چند anti-pattern پیدا شد
- چندتاشون fix شد
- اسکور طراحی (1-10) قبل و بعد

## نکات مهم
- فایل `app/globals.css` رو با `read_file` بخون (113KB ممکنه نیاز به pagination داشته باشه)
- Tailwind classes رو توی فایلهای `.tsx` جستجو کن با `search_files`
- داکر کانتینر frontend داره اجراست — **ریستارت نکن**
- backend API رو تغییر نده
- فقط فرانتاند / CSS / component

## خروجی مورد انتظار
1. فایل `DESIGN_AUDIT_MULTIAI.md` با گزارش کامل
2. Fix های P0/P1 اعمال شده
3. اسکور نهایی طراحی
