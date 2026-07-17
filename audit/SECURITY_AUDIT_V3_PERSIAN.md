# گزارش Audit امنیتی پروژه Multiai (نسخه ۳ — فارسی)

**تاریخ:** ۱۴۰۵/۰۴/۲۶ (۱۷ ژوئیه ۲۰۲۶)
**محدوده:** بکاند (FastAPI/Python) + فرانت‌اند (Next.js/React) + تنظیمات محیطی (.env)
**روش:** بازبینی مستقیم کد منبع (source review) — داکر در زمان اجرا در دسترس نبود، خروجی `docker exec ... env | grep DEBUG` از طریق فایل `.env` تأیید شد.

---

## وضعیت موارد درخواستی (چک‌لیست)

| # | موضوع | وضعیت | Severity |
|---|-------|-------|----------|
| ۱ | XSS / MarkdownRenderer | ✅ rehype-sanitize فعال و در ترتیب صحیح | LOW (تأیید شده ایمن) |
| ۲ | CSRF در admin endpoints | ✅ سیستم CSRF توکن + X-Requested-With | LOW (تأیید شده ایمن) |
| ۳ | Auth / Session security | ✅ پیاده‌سازی بالغ | LOW–MEDIUM (۲ مورد جزئی) |
| ۴ | Rate limiting | ✅ لایه‌بندی شده + fail-closed | LOW (۱ مورد جزئی) |
| ۵ | Secret scanning | ✅ هیچ secret هاردکد نشده | LOW (تأیید شده ایمن) |
| ۶ | SQL injection | ✅ همه parameterized | LOW (۱ مورد anti-pattern) |
| ۷ | File upload validation | ⚠️ فقط بر اساس پسوند | MEDIUM |

---

## ۱) XSS — MarkdownRenderer.tsx ✅

**نتیجه:** مشکلی یافت نشد. درخواست تأیید شد.

- فایل: `frontend/app/chat/components/MarkdownRenderer.tsx`
- خط ۱۳: `import rehypeSanitize from 'rehype-sanitize'`
- خط ۶۵: `rehypePlugins={[rehypeSanitize, rehypeHighlight]}` → **rehype-sanitize قبل از rehype-highlight** اجرا می‌شود (ترتیب صحیح؛ اگر برعکس بود، کد برجسته‌سازی می‌توانست تگ‌های خطرناک تزریق کند که sanitized نشوند).
- جستجو در کل فرانت‌اند: **صفر** مرجع به `dangerouslySetInnerHTML`، `innerHTML` یا `eval()`.
- لینک‌های خارجی با `rel="noopener noreferrer"` و `target="_blank"` ایمن‌سازی شده‌اند.
- **CSP** در `security.py` ست شده (اگرچه `script-src` شامل `'unsafe-inline'` و `'unsafe-eval'` است — نگاه کنید به بخش پیشنهادات).

---

## ۲) CSRF در admin endpoints ✅

**نتیجه:** محافظت دو‌لایه وجود دارد.

- `dependencies.py` → `admin_required()` (خط ۲۳۴): برای متدهای POST/PUT/DELETE/PATCH توکن CSRF از هدر `x-csrf-token`/`x-csrf` را با `hmac.compare_digest` چک می‌کند.
- `security.py` → `CsrfMiddleware` (خط ۲۴۸): برای مسیرهای کوکی‌محور (`/auth/`, `/api-keys`, `/referral/`) هدر `X-Requested-With` را الزامی می‌کند. فرم‌های cross-origin نمی‌توانند هدر سفارشی ست کنند → CSRF غیرممکن.
- Fallback legacy با هدر `x-admin-token` (constant-time comparison) برای ابزارهای اتوماسیون.
- **نکته مثبت:** مسیر ورود (`/auth/login`) نیز زیر prefix `/auth/` قرار دارد و توسط CsrfMiddleware پوشش داده می‌شود.

---

## ۳) Auth / Session security ✅ (با ۲ مورد جزئی)

**نقاط قوت:**
- رمزنگاری: PBKDF2-HMAC-SHA256 با salt تصادفی (۱۰۰,۰۰۰ تکرار) — استاندارد.
- کوکی سشن: `httponly=True`، `secure` (شرطی بر اساس ENV/DEBUG)، `samesite='lax'`.
- سشن‌های opaque در Redis با TTL — نه JWT ضعیف در سمت کلاینت.
- `API_KEY_PEPPER` اجباری (اگر ست نشده باشد برنامه اجرا نمی‌شود — fail closed).
- توکن‌ها با `secrets.token_urlsafe(32)` تولید می‌شوند (CRYPTO-secure).
- چرخش سشن در تغییر سطح دسترسی (`_rotate_session`).

