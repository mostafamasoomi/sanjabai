# Multiai Full Audit & Ideal UX Implementation Plan

> **For Hermes:** پس از تأیید مالک، این سند باید task-by-task با subagent-driven-development اجرا شود؛ در این مرحله هیچ implementation انجام نشود.

**Goal:** تبدیل `/root/multiai` به یک محصول Persian AI workspace سریع، قابل‌اعتماد، premium و task-first، با تمرکز اولویت‌دار روی UI/UX، بدون دست‌زدن به `/root/multiapi`.

**Architecture:** حفظ Next.js 14 App Router + React 18 + TypeScript + Tailwind + Recharts در frontend و FastAPI + PostgreSQL + Redis + LiteLLM در backend، اما با API contract واحد، auth/session امن، migration واقعی، observability و component/design system منسجم. رابط عمومی روی `0.0.0.0:3003` باقی می‌ماند؛ backend روی `127.0.0.1:8001` و admin جدا روی `127.0.0.1:8081`.

**Tech Stack:** Next.js 14، React 18، TypeScript، Tailwind، Recharts، Playwright، FastAPI، SQLAlchemy async، PostgreSQL 16، Redis 7، LiteLLM، pytest/httpx.

---

## 1. Scope و قانون‌های غیرقابل‌مذاکره

- فقط repository رسمی `/root/multiai` در scope است.
- `/root/multiapi`، پورت 3005 و containerهای آن نباید تغییر کنند.
- هیچ secret، token، password یا SSH key در plan، git، frontend bundle یا log منتشر نشود.
- هیچ claim بازاریابی بدون منبع واقعی در UI باقی نماند؛ اعداد illustrative باید label شوند یا حذف شوند.
- قبل از هر implementation، branch/commit جدا و working tree baseline ثبت شود.
- هیچ task بدون test و acceptance gate بسته نشود.

---

## 2. گزارش وضعیت فعلی (بر اساس بازرسی واقعی)

### 2.1 سرویس‌ها و دسترسی

| سرویس | وضعیت مشاهده‌شده | آدرس |
|---|---|---|
| Frontend رسمی `multiai_frontend` | running | `0.0.0.0:3003 -> 3000` |
| Backend `multiai_api` | پاسخ `200` برای health | `127.0.0.1:8001 -> 8000` |
| Admin جدا | container running، root پاسخ `404` | `127.0.0.1:8081` |
| PostgreSQL / Redis | در Compose فعال | شبکه داخلی |
| LiteLLM/Tunnel | در Compose فعال | شبکه داخلی |

صفحات عمومی بررسی‌شده (`/`, `/login`, `/chat`, `/models`, `/dashboard`) همگی HTTP 200 برگرداندند.

### 2.2 وضعیت repository و کیفیت build/test

- repository در commit `528f46b` قرار دارد و working tree بسیار بزرگ و عمدتاً uncommitted است؛ این موضوع traceability و rollback را پرریسک می‌کند.
- `npm run build` روی host اجرا نشد چون `node_modules` نصب نیست (`next: not found`). باید build داخل container/CI یا پس از install lockfile اجرا شود.
- `pytest -q`: **9 passed، 55 errors**. علت غالب، ناسازگاری test mock با async migration در `backend/migrate.py` است: `.all()` روی coroutine استفاده شده و startup lifespan قبل از هر test می‌شکند.
- `docker compose ps` بدون `.env` با خطای required `ADMIN_TOKEN` متوقف شد؛ با این حال containerهای قبلی فعال بودند. باید `.env.example`، secret bootstrap و CI contract شفاف شوند.

### 2.3 معماری frontend فعلی

موجود است:

- routeهای login/signup/chat/dashboard/wallet/topup/profile/api-keys/models/compare/playground/admin/pricing
- `AppShell` با desktop header، mobile drawer، mobile bottom nav، theme و language toggle
- design tokenهای CSS در `frontend/app/globals.css`
- `AuthProvider` در `frontend/lib/auth.tsx`
- `Chat` و SSE stream
- API routeهای Next برای auth، chat، wallet، payment، usage، conversations، models و admin pricing
- Recharts در dependencies

