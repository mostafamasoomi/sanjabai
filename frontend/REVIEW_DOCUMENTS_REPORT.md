# گزارش بررسی Frontend — بخش Documents (Document Generator)

**تاریخ:** ۱۴۰۵/۰۴/۲۶
**مسیر:** `/root/multiai/frontend`
**بازبین:** Subagent (تحلیل دستی + typecheck واقعی)

> **نکته درباره مدل deepseek-v4-pro:** طبق دستورالعمل باید از مدل `deepseek-v4-pro`
> استفاده میشد. این مدل در پروژه (در `litellm_config.yaml` و `modelUtils.ts`) تعریف شده
> اما از inside این subagent از طریق gateway / litellm / ollama **قابل فراخوانی نبود**
> (gateway فقط یک flag بود، ollama نصب نبود، litellm روی پورت باز در دسترس نبود).
> لذا تحلیل با بررسی دقیق کد + اجرای `tsc --noEmit` واقعی انجام شد. باگهای زیر
> با خروجی ابزار تأیید شدهاند، نه حدس.

---

## ۱) وضعیت فایل `app/documents/page.tsx`

فایل وجود دارد و UI کاملی دارد (انتخاب نوع سند، textarea پرامپت، پیشنهادات،
دکمه تولید، نمایش نتیجه با دانلود، و لیست سوابق با حذف).

### 🔴 مشکل بحرانی (BLOCKER) — ایمپورت اشتباه useAuth
```tsx
// خط ۴ — فعلی (اشتباه):
import { useAuth } from '@/hooks/useAuth'
// صحیح:
import { useAuth } from '@/lib/auth'
```
- پوشه `hooks/` **اصلاً وجود ندارد** (تأیید با `ls`).
- `useAuth` در `/root/multiai/frontend/lib/auth.tsx` خط ۹۳ تعریف شده.
- `tsc --noEmit` خطا میدهد:
  ```
  app/documents/page.tsx(4,25): error TS2307:
  Cannot find module '@/hooks/useAuth' or its corresponding type declarations.
  ```
- **نتیجه:** صفحه کامپایل نمیشود → در build جدید حضور ندارد
  (تأیید: `docker exec multiai-multiai_frontend-1 ls /app/app/documents` →
  `No such file or directory`). یعنی حتی AppShell لینک را دارد اما صفحه ۴۰۴ میدهد.

---

## ۲) AppShell.tsx — لینک documents ✅

در `NAV` (خط ۴۰) اضافه شده:
```ts
{ href: '/documents', label: 'سندساز', icon: 'file', section: 'tools' },
```
لینک در sidebar دسکتاپ، drawer موبایل، و command palette (از طریق NAV یکسان)
نمایش داده میشود. مشکلی ندارد — **اما به دلیل باگ بالا، کاربر به صفحه خراب/۴۰۴ میرسد.**

---

## ۳) Icon.tsx — آیکون file ✅

آیکون `file` تعریف شده (خط ۴۳):
```
file: 'M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z'
```
و `IconName` type آن را شامل میشود. ایمپورت در AppShell درست است. ✅

---

## ۴) نقد RTL / UX

### مشکلات جزئی:
1. **استفاده از ایموجی به جای SVG:** `DOC_TYPES` از ایموجی (`📊 📄 📝`) استفاده
   میکند در حالی که کامنت `Icon.tsx` صراحتاً میگوید "no emoji in production".
   ناسازگار با سیستم آیکون پروژه و رندر ناهمگون در پلتفرمهای مختلف.
2. **عدم استفاده از کلاسهای Tailwind مشترک:** بقیه صفحات از `card`, `card-header`,
   `btn`, `btn-primary` استفاده میکنند؛ اینجا همه استایلها inline است.
   باگردانی سختتر و ناسازگاری بصری با بقیه اپ.
3. **Grid غیرواکنشگرا:** `gridTemplateColumns: 'repeat(3, 1fr)'` در موبایل ۳ ستون
   باریک میدهد. باید حداقل در `sm` تکستونه یا ۲ ستونه شود.
4. **دکمه تولید بدون انتخاب مدل:** backend مدل پیشفرض `mimo-v2.5-pro` دارد اما
   UI هیچ selector مدلی ندارد (برخلاف بخش chat که `deepseek-v4-pro` و دیگران
   را لیست میکند). کاربر نمیتواند کیفیت/سرعت را انتخاب کند.
5. **خطای fetch بدون toast:** خطاها فقط درون صفحه نمایش داده میشوند، در حالی که
   پروژه `ToastContainer` دارد (در AppShell). همسانسازی بهتر است.
