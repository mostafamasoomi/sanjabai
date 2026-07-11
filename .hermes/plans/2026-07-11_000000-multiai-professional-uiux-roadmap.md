# Multiai — برنامه جامع رسیدن به نسخه Production-Grade

> **For Hermes:** این سند فقط برنامه‌ریزی است؛ اجرا باید پس از تأیید مالک پروژه انجام شود. هر مرحله با TDD، بازبینی مستقل و gate واقعی تکمیل شود.

**Goal:** تبدیل Multiai از یک Gateway/داشبورد خوبِ Phase 0 به سریع‌ترین، واضح‌ترین و قابل‌اعتمادترین پلتفرم فارسی برای Chat + Model Discovery + Developer API.

**Architecture:** حفظ FastAPI + PostgreSQL + Redis + LiteLLM + Next.js، اما با قراردادهای روشن، API client واحد، session امن، طراحی محصول مبتنی بر task و حذف ادعاها/داده‌های mock از مسیرهای واقعی. Frontend عمومی رسمی روی `0.0.0.0:3003` است؛ `/root/multiapi` خارج از scope این برنامه است.

**Tech Stack:** Next.js 14 App Router، React 18، TypeScript، Tailwind فعلی، FastAPI، SQLAlchemy async، PostgreSQL 16، Redis 7، LiteLLM، Playwright، pytest/httpx.

---

## 0. وضعیت فعلی و مرزبندی قطعی

### Repository رسمی

```text
/root/multiai
```

### سرویس‌ها و پورت‌ها

| سرویس | وضعیت فعلی | پورت |
|---|---|---:|
| Frontend رسمی Multiai | Docker Compose `multiai_frontend` | `0.0.0.0:3003 -> 3000` |
| Backend رسمی | `multiai_api` | `127.0.0.1:8001 -> 8000` |
| Admin جدا | `multiai_admin` | `127.0.0.1:8081 -> 80` |
| PostgreSQL | داخلی Compose | `5432` |
| Redis | داخلی Compose | `6379` |

**قانون:** هیچ تغییری در `/root/multiapi`، پورت 3005 یا سرویس‌های آن انجام نشود.

### نقاط قوت فعلی

- RTL و فارسی‌سازی پایه
- صفحات login/signup/profile/dashboard/wallet/models/compare/playground
- AppShell و mobile bottom navigation
- متادیتای SEO و JSON-LD
- API Gateway با streaming و مدل‌های متعدد
- ثبت مصرف، quota، wallet، referral، password reset و payment پایه
- rate limiter و security headers
- Compose رسمی که Frontend را روی 3003 منتشر می‌کند

### ریسک‌ها و ضعف‌های تأییدشده

1. **Backend monolith بزرگ:** `backend/app.py` حدود ۱۶۰۰+ خط و همزمان مسئول ORM، auth، route، billing، proxy و startup است.
2. **Schema drift:** startup از `Base.metadata.create_all` استفاده می‌کند؛ migration/versioning واقعی وجود ندارد.
3. **LiteLLM dependency شکننده:** `LITELLM_HOST` به hostname ثابت کانتینر خارجی اشاره می‌کند، درحالی‌که سرویس LiteLLM داخل `docker-compose.multiai.yml` تعریف نشده است.
4. **Admin secret fallback:** fallback عمومی حذف نشده بود؛ Compose باید بدون `ADMIN_TOKEN` اصلاً config نشود.
5. **Auth client contract:** `frontend/lib/api.ts` بسیار حداقلی است، usage با `userId` query کار می‌کند و API client واحد برای token/error/request-id وجود ندارد.
6. **Frontend rewrite کلی:** `/api/:path*` به backend rewrite می‌شود؛ routeهای حساس و response/error mapping صریح نیستند.
7. **ادعاهای غیرقابل‌اثبات در UI:** آمارهایی مثل `۵۰+ مدل`، `۹۹.۹٪ uptime`، `۱۰۰٪ پشتیبانی` و `۱۰,۰۰۰ تومان هدیه` باید از داده/قانون واقعی بیایند یا با copy محافظه‌کارانه جایگزین شوند.
8. **UI هنوز generic است:** emoji به‌جای icon system، hierarchy ضعیف، navigation طولانی، نبود command palette، نبود stateهای کامل، و نبود flow مشخص برای اولین پاسخ موفق.
9. **Performance:** فونت از Google Fonts و JSON-LD در layout client boundary، تصاویر unoptimized، نبود performance budget و route-level loading/error contract.
10. **تست‌ها:** تست‌های فعلی عمدتاً smoke/source-level هستند؛ E2E واقعی و auth/ownership/payment concurrency کافی نیست.
11. **Security:** admin در localStorage، rate-limit وابسته به Redis بدون تست رفتاری کافی، و endpointهای admin باید با dependency واحد و session امن بازطراحی شوند.
12. **Payment safety:** callback باید order را با row lock claim کند و credit wallet + ledger + order completion را در یک transaction اتمیک انجام دهد.