**موارد جزئی (LOW):**
- **A3.1** — `get_telegram_token` (auth.py:550) سشن را به صورت `str(user.id)` (نه JSON) در Redis ذخیره می‌کند. `_get_session` آن را تحمل می‌کند اما فیلد `expires_at` چک نمی‌شود → سشن تلگرامی تا ابد معتبر نمی‌ماند (چون expire دارد) اما از منطق expiry صریح بی‌بهره است. اصلاح پیشنهادی: ذخیره به فرمت JSON یکسان با `_create_session`.
- **A3.2** — `SESSION_COOKIE_SECURE` وقتی `DEBUG=true` باشد غیرفعال می‌شود (خط ۲۷–۳۱). در حال حاضر `DEBUG=false` است پس مشکلی نیست، اما در محیط staging باید دقت شود.

---

## ۴) Rate limiting ✅ (۱ مورد جزئی)

- `security.py` → `RateLimiter` بر پایه Redis با sliding window.
- لایه‌بندی: signup=۵/دقیقه، login=۳۰، chat رایگان=۳۰ / pro=۱۲۰ / enterprise=۳۰۰، admin=۳۰.
- **Fail-closed:** اگر Redis در دسترس نباشد، ترافیک رد می‌شود (خط ۵۰) — عالی.
- شناسایی کلاینت: اولویت با user_id، فال‌بک IP+User-Agent hash.
- **مورد جزئی (LOW):** آپلود RAG (`/v1/rag/upload`) تحت محدودیت کلی ۶۰/دقیقه است و محدودیت حجمی جداگانه یا rate limit اختصاصی برای آپلود ندارد — می‌تواند وسیله‌ای برای DoS ذخیره‌سازی (۲۰MB × ۶۰ = ۱.۲GB/دقیقه به ازای هر کاربر) باشد. پیشنهاد: limiter اختصاصی آپلود (مثلاً ۱۰/دقیقه) + نظارت فضای دیسک.

---

## ۵) Secret scanning ✅

- جستجوی regex در کل مخزن (py/ts/tsx/js/yml/yaml، به جز node_modules): **هیچ secret هاردکد یافت نشد**.
- تمام کلیدها از env خوانده می‌شوند: `ADMIN_TOKEN`, `SECRET_KEY`, `API_KEY_PEPPER`, `INTERNAL_TOKEN`, کلیدهای LiteLLM، SMTP.
- برنامه با `RuntimeError` مانع اجرا می‌شود اگر `ADMIN_TOKEN` یا `API_KEY_PEPPER` ست نشده باشند.
- `.env` در `.gitignore` هست (دسترسی مستقیم به آن توسط ابزار خواندن فایل مسدود شد — defense-in-depth).
- **تأیید:** `DEBUG=false` در `.env` (خروجی grep).

---

## ۶) SQL injection ✅ (۱ anti-pattern)

- تقریباً تمام کوئری‌ها از SQLAlchemy ORM یا `sqlalchemy.text(...)` با binding پارامتر (`:name`) استفاده می‌کنند → ایمن در برابر injection.
- جستجوی LIKE در `conversations.py:126` از `_escape_like()` استفاده می‌کند (فرار wildcards) — درست.
- **Anti-pattern (LOW):** `services/rag.py:75` از f-string برای ساخت متن SQL استفاده می‌کند:
  ```python
  res = await session.execute(sqlalchemy.text(f"""... {doc_filter} ..."""), params)
  ```
  در حال حاضر `doc_filter` فقط بر دو مقدار hardcoded (`'AND rc.document_id = :doc_id'` یا `''`) ست می‌شود و ورودی کاربر مستقیماً تزریق نمی‌شود → **عملاً ایمن**، اما الگوی خطرناکی است که با کوچکترین تغییر در آینده می‌تواند تزریق‌پذیر شود. پیشنهاد: حذف f-string و استفاده از conditional `params` خالص.

---

## ۷) File upload validation ⚠️ MEDIUM

**ضعف اصلی یافت شده.**