ضعف‌های verified:

1. **Navigation overload:** ۱۰ آیتم در header و mobile bottom nav؛ برای محصول task-first زیاد است.
2. **Emoji as UI icon:** nav/CTA از emoji استفاده می‌کند؛ ظاهر غیرحرفه‌ای و accessibility ضعیف.
3. **AppShell monolithic:** auth، nav، desktop/mobile layout و footer در یک component؛ route-level code splitting و provider isolation ضعیف.
4. **API client بسیار حداقلی:** `frontend/lib/api.ts` فقط چند تابع دارد؛ error contract، request ID، timeout، retry، auth refresh و typed response ندارد.
5. **Auth token در localStorage:** ریسک XSS و عدم انطباق با session امن؛ باید HttpOnly cookie/rotation شود.
6. **Chat UX ناقص:** مدل‌ها و conversationها fetch می‌شوند ولی loading/error/offline، draft persistence، search، cost preview، keyboard shortcuts و stream recovery کامل نیستند.
7. **Mock/claim risk:** landing آمار `۵۰+ مدل`، `۹۹.۹٪ uptime`، `۱۰۰٪ پشتیبانی` و `۱۰,۰۰۰ تومان هدیه` را hardcode کرده؛ باید به data contract/feature flag/claim-safe copy تبدیل شود.
8. **Landing generic:** سکشن‌های متعدد با کارت و emoji وجود دارد اما live demo، use-case routing، cost transparency و proof واقعی کم است.
9. **Accessibility:** focus management، icon labels، semantic navigation، modal focus trap، reduced motion و automated a11y coverage کافی نیست.
10. **Typography/performance:** احتمال وابستگی runtime به font خارجی، provider بزرگ global و نبود performance budget route-level.
11. **RTL/LTR boundary:** code/model IDs/price/API key باید explicit LTR isolation داشته باشند.

### 2.4 معماری backend فعلی

- `backend/app.py` یک monolith حدود ۱۶۰۰+ خط است و route، auth، wallet، proxy، payment و startup را ترکیب می‌کند.
- migration runner وجود دارد، اما test seam آن شکسته است و `Base.metadata.create_all`/schema evolution باید audit شود.
- auth و billing مسیرهای حساس‌اند؛ session/token contract و ownership/payment concurrency باید با تست رفتاری تثبیت شوند.
- endpointهای public/admin و error response contract یکپارچه و typed نیستند.
- `LITELLM_HOST` و service topology باید با Compose صریح و قابل‌تکرار باشند.

---

## 3. تحلیل رقابتی و جایگاه مطلوب

### رقبای مرجع محصولی

| رقیب | نقطه قوت UX | ضعف/فرصت برای Multiai |
|---|---|---|
| ChatGPT | onboarding بسیار کوتاه، chat-first، حافظه و history واضح | multi-model، قیمت ریالی و کنترل هزینه را بهتر می‌توانیم ارائه کنیم |
| Claude | typography آرام، پاسخ‌محور و distraction کم | model marketplace و wallet ایرانی می‌تواند مزیت باشد |
| Poe | model switching و discovery ساده | شفافیت مالی، فارسی و API developer workflow بهتر شود |
| OpenRouter | catalog، pricing و developer orientation قوی | کاربر عمومی و RTL/پرداخت داخلی ضعیف؛ Multiai باید هر دو segment را جدا کند |
| Google AI Studio/Gemini | playground و قابلیت‌های model-centric | تجربه فارسی، wallet و unified provider بهتر شود |
| Perplexity | intent-first و answer workflow | برای Multiai، task templates و model recommendation قابل اقتباس است |

### نتیجه رقابتی

Multiai نباید صرفاً «یک chat با چند مدل» باشد. جایگاه ایده‌آل:

> **سریع‌ترین workspace فارسی برای انتخاب مدل مناسب، گرفتن پاسخ موفق، کنترل هزینه و انتقال امن از کاربر عمومی به developer API.**

تمایزهای قابل دفاع:

- فارسی/RTL واقعی، نه ترجمه سطحی
- model recommendation بر اساس هدف و بودجه
- cost preview و ledger شفاف قبل/بعد از request
- local payment/wallet و quota قابل فهم
- chat UX حرفه‌ای + API key workflow در یک workspace
- performance و reliability با اعداد واقعی، نه claim تبلیغاتی

---

## 4. حالت ایده‌آل (North Star Experience)

### Journey کاربر جدید

`Landing → هدف خود را انتخاب کن → مدل پیشنهادی → prompt آماده → اولین پاسخ موفق → نمایش هزینه/مصرف → شارژ یا API key`

هدف: کمتر از ۹۰ ثانیه تا اولین پاسخ موفق.

### Information architecture پیشنهادی

- **خانه:** promise دقیق، live model demo، use cases، cost/security proof، CTA
- **Workspace:** chat، conversation search، model picker، cost preview، usage status
- **Models:** filter by task/budget/speed/context، compare، use in chat
- **Usage & Wallet:** موجودی برجسته، هزینه امروز/ماه، forecast، ledger، top-up
- **Developer:** API keys، quickstart، code snippets، request logs
- **More:** profile، referral، support، settings
- **Admin:** جدا از shell کاربر و با authorization مستقل

### Visual direction

- dark-first premium، آرام و کم‌نئون
- surface hierarchy سه‌لایه، border کم‌کنتراست، accent بنفش/آبی کنترل‌شده
- Vazirmatn self-host/subset، اعداد tabular و code با font mono
- icon system واقعی (Lucide یا داخلی SVG)، حذف emoji از nav و CTA
- micro-interaction کوتاه با `prefers-reduced-motion`
- glass فقط برای overlay/hero، نه همه کارت‌ها

---

## 5. Roadmap اجرایی اولویت‌بندی‌شده

### Phase 0 — Stabilization Gate (اول از همه)

**هدف:** baseline قابل اعتماد قبل از redesign.

1. ثبت `git status`, commit و runtime versions؛ ایجاد branch `feat/multiai-aurora`.
2. اصلاح async migration test seam در `backend/migrate.py` و fixtureهای `backend/tests/conftest.py`؛ اجرای دوباره `pytest -q`.
3. اطمینان از `frontend/package-lock.json` و اجرای `npm ci && npm run build` داخل محیط reproducible.
4. ساخت `.env.example` بدون secret واقعی و دستور startup رسمی با `ADMIN_TOKEN` اجباری.
5. اضافه‌کردن smoke script برای Compose، `/health/live`, `/health/ready`, صفحات مهم و API auth.

**Gate:** صفر error در test suite موجود، frontend build موفق، Compose fresh start موفق.

### Phase 1 — Product/Data Contract

**Files:** `docs/product-contract.md`, `frontend/lib/feature-flags.ts`, `frontend/app/page.tsx`, `frontend/app/models/page.tsx`, `frontend/app/pricing/page.tsx`, `frontend/app/dashboard/page.tsx`, `backend/app.py`.

1. تعریف segmentها: consumer، developer، team.
2. حذف یا label کردن claims hardcoded.
3. تعریف typed model catalog: provider، capability، context، pricing، availability، recommended_for.
4. تعریف contract هزینه، token، balance، quota و signup credit.

**Gate:** هیچ promise یا metric بدون source واقعی در production UI نماند.

### Phase 2 — Design System و Component Foundation

**Create:** `frontend/design/tokens.ts`, `frontend/components/ui/Icon.tsx`, `Button.tsx`, `Badge.tsx`, `Surface.tsx`, `Tooltip.tsx`, `Modal.tsx`, `Spinner.tsx`, `EmptyState.tsx`, `ErrorState.tsx`.

**Modify:** `frontend/app/globals.css`, `frontend/components/ui.tsx`.

1. تبدیل CSS tokenها به source typed و mapping Tailwind/CSS.
2. icon strategy با aria-label و icon-only focus.
3. standardize button/input/card/table/badge/modal.
4. اضافه‌کردن focus ring، contrast، reduced-motion و safe-area.

**Gate:** صفحات موجود بدون visual regression شکسته build شوند؛ keyboard navigation عملی باشد.

