# Multiai — برنامه عملیاتی تثبیت نسخه پایدار

**تاریخ:** 2026-07-12
**Scope:** فقط `/root/multiai`
**هدف:** تبدیل وضعیت فعلی به یک release پایدار و قابل ارائه، بدون feature جدید و بدون redesign.

## تصمیم اجرایی

برنامه‌های قبلی بیش‌ازحد بزرگ بودند و بخش زیادی از آن‌ها feature/design جدید پیشنهاد می‌دادند. این برنامه فقط روی correctness، reliability، security baseline، reproducible build و release verification تمرکز دارد.

### خارج از Scope این release

- feature جدید
- Team/tenant/SSO
- redesign و polish گسترده UI
- marketing/onboarding جدید
- modularization بزرگ Backend
- performance optimization غیرضروری
- اضافه‌کردن provider یا model جدید بدون live verification

## واقعیت فعلی

### Repository

- remote: `mostafamasoomi/multiai`
- working tree بسیار dirty است: تغییرات هم‌زمان در Backend، Frontend، Admin، Compose، migrations، tests و docs.
- چند backup و artifact تستی داخل workspace وجود دارد.
- قبل از release باید baseline تغییرات ثبت و فایل‌های generated/backup از مسیر release جدا شوند.

### Runtime

- Frontend: running روی `0.0.0.0:3003`
- Backend: running روی `127.0.0.1:8001` و health فعلی `200` با DB/Redis سالم
- Admin: running روی `0.0.0.0:8081`
- PostgreSQL و Redis: running
- LiteLLM: running
- Compose config: معتبر
- Frontend production build: موفق، Next.js route generation برای 39 route
- Catalog فعلی: 7 مدل approved و API آن `200` است

### Test truth

اجرای `pytest -q` در وضعیت فعلی release قابل قبول نیست:

- `39 passed`
- `4 skipped`
- `28 failed`
- `58 errors`
- `56 warnings`

دو ریشه اصلی خطاها:

1. TestClient سفارشی با نسخه فعلی Starlette/HTTPX ناسازگار است و argument `client` را به `_TestClientTransport` می‌دهد.
2. fixtureهای migration، `MagicMock`/`AsyncMock` ناسازگار با `migrate()` می‌سازند؛ در `backend/migrate.py` نتیجه `.all()` روی coroutine تستی می‌شکند.

این تست‌ها قبل از هر claim درباره release باید اصلاح شوند.

### Build truth

- `frontend/npm run build`: موفق
- Build باید با `npm ci` در محیط تمیز هم تکرار شود؛ وجود artifactهای `node_modules`, `.next`, `tsconfig.tsbuildinfo` نباید شرط موفقیت باشد.

### Runtime chat truth

- health به‌تنهایی کافی نیست.
- پذیرش Chat باید با کاربر واقعی browser-facing انجام شود: login → catalog → non-streaming → SSE برای هر مدل approved.
- مدل‌ها و provider باید live probe شوند و مدل timeout‌دار selectable نماند.
- quota/wallet بخشی از پذیرش است؛ تست با کاربر بدون balance معتبر نیست.

## ترتیب کار با کمترین ریسک و مصرف توکن

### Gate 0 — Freeze و baseline

1. هیچ feature جدیدی اضافه نشود.
2. وضعیت فعلی، container image، compose config و endpointها ثبت شود.
3. فایل‌های backup/generated/test artifact از مسیر build و git status تفکیک شوند؛ حذف فقط پس از بررسی ownership.
4. یک release checklist واحد ساخته شود.

**خروجی:** baseline قابل rollback و فهرست دقیق تغییرات.

### Gate 1 — Test harness را قابل اعتماد کن

فایل‌های اصلی:

- `backend/tests/conftest.py`
- `backend/migrate.py`
- `backend/pytest.ini`
- `backend/requirements.txt`

کارها:

1. TestClient را با نسخه‌های نصب‌شده سازگار کن؛ یا از TestClient رسمی با dependency pin صحیح استفاده کن، یا transport سفارشی را با signature واقعی نسخه نصب‌شده تطبیق بده.
2. migration mock را طوری اصلاح کن که `await execute()` یک Result واقعی برگرداند و `all()` synchronous باشد.
3. warningهای dependency و deprecation را دسته‌بندی کن.
4. ابتدا تست‌های auth/catalog/ownership/wallet/admin را جدا اجرا کن، بعد full suite.

**Acceptance:** `pytest -q` بدون error؛ failure باقی‌مانده فقط failure واقعی product باشد و برای هرکدام issue مشخص وجود داشته باشد.

### Gate 2 — Database و migration correctness

فایل‌های اصلی:

- `backend/migrate.py`
- `backend/migrations/*.sql`
- `backend/tests/test_migrations_real.py`
- `backend/app.py`

کارها:

1. migration روی PostgreSQL disposable از صفر اجرا شود.
2. migration دوباره اجرا شود و idempotent باشد.
3. روی DB فعلی فقط migrationهای pending اجرا شوند؛ schema دستی با migration جایگزین نشود.
4. مدل‌های ORM/queryهای واقعی با schema بررسی شوند، مخصوصاً ledger، pricing، usage و catalog.
5. خطاهای settlement، reservation، usage و payment callback به‌صورت structured ثبت شوند؛ `pass` خاموش در مسیر مالی باقی نماند.

**Acceptance:** fresh DB و existing DB هر دو بدون drift؛ تست ownership و ledger invariant سبز.

### Gate 3 — Chat و مدل Catalog

فایل‌های اصلی:

- `backend/litellm_config.yaml`
- `backend/app.py`
- `frontend/app/api/chat/route.ts`
- `frontend/app/chat/page.tsx`
- `frontend/lib/useCatalog.ts`
- `frontend/types/catalog.ts`

کارها:

1. `/v1/models` provider را query کن.
2. هر مدل را با minimal completion و timeout محدود probe کن.
3. فقط مدل‌های healthy در Catalog با `availability=available` بمانند؛ timeout/errorها `degraded` یا حذف selectable شوند.
4. `id` داخلی و `providerModelId` همیشه جدا بمانند؛ درخواست Chat فقط upstream ID را بفرستد.
5. Catalog duplicate بر اساس `providerModelId` حذف شود.
6. Chat برای non-stream و SSE تست شود.
7. خطاهای 401، 402، 404، 429، 502 به خطای ساختاری و قابل فهم UI تبدیل شوند؛ raw upstream exception نمایش داده نشود.
8. quota/wallet policy برای preview مستند و یکنواخت باشد؛ balance تستی خارج از production policy باقی نماند.

**Acceptance:** برای تک‌تک مدل‌های visible، browser-facing login + catalog + non-stream + SSE با پاسخ واقعی و `[DONE]` موفق باشد.

### Gate 4 — Auth و Ownership baseline

فایل‌های اصلی:

- `backend/app.py`
- `frontend/lib/auth.tsx`
- `frontend/app/api/auth/*`
- `backend/tests/test_auth.py`
- `backend/tests/test_ownership.py`

کارها:

1. یک auth contract canonical انتخاب و مستند شود.
2. localStorage token که برای auth استفاده می‌شود حذف یا به migration موقت محدود شود؛ secret/admin token هرگز browser-visible نباشد.
3. session cookie: HttpOnly، SameSite مناسب و Secure در production.
4. logout، expiry و revoke تست شود.
5. دو کاربر نتوانند conversation/wallet/ledger/usage/API key یکدیگر را ببینند یا تغییر دهند.

**Acceptance:** auth/ownership/security tests سبز و هیچ secret در bundle/log نباشد.

### Gate 5 — Admin و Financial safety

فایل‌های اصلی:

- `admin/app.py`
- `admin/Dockerfile`
- `backend/payment.py`
- pricing/wallet routes

کارها:

1. Admin login، pricing، models، users با schema واقعی تست شوند.
2. Admin origin/session از user session جدا باشد.
3. payment callback: authority، amount، state، replay و duplicate callback تست شود.
4. ledger append-only و idempotency بررسی شود.
5. خطاهای DB در Admin به 500 خام یا traceback تبدیل نشوند.

**Acceptance:** admin smoke، pricing read/write و payment negative cases سبز.

### Gate 6 — Release reproducibility

کارها:

1. `npm ci && npm run build` در frontend clean اجرا شود.
2. Backend dependencyها pin یا حداقل با lock/constraints قابل تکرار شوند.
3. Compose fresh recreate از `.env.example` + secret injection مستند اجرا شود.
4. `MOCK_MODE=false` در effective container environment verify شود.
5. logs startup و health readiness بررسی شوند.
6. یک smoke script واحد اضافه/تکمیل شود.

**Acceptance:** fresh recreate، health، auth، catalog، chat، admin و rollback همگی موفق.

## Release Smoke Checklist

```bash
set -e
cd /root/multiai/backend
pytest -q
cd /root/multiai/frontend
npm ci
npm run build
cd /root/multiai
./scripts/smoke.sh
```

Smoke باید این‌ها را بررسی کند:

- frontend route: `200`
- backend `/health`: DB و Redis `ok`
- admin login: `200`
- catalog: schema، uniqueness، no secrets
- login/signup unauthorized behavior
- هر model approved: non-stream `200`
- هر model approved: SSE `200` و `[DONE]`
- insufficient balance: structured `402/429`
- no mock mode
- no crash-loop

## Definition of Done

نسخه فقط زمانی stable اعلام شود که:

- full backend suite بدون error و failure غیرموجه سبز باشد.
- clean frontend build با `npm ci` سبز باشد.
- fresh Compose recreate سبز باشد.
- مدل‌های visible همگی live و browser-facing تست شده باشند.
- wallet/quota/auth/ownership رفتار مستند و تست‌شده داشته باشند.
- Admin روی schema واقعی بدون traceback کار کند.
- هیچ secret یا raw provider error در UI، bundle یا log نباشد.
- rollback path و baseline release ثبت شده باشد.

## چیزهایی که عمداً انجام نمی‌دهیم

- مدل یا provider جدید بدون probe
- طراحی مجدد UI
- feature جدید
- Team/SSO/tenant
- claim تبلیغاتی جدید
- migration بزرگ معماری
- تغییر `/root/multiapi`

## ریسک‌های فعلی

| ریسک | شدت | اقدام |
|---|---:|---|
| Test suite فعلاً 28 failure و 58 error دارد | Critical | Gate 1 |
| migration mock با async runtime ناسازگار است | Critical | Gate 1 |
| working tree بسیار dirty و rollback سخت است | High | Gate 0 |
| catalog ممکن است duplicate/stale شود | High | Gate 3 |
| quota در browser chat می‌تواند 429 بدهد | High | Gate 3 |
| payment/ledger schema drift محتمل است | Critical | Gate 2/5 |
| localStorage auth هنوز در برخی مسیرها وجود دارد | High | Gate 4 |
| tunnel upstream ناپایدار است | Medium | live probe + degraded state |