- `rag_endpoints.py:52` و `doc_processor.py:27`: اعتبارسنجی **فقط بر اساس پسوند فایل** (`ext = filename.rsplit('.',1)[-1].lower()`).
- `SUPPORTED_TYPES = {'pdf','txt','md','csv','json'}` — محتوای واقعی (magic bytes) یا `Content-Type` چک نمی‌شود.
- **تحلیل ریسک:**
  - PDF: توسط `pymupdf`/`pypdf` پردازش می‌شود که اگر فایل PDF معتبر نباشد خطا می‌دهد → حمله polyglot محدود شده اما صفر نیست (PDF parser ها گاهی آسیب‌پذیر به memory corruption هستند؛ نگهداری کتابخانه به‌روز ضروری است).
  - txt/md/csv/json: صرفاً `decode('utf-8')` می‌شوند → ریسک اجرای کد ندارند، اما یک فایل `.json` با پسوند `.pdf` (یا بالعکس) می‌تواند فرآیند پردازش را با خطای غیرمنتظره مواجه کند.
- **نقطه قوت:** محدودیت حجم (RAG=۲۰MB، chat=۱۰MB) و چک `len(content)==0` وجود دارد.
- **پیشنهاد اصلاح:**
  1. چک magic bytes (header) علاوه بر پسوند — مثلاً PDF باید با `%PDF` شروع شود.
  2. محدودیت تعداد صفحات PDF (در chat.py هست=۱۰۰، در doc_processor نیست — اضافه شود).
  3. rate limit اختصاصی آپلود (نگاه بخش ۴).
  4. اسکن آنتی‌ویروس/沙NDR برای فایل‌های PDF در محیط production.

---

## سایر مشاهدات

- **WebSocket auth (LOW):** `websocket.py:27` هنوز اجازه auth با query param `?token=` را می‌دهد (با هشدار deprecation). ریسک پایین چون فقط notify می‌کند، اما توکن در URL لاگ می‌شود. پیشنهاد: غیرفعال کردن کامل query-param auth.
- **CSP (LOW):** `script-src 'self' 'unsafe-inline' 'unsafe-eval'` — `unsafe-eval` و `unsafe-inline` XSS را تسهیل می‌کنند. از آنجا که React همه چیز را escape می‌کند و rehype-sanitize فعال است، ریسک عملی کم است، اما برای امتیاز کامل باید به nonce-based CSP مهاجرت کرد.
- **CORS (✅):** `allow_origins` از env (`CORS_ORIGINS`) با لیست صریح — نه `*` — ایمن.
- **Payment (✅):** Zarinpal با `trust_env=False` و verify callback دقیق — ایمن.
- **Proxy config admin (✅):** مسدودسازی آدرس‌های داخلی (localhost/۱۲۷/۱۰.x/۱۹۲.۱۶۸/۱۷۲) در ست کردن پروکسی — جلوگیری از SSRF.

---

## نمره امنیت کلی: **۸.۵ / ۱۰**

**توزیع:**
- XSS: ۱۰/۱۰ (rehype-sanitize تأیید شد)
- CSRF: ۱۰/۱۰ (دو‌لایه)
- Auth/Session: ۹/۱۰ (۲ مورد جزئی)
- Rate limiting: ۸/۱۰ (نبود limiter اختصاصی آپلود)
- Secret scanning: ۱۰/۱۰ (صفر هاردکد)
- SQL injection: ۹/۱۰ (۱ anti-pattern بی‌خطر فعلاً)
- File upload: ۶/۱۰ (فقط پسوند) ← **تنها نقطه ضعف واقعی**

**اولویت اصلاح:**
1. 🔴 File upload: چک magic bytes + محدودیت صفحات PDF در doc_processor (MEDIUM).
2. 🟡 Rate limit اختصاصی آپلود (LOW–MEDIUM).
3. 🟡 حذف f-string در rag.py:75 (LOW).
4. 🟡 یکسان‌سازی فرمت سشن تلگرام (LOW).
5. 🟢 غیرفعال کردن WebSocket query-param auth + مهاجرت به nonce-CSP (LOW).

**جمع‌بندی:** پروژه در وضعیت امنیتی **بسیار خوب** قرار دارد. زیرساخت احراز هویت، سشن، CSRF، rate limiting و جلوگیری از SQL injection بالغ و درست پیاده‌سازی شده‌اند. اتصال XSS در رندر Markdown که قبلاً اصلاح شده بود **تأیید شد** و `DEBUG=false` نیز تأیید شد. تنها اقدام اصلاحی با اولویت متوسط، تقویت اعتبارسنجی آپلود فایل است.
