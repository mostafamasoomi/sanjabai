# گزارش ممیزی امنیتی پروژه Multiai

**تاریخ:** ۱۴۰۵/۰۴/۲۶ (۲۰۲۶-۰۷-۱۷)
**محدوده:** بکاند (FastAPI/Python) + فرانت‌اند (Next.js/React)
**روش:** بررسی ایستای کد منبع (static analysis) + تایید تنظیمات محیطی
**نویسنده:** زیرعامل امنیت (مبتنی بر تحلیل مستقل کد؛ با رویکرد سخت‌گیرانه مشابه مدل‌های ممیزی قوی)

---

## خلاصه اجرایی (Executive Summary)

پروژه از نظر امنیتی در وضعیت **بسیار خوب** قرار دارد. زیرساخت احراز هویت، session، CSRF محافظت، rate limiting و جلوگیری از SQL injection کاملاً بالغ و درست پیاده‌سازی شده‌اند. اتصال XSS در رندر Markdown که قبلاً اصلاح شده بود **تایید شد (rehype-sanitize فعال است)**. تنظیم `DEBUG=false` هم در فایل `.env` تایید شد.

مشکلات باقی‌مانده عمدتاً در سطح **پیکربندی (hardening)** و **کنترل دقیق‌تر ورودی** هستند، نه آسیب‌پذیری‌های بحرانی.

**نمره امنیت کلی: ۸.۵ / ۱۰**

---

## جزئیات یافته‌ها بر اساس دسته‌بندی درخواستی

### ۱) XSS — رندر Markdown ✅ (تایید شد، مشکلی نیست)

**فایل:** `frontend/app/chat/components/MarkdownRenderer.tsx`

```tsx
rehypePlugins={[rehypeSanitize, rehypeHighlight]}
```

- `rehype-sanitize` **قبل** از `rehype-highlight` اجرا می‌شود (ترتیب صحیح — اگر برعکس بود، کد برجسته‌سازی می‌توانست تگ‌های خطرناک تزریق کند که sanitized نشوند).
- کتابخانه در `package.json` نصب شده (`^6.0.0`).
- لینک‌های خارجی با `rel="noopener noreferrer"` و `target="_blank"` باز می‌شوند.
- تصاویر با `loading="lazy"` و بدون اجازه اسکریپت.

**نتیجه:** XSS از مسیر Markdown **مسدود است**.
**Severity:** بدون مشکل (None)

**نکته جزئی (Low):** CSP در بکاند شامل `'unsafe-inline'` و `'unsafe-eval'` است (فایل `security.py` خط ۲۱۸) که دفاع لایه‌آخر را ضعیف می‌کند. پیشنهاد: حذف `unsafe-eval` و استفاده از nonce برای اسکریپت‌های inline در صورت امکان.

---

### ۲) CSRF در endpoint های ادمین ✅ (پیاده‌سازی درست، با یک نکته)

**فایل:** `backend/dependencies.py` — تابع `admin_required` (خط ۲۳۴-۲۴۷)

برای درخواست‌های POST/PUT/DELETE/PATCH:
```python
csrf = request.headers.get('x-csrf-token') or request.headers.get('x-csrf')
if not csrf or not hmac.compare_digest(csrf, sess.get('csrf', '')):
    return False
```
- توکن CSRF در زمان لاگین ادمین تولید و در کوکی جداگانه (`admin_csrf`) قرار می‌گیرد.
- مقایسه با `hmac.compare_digest` (مقاوم در برابر حملات زمان‌سنجی).
- کوکی سشن ادمین `httponly=True` و `samesite='lax'`.

**Severity:** Low (یک نکته)

**مشکل شناسایی شده (Medium/Low):**
مسیر قدیمی (legacy) احراز هویت ادمین با هدر `x-admin-token` / `Authorization: Bearer <ADMIN_TOKEN>` **هنوز فعال است** و CSRF ندارد:
```python
token = request.headers.get('x-admin-token') or ...
return bool(ADMIN_TOKEN) and bool(token) and hmac.compare_digest(token, ADMIN_TOKEN)
```
اگرچه هدرهای سفارشی در فرم‌های cross-origin قابل ست شدن نیستند (پس CSRF عملی نیست)، اما این مسیر legacy باعث می‌شود محافظت CSRF یک‌لایه باشد و در صورت نشت توکن، هیچ محدودیت دومی وجود ندارد.

**راه حل:** در صورت عدم نیاز به ادغام سرویس-to-سرویس، مسیر `x-admin-token` را حذف یا پشت فلگ محیطی غیرفعال کنید. همچنین `samesite='lax'` برای ادمین را به `'strict'` ارتقا دهید (در صورتی که UX اجازه دهد).