---

## 1. معیارهای نسخه ایده‌آل

### Product metrics

- Time to first successful answer: هدف p50 کمتر از ۱۰ ثانیه در شبکه عادی
- ثبت‌نام تا اولین پاسخ موفق: کمتر از ۹۰ ثانیه
- نرخ تکمیل اولین prompt: بالاتر از ۸۵٪ در تست usability
- خطای قابل مشاهده کاربر: صفر صفحه سفید؛ همه خطاها action قابل‌فهم داشته باشند
- model discovery: کاربر در کمتر از ۱۵ ثانیه مدل مناسب را پیدا کند
- mobile task completion: چت، شارژ، مشاهده مصرف و تغییر مدل بدون zoom/scroll افقی

### Performance budgets

- LCP صفحه عمومی: کمتر از ۲.۵s در موبایل متوسط
- INP: کمتر از ۲۰۰ms
- CLS: کمتر از ۰.۱
- JS اولیه landing: کمتر از ۱۸۰KB gzip هدف‌گذاری شود
- چت: ورود shell بدون بارگذاری bundleهای dashboard/admin
- هر route با `loading.tsx`, `error.tsx`, empty state و retry مشخص

### Reliability gates

- build clean
- import smoke واقعی در cwd کانتینر
- fresh DB migration
- existing DB migration
- direct backend smoke
- frontend public smoke روی 3003
- E2E login → first chat → usage → logout
- تست دو کاربره ownership
- تست callback پرداخت همزمان
- reviewer مستقل بدون context implementation

---

## 2. فاز A — Freeze قرارداد محصول و اطلاعات واقعی

### Task A1: ایجاد product contract

**Files:**
- Create: `docs/product-contract.md`
- Modify: `docs/phase-0-complete.md`

**محتوا:**
- segmentها: کاربر عمومی، developer، تیم/سازمان
- CTA اصلی: «شروع رایگان» و «ساخت API Key»
- glossary فارسی: مدل، توکن، موجودی، اعتبار، هزینه، استریم، کلید API
- ادعاهای مجاز و غیرمجاز
- تعریف هدیه signup و شرایط آن
- تعریف رسمی uptime و مدل count

**Acceptance:** هیچ copy بازاریابی عدد یا promise بدون منبع/feature flag باقی نماند.

### Task A2: data contract مدل‌ها

**Files:**
- Modify: `backend/app.py`
- Create: `backend/model_catalog.py`
- Create: `backend/tests/test_model_catalog.py`

مدل عمومی باید شامل این فیلدها باشد:

```json
{
  "id": "deepseek-v3",
  "display_name": "DeepSeek V3",
  "provider": "DeepSeek",
  "capabilities": ["chat", "coding", "reasoning"],
  "context_window": 64000,
  "pricing": {"input": 0, "output": 0, "currency": "IRR"},
  "availability": "available",
  "recommended_for": ["کدنویسی", "تحلیل"]
}
```

### Task A3: حذف mock data از مسیر production

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/models/page.tsx`
- Modify: `frontend/app/dashboard/page.tsx`
- Modify: `frontend/app/pricing/page.tsx`
- Create: `frontend/lib/feature-flags.ts`

هر داده ثابت باید یکی از این سه حالت باشد:

1. داده واقعی API
2. داده illustrative با label واضح
3. حذف شود

---

## 3. فاز B — معماری Backend برای رشد حرفه‌ای

### Task B1: ساخت migration baseline

**Files:**
- Create: `backend/migrations/0001_baseline.sql`
- Create: `backend/migrations/0002_auth_sessions.sql`
- Create: `backend/migrations/0003_billing_safety.sql`
- Create: `backend/migrate.py`
- Test: `backend/tests/test_migrations.py`

جدول‌های اجباری:

- `schema_migrations`
- `users`
- `sessions`
- `api_keys`
- `wallets`
- `ledger`
- `payment_orders`
- `quotas`
- `model_aliases`
- `pricing`
- `audit_logs`

`create_all` از startup production حذف شود؛ migration runner تنها source of truth باشد.

### Task B2: شکستن `backend/app.py`

**Files:**

```text
backend/app/
├── main.py
├── config.py
├── db.py
├── models/
├── schemas/
├── services/
├── routers/
│   ├── health.py
│   ├── auth.py
│   ├── chat.py
│   ├── models.py
│   ├── wallet.py
│   ├── usage.py
│   ├── payments.py
│   ├── admin.py
│   └── referral.py
└── middleware/
    ├── auth.py
    ├── rate_limit.py
    └── request_id.py