### Phase 3 — Navigation و Shell بازطراحی‌شده

**Create:** `frontend/components/CommandPalette.tsx`, `frontend/components/KeyboardShortcuts.tsx`, `frontend/components/Sidebar.tsx`.

**Modify:** `frontend/components/AppShell.tsx`, `frontend/app/layout.tsx`.

1. desktop sidebar collapsible با ۴ مسیر اصلی: Chat، Models، Usage/Wallet، Developer.
2. مسیرهای فرعی در More و command palette.
3. mobile bottom nav فقط Chat، Models، Wallet، More.
4. active state، focus trap، ESC، scroll restoration و safe-area.
5. جداسازی admin shell از user shell.

**Gate:** کاربر در desktop/mobile بدون scroll افقی به چهار task اصلی برسد.

### Phase 4 — Landing Conversion و Onboarding

**Create:** `frontend/components/landing/Hero.tsx`, `LiveModelDemo.tsx`, `UseCases.tsx`, `CostTransparency.tsx`, `TrustSection.tsx`, `FAQ.tsx`, `frontend/app/onboarding/page.tsx`, `frontend/components/onboarding/GoalPicker.tsx`, `ModelRecommendation.tsx`, `FirstPrompt.tsx`.

**Modify:** `frontend/app/page.tsx`, `frontend/lib/auth.tsx`.

1. Hero با promise دقیق و CTA واحد.
2. live demo متصل به catalog واقعی یا illustrative با label.
3. use caseهای کدنویسی، تحلیل، ترجمه، تولید محتوا.
4. cost transparency با مثال واقعی.
5. onboarding goal → recommendation → first prompt.

**Gate:** تست usability: کاربر جدید در کمتر از ۹۰ ثانیه اولین پاسخ موفق بگیرد.

### Phase 5 — Chat Workspace حرفه‌ای

**Create:** `frontend/components/chat/ConversationList.tsx`, `Composer.tsx`, `ModelPicker.tsx`, `CostPreview.tsx`, `StreamStatus.tsx`, `MessageActions.tsx`, `CodeBlock.tsx`.

**Modify:** `frontend/app/chat/page.tsx`, `frontend/components/Chat.tsx`, `frontend/lib/sse.ts`.

1. optimistic user message و assistant placeholder.
2. AbortController cancel، retry/regenerate، reconnect.
3. draft persistence و conversation search.
4. model picker با task/cost/context.
5. cost preview قبل از ارسال و usage بعد از پاسخ.
6. copy/export/share با privacy warning.
7. code block با copy و LTR isolation.
8. keyboard shortcuts: new chat، focus composer، cancel.

**Gate:** E2E login → select model → send → stream → cancel/retry → usage.

### Phase 6 — Model Browser و Compare

**Create:** `frontend/components/models/ModelCard.tsx`, `ModelFilters.tsx`, `ModelCompare.tsx`, `ModelRecommendation.tsx`.

**Modify:** `frontend/app/models/page.tsx`, `frontend/app/compare/page.tsx`, `frontend/app/api/models/route.ts`.

1. filter بر اساس task، budget، speed، context و provider.
2. card شامل capability، context، قیمت، availability و CTA.
3. compare حداکثر سه مدل با جدول readable.
4. deep link به chat با model انتخاب‌شده.

### Phase 7 — Usage/Wallet/Payments Trust Layer

**Create:** `frontend/components/usage/UsageSummary.tsx`, `UsageChart.tsx`, `frontend/components/wallet/LedgerTable.tsx`, `TopupFlow.tsx`.

**Modify:** dashboard، wallet، topup، payment API routes و backend payment service.

1. balance، هزینه امروز/ماه، projected remaining.
2. ledger filter و status واضح.
3. top-up با confirmation و idempotency.
4. payment callback با row lock، verify amount، atomic wallet+ledger+order transaction.

**Gate:** تست concurrent callback و ownership user.

### Phase 8 — Developer Experience

**Modify:** `frontend/app/api-keys/page.tsx`, `frontend/app/playground/page.tsx`, `frontend/lib/api.ts`.