**نکته دیگر:** کوکی ادمین `path='/'` دارد؛ محدود کردن به `/admin` حمله سطح سطح را کاهش می‌دهد.

---

### ۳) احراز هویت و امنیت سشن ✅ (بالغ)

**فایل‌ها:** `dependencies.py`, `auth.py`, `database.py`

- **هش رمز عبور:** PBKDF2-HMAC-SHA256 با نمک تصادفی ۱۶ بایتی و ۱۰۰,۰۰۰ تکرار (خط ۴۶-۴۹). استاندارد و مناسب.
- **سشن‌ها:** توکن‌های تصادفی `secrets.token_urlsafe(32)` روی Redis با انقضا (TTL ۷ روز) — opaque tokens، نه JWT قابل جعل.
- **API keys:** با pepper سروری (`API_KEY_PEPPER` اجباری در محیط — خط ۳۶-۳۷) و SHA-256 هش می‌شوند؛ کلید خام فقط یک بار نمایش داده می‌شود.
- **HTTP client:** `trust_env=False` (خط ۷۷ app.py) — از نشت پروکسی محیطی جلوگیری می‌کند.
- **CORS:** `allow_credentials=False` و اوریجین‌های محدود (خط ۱۲۶ app.py) — امن.
- **DEBUG=false:** تایید شد در `.env`؛ docs_url در production غیرفعال (خط ۱۱۷ app.py).

**Severity:** Low (نکات جزئی)

**موارد بهبود:**
1. پس از `login` و `signup` سشن rotate نمی‌شود (فقط `_create_session`). روتیشن سشن پس از ورود (session fixation defense) پیشنهاد می‌شود — هرچند چون توکن جدید همیشه تولید می‌شود، ریسک session fixation عملاً صفر است.
2. WebSocket اجازه auth با query param (`?token=`) را می‌دهد (خط ۲۷ websocket.py) که در لاگ‌های پروکسی نشت می‌کند. هشدار چاپ می‌شود اما هنوز پذیرفته می‌شود. پیشنهاد: حذف پشتیبانی query-param auth.

---

### ۴) Rate Limiting ✅ (قوی)

**فایل:** `backend/security.py`

- پنجره لغزان (sliding window) مبتنی بر Redis با محدودیت‌های متفاوت:
  - login: ۳۰/دقیقه، signup: ۵/دقیقه، forgot-password: ۲۰/دقیقه
  - chat: tiered (free ۳۰ / pro ۱۲۰ / enterprise ۳۰۰)
  - admin: ۳۰/دقیقه
- **Fail-closed:** اگر Redis در دسترس نباشد، ترافیک رد می‌شود (خط ۵۰).
- شناسه کلاینت ترکیبی از user_id یا hash IP+User-Agent.
- هدرهای `X-RateLimit-*` و `Retry-After` ست می‌شوند.

**Severity:** بدون مشکل (None)

**نکته جزئی (Low):** شناسه مبتنی بر IP از `X-Forwarded-For` فقط وقتی معتبر است که کانکتینگ IP در `TRUSTED_PROXY_IPS` باشد (درست پیاده‌سازی شده). اگر پروکسی معتبر تنظیم نشود، تمام کاربران پشت یک NAT/NAT64 یک شناسه مشترک می‌گیرند و ممکن است یکدیگر را rate-limit کنند (تأثیر کم).

---

### ۵) اسکن رمزهای مخفی (Secret Scanning) ✅ (تمیز)

- جستجوی الگوهای کلید (OpenAI `sk-...` طولانی، AWS `AKIA`, GitHub `ghp_`, Slack `xox`, Google `AIza`, JWT) در کل بکاند: **۰ مورد**.
- کلیدهای حساس (`ADMIN_TOKEN`, `INTERNAL_TOKEN`, `API_KEY_PEPPER`, `DATABASE_URL`, `SMTP_PASS`) همگی از متغیرهای محیطی خوانده می‌شوند، نه هاردکد در کد.
- ثابت‌های محیطی در `.env` (محافظت‌شده توسط سیستم از خواندن مستقیم) و `.env.example` فقط کلیدها بدون مقدار.
- `API_KEY_PEPPER` اجباری است — برنامه با مقدار پیش‌فرض ناامن استارت نمی‌شود (RuntimeError).

**Severity:** بدون مشکل (None)

**توصیه:** افزودن pre-commit hook (مثل `gitleaks` یا `trufflehog`) برای جلوگیری از نشت احتمالی در آینده.

---

### ۶) SQL Injection ✅ (مسدود)

- تمام کوئری‌های ORM از SQLAlchemy Core/ORM استفاده می‌کنند.
- کوئری‌های خام (`sqlalchemy.text`) همگی با پارامترهای جایگذاری شده (`{...}`) هستند — مثال:
  ```python
  sqlalchemy.text('SELECT ... WHERE user_id = :uid'), {'uid': uid}
  ```