```

هر route باید thin باشد؛ business logic در service باشد.

### Task B3: request ID و error contract

**Files:**
- Create: `backend/request_id.py`
- Create: `backend/errors.py`
- Modify: `backend/app.py`
- Modify: `frontend/lib/api.ts`
- Test: `backend/tests/test_error_contract.py`

فرمت خطا:

```json
{
  "error": {
    "code": "insufficient_balance",
    "message": "موجودی برای این درخواست کافی نیست.",
    "request_id": "req_...",
    "retryable": false
  }
}
```

### Task B4: LiteLLM را explicit و service-based کن

**Files:**
- Modify: `docker-compose.multiai.yml`
- Create/modify: `backend/Dockerfile.litellm`
- Modify: `backend/app.py`
- Create: `backend/tests/test_upstream_contract.py`

گزینه ترجیحی:

```yaml
multiai_litellm:
  image: ghcr.io/berriai/litellm:main-latest
  command: ["--config", "/app/config.yaml", "--port", "4000"]
  expose: ["4000"]
  networks: [multiai_net]
```

سپس:

```env
LITELLM_HOST=http://multiai_litellm:4000
```

Hostname کانتینر خارجی حذف شود.

### Task B5: Auth/session امن

**Files:**
- Modify: `backend/app.py`
- Create: `backend/auth_service.py`
- Modify: `frontend/lib/auth.tsx`
- Modify: `frontend/lib/api.ts`
- Test: `backend/tests/test_auth_security.py`

الزامات:

- session token فقط HttpOnly/Secure/SameSite cookie
- عدم برگشت token خام در response production
- refresh/rotation
- revoke/logout-all
- bcrypt/argon2 password hash
- generic forgot-password response
- rate-limit رفتاری برای login/reset
- status user در همه protected routes

### Task B6: payment transaction atomicity

**Files:**
- Modify: `backend/payment.py`
- Modify: `backend/app.py`
- Modify: `backend/schema.sql`
- Test: `backend/tests/test_payment_concurrency.py`

قانون callback:

1. order با `SELECT ... FOR UPDATE`
2. اگر completed بود، بدون credit اضافه return
3. verify با amount ذخیره‌شده
4. order، wallet و ledger در یک transaction
5. unique index روی authority/ref_id/payment_order_id
6. rollback کامل در هر failure

---

## 4. فاز C — طراحی UI/UX نسل بعد

### Design direction

**نام داخلی:** Multiai Aurora / Persian AI Workspace

اصول:

- آرام، premium، سریع؛ نه شلوغ و neon-heavy
- dark-first با contrast واقعی
- typography فارسی خوانا، اعداد tabular
- icon system واقعی؛ حذف emoji از navigation و CTA
- task-first: کاربر بداند قدم بعدی چیست
- progressive disclosure: اطلاعات پیچیده فقط هنگام نیاز
- حفظ RTL بدون شکستن code/content LTR
- micro-interaction کوتاه و هدفمند، با reduced-motion

### Task C1: Design tokens

**Files:**
- Create: `frontend/design/tokens.ts`
- Create: `frontend/components/ui/Icon.tsx`
- Create: `frontend/components/ui/Button.tsx`
- Create: `frontend/components/ui/Badge.tsx`
- Create: `frontend/components/ui/Surface.tsx`
- Create: `frontend/components/ui/Tooltip.tsx`
- Modify: `frontend/app/globals.css`

Tokens:

```text
space-1..8
radius-sm..xl
surface-0..3
text-primary/secondary/muted
accent/positive/warning/danger
focus-ring
motion-fast/normal/slow
```

Acceptance:

- تمام interactiveها keyboard focus دارند.
- contrast متن اصلی حداقل WCAG AA.
- هیچ icon-only button بدون aria-label نیست.

### Task C2: Landing page conversion-first

**Files:**
- Modify: `frontend/app/page.tsx`
- Create: `frontend/components/landing/Hero.tsx`
- Create: `frontend/components/landing/LiveModelDemo.tsx`
- Create: `frontend/components/landing/CostTransparency.tsx`
- Create: `frontend/components/landing/TrustSection.tsx`
- Create: `frontend/components/landing/FAQ.tsx`

ساختار:

1. Hero با promise دقیق، نه ادعای غیرقابل‌اثبات
2. demo تعاملی مدل/هزینه با داده API
3. use caseهای فارسی: کدنویسی، تحلیل، ترجمه، تولید محتوا
4. مقایسه هزینه و workflow با چند provider
5. امنیت و کنترل هزینه
6. CTA تکرارشونده
7. FAQ واقعی

### Task C3: First-run onboarding

**Files:**
- Create: `frontend/app/onboarding/page.tsx`
- Create: `frontend/components/onboarding/GoalPicker.tsx`
- Create: `frontend/components/onboarding/ModelRecommendation.tsx`
- Create: `frontend/components/onboarding/FirstPrompt.tsx`
- Modify: `frontend/lib/auth.tsx`

Flow:

```text
ثبت‌نام → انتخاب هدف → پیشنهاد مدل → prompt آماده → اولین پاسخ → دعوت به شارژ/API
```

Acceptance: کاربر جدید بدون خواندن docs به اولین پاسخ موفق برسد.

### Task C4: Chat workspace حرفه‌ای

**Files:**
- Modify: `frontend/app/chat/page.tsx`
- Modify: `frontend/components/Chat.tsx`
- Create: `frontend/components/chat/ConversationList.tsx`
- Create: `frontend/components/chat/Composer.tsx`
- Create: `frontend/components/chat/ModelPicker.tsx`
- Create: `frontend/components/chat/CostPreview.tsx`
- Create: `frontend/components/chat/StreamStatus.tsx`
- Create: `frontend/lib/sse.ts`

الزامات UX:

- optimistic user message
- assistant placeholder
- cancel با AbortController
- retry/regenerate
- واضح بودن مدل و هزینه قبل از ارسال
- usage/cost بعد از پاسخ
- کپی، export، share با privacy warning
- conversation history و search
- draft persistence
- offline/reconnect state
- keyboard shortcuts
- code block copy و LTR isolation

### Task C5: Model browser قابل‌فهم

**Files:**
- Modify: `frontend/app/models/page.tsx`
- Create: `frontend/components/models/ModelCard.tsx`
- Create: `frontend/components/models/ModelFilters.tsx`
- Create: `frontend/components/models/ModelCompare.tsx`

هر card:

- بهترین کاربرد
- سرعت تقریبی با label غیرقطعی
- context
- capability chips
- input/output price
- availability
- CTA «استفاده در چت»

### Task C6: Dashboard و wallet قابل اعتماد

**Files:**
- Modify: `frontend/app/dashboard/page.tsx`
- Modify: `frontend/app/wallet/page.tsx`
- Create: `frontend/components/usage/UsageSummary.tsx`
- Create: `frontend/components/usage/UsageChart.tsx`
- Create: `frontend/components/wallet/LedgerTable.tsx`
- Create: `frontend/components/wallet/TopupFlow.tsx`

الزامات:

- موجودی فعلی برجسته
- هزینه امروز و ماه
- projected remaining usage
- ledger قابل فیلتر
- status پرداخت
- top-up با confirmation
- empty/loading/error states

### Task C7: Navigation و responsive architecture

**Files:**
- Modify: `frontend/components/AppShell.tsx`
- Create: `frontend/components/CommandPalette.tsx`
- Create: `frontend/components/KeyboardShortcuts.tsx`
- Modify: `frontend/app/globals.css`

- desktop sidebar کم‌عرض و collapsible
- mobile bottom nav فقط ۴ action اصلی
- باقی مسیرها در More/Command Palette
- active state واضح
- حفظ scroll position
- focus trap برای drawer/modal
- safe-area inset برای iOS

### Task C8: Accessibility و state completeness

**Files:**
- Create: `frontend/tests/a11y.spec.ts`
- Create: `frontend/tests/navigation.spec.ts`
- Add per-route: `loading.tsx`, `error.tsx`, `not-found.tsx`

برای هر route:

```text
loading
empty
error
unauthorized
offline
success
```

---

## 5. فاز D — Performance و observability

### Task D1: حذف هزینه‌های frontend

- فونت self-host یا subset شود؛ وابستگی runtime به Google Fonts حذف شود.
- dynamic import برای chart، admin و playground.
- تصاویر واقعی با `next/image` یا حذف تصاویر غیرضروری.
- route-specific providers؛ AppShell نباید همه featureها را وارد bundle کند.
- اجرای `next build` با bundle report.

### Task D2: metrics backend

**Files:**
- Create: `backend/observability.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_observability.py`

ثبت:

- request_id
- latency
- status
- model
- stream first-token latency
- upstream error
- wallet/payment event بدون secret و محتوای حساس

### Task D3: health/readiness تفکیک‌شده

```text
GET /health/live
GET /health/ready
GET /health/deep   # admin-only
```

`ready` باید DB، Redis و LiteLLM را check کند؛ `/health` نباید وضعیت جعلی `ok` بدهد وقتی dependency اصلی down است.

---

## 6. فاز E — Admin Console حرفه‌ای

**Files:**

```text
frontend/app/admin/
├── layout.tsx
├── page.tsx
├── users/page.tsx
├── pricing/page.tsx
├── payments/page.tsx
├── models/page.tsx
├── audit/page.tsx
└── settings/page.tsx
```

الزامات:

- admin token در localStorage حذف شود.
- session کوتاه‌عمر یا HttpOnly admin cookie.
- login با endpoint واقعی validate شود.
- تمام عملیات مالی confirmation و audit event داشته باشد.
- pagination و server-side filtering.
- destructive action دو مرحله‌ای.
- export با permission و rate-limit.
- audit log غیرقابل‌تغییر برای تغییر قیمت، wallet، kill switch و user status.

---

## 7. فاز F — تست و Release Candidate

### Backend tests

```text
backend/tests/test_auth_security.py
backend/tests/test_ownership.py
backend/tests/test_wallet_atomicity.py
backend/tests/test_payment_concurrency.py
backend/tests/test_migrations.py
backend/tests/test_error_contract.py
backend/tests/test_chat_stream.py
backend/tests/test_upstream_contract.py
```

### Frontend tests

```text
frontend/tests/auth.spec.ts
frontend/tests/first-run.spec.ts
frontend/tests/chat.spec.ts
frontend/tests/mobile.spec.ts
frontend/tests/a11y.spec.ts
frontend/tests/performance.spec.ts
```

### Commands

```bash
cd /root/multiai/backend
PYTHONPATH=. pytest -q
python3 -m compileall -q .