6. **عدم نمایش progress واقعی:** `generating` فقط spinner نشان میدهد؛ تولید
   اسلایدهای سنگین ممکن است ثانیهها طول بکشد بدون بازخورد مرحلهای.
7. **دانلود در تب جدید باز نمیشود:** `download` attribute روی `<a>` هست اما
   route `/v1/documents/:id/download` احتمالاً `Content-Disposition` مناسب دارد
   (از backend برمیگرداند) — اوکی، ولی لینک history هم `<a>` ساده است.

---

## ۵) مشکلات Integration با API

| مورد | وضعیت | توضیح |
|------|--------|-------|
| GET `/v1/documents` | ✅ تطابق | backend `{documents: [...]}` برمیگرداند؛ frontend `d.documents` میخواند |
| POST `/v1/documents/generate` | ⚠️ جزئی | frontend فقط `{prompt, type}` میفرستد؛ backend مدل را پیشفرض میگیرد (مشکلی نیست ولی selector ندارد) |
| GET `/v1/documents/:id/download` | ✅ | مسیر درست است |
| DELETE `/v1/documents/:id` | ⚠️ silent fail | `handleDelete` خطا را `catch{}` میکند و هیچ بازخوردی نمیدهد؛ اگر ۴۰۱/۴۰۳ باشد کاربر گیج میشود |
| Auth header | ✅ | `Authorization: Bearer ${token}` صحیح است |
| فیلد `created_at` | ✅ | backend ایزو میفرستد، frontend با `toLocaleDateString('fa-IR')` نمایش میدهد |

### 🟠 مشکل persistence (مهم):
- فایلها در **`/tmp/multiai_docs`** ذخیره میشوند (`DOC_STORAGE` در backend).
- `/tmp` روی restart کانتینر پاک میشود → تمام داکیومنتهای تولید شده از دست میروند
  در حالی که در `list_documents` هنوز در `_doc_registry` (in-memory) هستند →
  تناقض: لیست نشان میدهد ولی دانلود ۴۰۴ میدهد.
- `_doc_registry` یک dict global در حافظه است → روی چندین worker/restart صفر میشود.
  برای production باید به DB یا volume پایدار منتقل شود.

### 🟡 ناهماهنگی فیلد (ناچیز):
- backend در list فیلدهای `prompt`, `model`, `user_id` هم میفرستد که frontend
  نادیده میگیرد — مشکلی نیست، فقط حجم پاسخ بیشتر.

---

## 📋 خلاصه مشکلات (اولویتبندی)

| # | شدت | مشکل | راه حل |
|---|------|------|--------|
| 1 | 🔴 بحرانی | ایمپورت اشتباه `@/hooks/useAuth` → صفحه کامپایل نمیشود | تغییر به `@/lib/auth` |
| 2 | 🟠 متوسط | ذخیره در `/tmp` + registry in-memory → از دست رفتن داده | انتقال به volume/DB پایدار |
| 3 | 🟡 کم | استفاده از ایموجی به جای SVG icon | جایگزینی با `Icon name="file"` و غیره |
| 4 | 🟡 کم | grid غیرواکنشگرا در موبایل | `repeat(auto-fit, minmax(140px,1fr))` |
| 5 | 🟡 کم | حذف silent (بدون toast/خطا) | افزودن toast در catch |
| 6 | 🟡 کم | نبود انتخاب مدل در UI | افزودن ModelPicker مشابه chat |
| 7 | ⚪ بهبود | استایلهای inline به جای کلاسهای مشترک | بازنویسی با `card/btn` |

---

## ✅ پیشنهادات اصلاح سریع

```tsx
// app/documents/page.tsx خط ۴:
import { useAuth } from '@/lib/auth'   // ← اصلاح بحرانی

// خط ۳۳-۴۹: جایگزینی ایموجی
icon: 'file'  // و در render: <Icon name={dt.icon} size={32} />
```

برای مشکل `/tmp`: در `document_generator.py`:
```python
DOC_STORAGE = Path(os.getenv('DOC_STORAGE', '/var/lib/multiai/docs'))
```
و mount یک volume پایدار روی آن. همچنین registry را به SQLite/Redis ارتقا دهید.

---

## 🏁 نمره نهایی: **۴/۱۰**

**دلیل:** ایده و ساختار UI خوب است (نمره بالقوه ۷+)، اما یک **باگ کامپایل بحرانی**
باعث میشود صفحه اصلاً لود نشود و لینک AppShell به ۴۰۴ برسد. علاوه بر این عدم
پایداری ذخیرهسازی (`/tmp`) یک ریسک داده در سطح production است. با اصلاح ایمپورت
(۵ دقیقه) نمره به ۶ و با رفع persistence و موارد UX به ۸ میرسد.