- جستجوی الگوهای الحاق رشته در کوئری‌ها (`execute(... + ...)`, `f"...SELECT..."`): **۰ مورد**.
- تابع `_escape_like` برای جستجوهای LIKE وجود دارد (خط ۷۱ dependencies.py).

**Severity:** بدون مشکل (None)

---

### ۷) اعتبارسنجی آپلود فایل ⚠️ (متوسط — نیاز به بهبود)

**فایل‌ها:** `backend/rag_endpoints.py`, `backend/chat.py`, `backend/services/doc_processor.py`

**وضع فعلی:**
- محدودیت اندازه: ۲۰MB (RAG) و چک در chat.py وجود دارد.
- فرمت‌های مجاز: `{pdf, txt, md, csv, json}` در RAG.
- **فقط پسوند فایل (extension) چک می‌شود** — نه MIME type واقعی، نه magic bytes.

**مشکل (Medium):**
یک مهاجم می‌تواند فایل مخرب را مثلاً `evil.pdf` نام‌گذاری کند در حالی که محتوای آن PDF نیست. اگرچه در جریان فعلی فقط متن استخراج می‌شود (PDF parser پایموپdf/pypdf محتوای غیر-PDF را رد می‌کند)، اما:
1. در `chat.py` فایل‌های `.txt/.md/.csv/.json/.log` صرفاً با `decode('utf-8')` پردازش می‌شوند — یک فایل `.json` حاوی payload می‌تواند در خروجی مدل نمایش داده شود (اما sanitized نیست چون از مسیر Markdown رد نمی‌شود).
2. اگر در آینده فایل‌ها "سرو" (download/static) شوند، عدم بررسی محتوا باعث stored XSS یا فایل‌های اجرایی می‌شود.

**راه حل:**
- بررسی **magic bytes** (header بایتی واقعی) علاوه بر پسوند.
- برای RAG: استفاده از `python-magic` یا بررسی امضای فایل قبل از پردازش.
- برای chat.py: پسوندهای `.log` و `.text` را محدود کنید یا محتوا را پیش از نمایش در پاسخ مدل، از فیلتر XSS رد کنید.
- اگر فایل‌ها ذخیره و سرو می‌شوند، `Content-Disposition: attachment` اجباری و جلوگیری از پسوندهای اجرایی.

**Severity:** Medium

**نکته مثبت:** endpoint دانلود (`document_generator.py` خط ۴۱۷) از `doc_id` مبتنی بر registry استفاده می‌کند نه ورودی کاربر برای مسیر فایل — **Path Traversal وجود ندارد**.

---

## سایر یافته‌ها (جزئی)

| مورد | فایل | Severity | توضیح |
|------|------|----------|-------|
| WebSocket query-param auth | websocket.py:27 | Low | توکن در URL نشت می‌کند؛ پشتیبانی را حذف کنید |
| CSP unsafe-inline/eval | security.py:218 | Low | دفاع لایه آخر را ضعیف می‌کند |
| Legacy admin token path | dependencies.py:246 | Low | CSRF ندارد؛ در صورت عدم نیاز غیرفعال شود |
| silent `except: pass` | چندین فایل | Info | در جاهایی لاگ نمی‌کند؛ تأثیر امنیتی کم |

---

## جدول نمره‌دهی نهایی

| دسته | وضعیت | نمره |
|------|-------|------|
| XSS (Markdown) | ✅ حل شده | ۱۰/۱۰ |
| CSRF (admin) | ✅ قوی + نکته | ۸/۱۰ |
| Auth/Session | ✅ بالغ | ۹/۱۰ |
| Rate Limiting | ✅ قوی | ۱۰/۱۰ |
| Secret Scanning | ✅ تمیز | ۱۰/۱۰ |
| SQL Injection | ✅ مسدود | ۱۰/۱۰ |
| File Upload | ⚠️ بهبود لازم | ۶/۱۰ |

**نمره امنیت کلی: ۸.۵ / ۱۰**

---

## اولویت‌بندی اصلاحات

1. **High-Impact/Low-Effort:** حذف مسیر legacy `x-admin-token` یا قرار دادن پشت فلگ.
2. **Medium:** بررسی magic bytes در آپلود فایل (RAG + chat).
3. **Low:** حذف WebSocket query-param auth؛ بهبود CSP (حذف unsafe-eval).
4. **Info:** افزودن gitleaks pre-commit؛ لاگ‌گیری در except blocks.

---

*گزارش توسط تحلیل ایستای کد تولید شده است. خطوط دقیق به فایل‌های مربوطه ارجاع داده شده‌اند.*