**Create:** `frontend/app/developers/page.tsx`, `frontend/components/developer/Quickstart.tsx`, `CodeSnippet.tsx`, `RequestLog.tsx`.

1. ساخت key فقط یک‌بار secret را نمایش دهد.
2. quickstart برای curl/Python/JS.
3. endpoint/model/usage/request-id واضح.
4. revoke و key status.

### Phase 9 — Backend Architecture/Security

**Create:** `backend/app/{main,config,db}.py`, `backend/app/{routers,services,schemas,models,middleware}/...` incrementally.

**Modify:** `backend/app.py`, `backend/security.py`, `backend/payment.py`, migrations، Compose.

1. شکستن monolith به thin routers و service layer.
2. request-id و typed error contract.
3. HttpOnly/Secure/SameSite cookie، rotation، revoke/logout-all.
4. rate limit رفتاری login/reset/chat.
5. admin auth مستقل، بدون localStorage token.
6. migration runner source of truth؛ حذف schema drift.
7. health live/ready/deep.

### Phase 10 — Performance/Observability

1. self-host/subset font و حذف external runtime dependency.
2. dynamic import chart/admin/playground.
3. route-level providers و loading/error/empty states.
4. performance budget: LCP <2.5s، INP <200ms، CLS <0.1، initial landing JS <180KB gzip هدف.
5. metrics: request id، latency، first-token latency، upstream error، model، payment event بدون secret/content.
6. bundle analysis و Lighthouse mobile baseline.

### Phase 11 — QA و Release

**Create:** `frontend/tests/smoke.spec.ts`, `frontend/tests/a11y.spec.ts`, `frontend/tests/navigation.spec.ts`, `backend/tests/test_error_contract.py`, `test_auth_security.py`, `test_payment_concurrency.py`, `test_ownership.py`.

سناریوهای اجباری:

- signup/login/logout و session expiry
- first-run onboarding
- chat stream/cancel/retry/reconnect
- دو کاربر و عدم دسترسی به conversation/ledger دیگری
- wallet top-up و callback duplicate/concurrent
- API key create/revoke
- admin unauthorized/authorized
- mobile 360px، desktop 1440px، RTL/LTR code
- keyboard-only و reduced-motion
- fresh DB و existing DB migration

**Release gate:** build/test/compose/E2E/a11y/performance همگی green؛ rollback procedure مستند.

---

## 6. معیارهای پذیرش نسخه ایده‌آل

### UX

- اولین پاسخ موفق ≤۹۰s برای کاربر جدید.
- model مناسب ≤۱۵s پیدا شود.
- Chat، مدل، wallet و usage در mobile بدون horizontal scroll.
- هیچ صفحه سفید یا خطای بدون action.
- همه icon-only controlها label و focus قابل مشاهده داشته باشند.

### Performance

- LCP <2.5s، INP <200ms، CLS <0.1 روی baseline موبایل.
- landing initial JS <180KB gzip هدف.
- chat shell بدون bundle dashboard/admin.

### Reliability/Security

- pytest و Playwright green.
- fresh/existing migration green.
- session خام در localStorage نباشد.
- payment callback idempotent و atomic.
- ownership و admin authorization با تست رفتاری اثبات شود.

### Visual quality

- emoji از navigation/CTA حذف شود.
- typography و spacing یکنواخت.
- data واقعی distinguishable از illustrative.
- dark/light، RTL/LTR، keyboard و reduced-motion پشتیبانی شود.

---

## 7. ترتیب اجرای پیشنهادی توسط تیم

1. Phase 0 Stabilization Gate
2. Phase 1 Product/Data Contract
3. Phase 2 Design System
4. Phase 3 Shell/Navigation
5. Phase 4 Landing/Onboarding
6. Phase 5 Chat
7. Phase 6 Models
8. Phase 7 Wallet/Payments
9. Phase 8 Developer
10. Phase 9 Backend hardening
11. Phase 10 Performance/Observability
12. Phase 11 QA/Release

هر phase باید با branch/PR مستقل، test evidence، screenshot/trace برای UI و rollback note تحویل شود. هیچ phase بعدی نباید failureهای gate قبلی را پنهان کند.