cd /root/multiai/frontend
npm ci
npm run build

cd /root/multiai
ADMIN_TOKEN='temporary-test-secret' docker compose -f docker-compose.multiai.yml config --quiet
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:3003/
```

### Release gate

نسخه فقط وقتی RC محسوب شود که:

- هیچ Critical/High unresolved باقی نماند.
- Backend از fresh DB بالا بیاید.
- LiteLLM در همان Compose resolve شود.
- frontend رسمی روی 3003 به backend صحیح وصل باشد.
- login، first chat، stream cancel، payment و logout E2E پاس شوند.
- تست دو کاربره ownership پاس شود.
- Lighthouse/Playwright budgets پاس شوند.
- reviewer مستقل current tree را PASS کند.

---

## 8. ترتیب اجرای پیشنهادی توسط تیم

### Sprint 1 — Trust & correctness

1. Compose secret fail-closed
2. LiteLLM service explicit
3. migration runner
4. request ID/error contract
5. payment atomicity
6. auth cookie/session hardening

### Sprint 2 — Design system & first-run

1. tokens/icon system
2. AppShell/navigation
3. landing conversion
4. onboarding
5. loading/error/empty states

### Sprint 3 — Chat excellence

1. stream lifecycle
2. composer
3. model picker
4. history/search
5. cost preview
6. mobile UX

### Sprint 4 — Product depth

1. model browser
2. dashboard/usage
3. wallet/payment history
4. API developer portal
5. admin/audit

### Sprint 5 — Verification & launch

1. E2E/a11y/performance
2. fresh/existing DB tests
3. load smoke
4. security review
5. RC deployment on official 3003 path

---

## 9. تصمیم‌های مهم قبل از اجرا

- LiteLLM باید داخل همین Compose بیاید یا external dependency رسمی بماند؛ حالت مبهم فعلی قابل قبول نیست.
- وعده «۱۰,۰۰۰ تومان هدیه» باید واقعاً با transaction و eligibility پیاده شود یا از UI حذف شود.
- token frontend فعلی باید به session cookie مهاجرت کند.
- `Base.metadata.create_all` باید فقط برای test/dev باقی بماند.
- مسیر رسمی انتشار فقط `/root/multiai` و پورت `3003` است.

## خروجی مورد انتظار نهایی

Multiai باید حس یک محصول premium و مطمئن بدهد، نه صرفاً یک پنل CRUD:

- اولین تجربه بدون اصطکاک
- پاسخ سریع و قابل‌کنترل
- هزینه کاملاً شفاف
- مدل‌یابی ساده برای کاربر غیرمتخصص
- ابزار حرفه‌ای برای developer
- فارسی واقعی و RTL بی‌نقص
- mobile-first
- خطاهای قابل‌فهم
- امنیت و billing قابل‌اعتماد
- معماری قابل‌توسعه بدون monolith شدن
