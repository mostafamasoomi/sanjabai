# SENIOR 3 — Frontend All Pages Deep Audit

**Auditor:** Senior Frontend Engineer  
**Scope:** All non-chat pages at `/root/multiai/frontend/`  
**Date:** 2026-07-14  

---

## Architecture Overview

- **Framework:** Next.js App Router (`'use client'` pages)  
- **API Proxy:** Next.js `rewrites` in `next.config.js` maps `/api/:path*` → backend `/:path*`. Explicit route files in `app/api/` take precedence when they exist.  
- **Auth:** `useAuth()` hook from `@/lib/auth` provides `{ token, user, login, signup, loading }`  
- **UI:** Custom design system with `card`, `btn`, `input`, `badge`, `skeleton` classes; RTL Persian UI  
- **Icons:** `@/components/ui/Icon` with named icons  
- **Toast:** `@/components/ui` toast notifications  

---

## 1. /wallet — Wallet Page (`frontend/app/wallet/page.tsx`)

**747 lines** | Well-implemented, feature-rich page.

### ✅ Strengths
- **Loading state:** Full skeleton components for balance, topup, packages, and table sections
- **Empty states:** Custom `EmptyStateIcon` component used for ledger (no transactions), packages (no packages), and payments (no payments)
- **Auth gate:** Shows login prompt when user is not authenticated (doesn't redirect)
- **Error handling:** `try/catch` with Persian toast messages on all API calls
- **Refresh:** Manual refresh button with spinning animation
- **Confirmation modal:** Topup flow has a confirmation modal before payment
- **Filter tabs:** Ledger entries filterable by all/credit/debit
- **Credit packages:** Display with bonus badges, purchase flow with payment redirect
- **Payment callback:** Supports `payment_url` redirect from topup and credit package checkout
- **Responsive:** Uses `grid-template-columns: repeat(auto-fit, minmax(300px, 1fr))` for balance+topup grid
- **Currency formatting:** Persian locale number formatting (fa-IR)

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Medium** | No 401 redirect handling — if wallet/ledger API returns 401, silently fails (sets null/empty). Other pages redirect to `/login`. |
| **Medium** | `effectiveAmount` calculated as `(selectedPreset ?? parseInt(topupAmount)) || 0` — `parseInt` on empty string returns `NaN`, which the `|| 0` catches, but `parseInt("10.5")` returns `10`, silently truncating decimal amounts |
| **Low** | Typo in toast: `"در حال انتزار به درگاه پرداخت..."` should be `"در حال انتقال به درگاه پرداخت..."` (line 229) |
| **Low** | The `<style jsx global>` block at bottom injects CSS globally (fadeIn, spin keyframes) — could conflict with other pages or cause FOUC |
| **Low** | No pagination on ledger table — all entries rendered at once (could be performance issue for heavy users) |
| **Info** | `LedgerFilter` type is `'all' | 'credit' | 'debit'` but the type itself is unused beyond the state type annotation |

### API Endpoints
| Frontend Call | Backend Route | Status |
|---|---|---|
| `GET /api/wallet` | `GET /wallet` | ✅ Via rewrite + explicit route |
| `GET /api/wallet/ledger` | `GET /wallet/ledger` | ✅ Via rewrite + explicit route |
| `GET /api/payment/history` | `GET /payment/history` | ✅ Via rewrite + explicit route |
| `GET /api/credit-packages` | `GET /credit-packages` | ✅ Via rewrite |
| `POST /api/wallet/topup` | `POST /wallet/topup` | ✅ Via rewrite + explicit route |
| `POST /api/credit-package/checkout` | `POST /credit-package/checkout` | ✅ Via rewrite |

---

## 2. /api-keys — API Keys Page (`frontend/app/api-keys/page.tsx`)

**316 lines** | Clean implementation.

### ✅ Strengths
- **Loading:** Uses spinner on generate button
- **Empty state:** Friendly message with icon when no keys exist
- **Auth:** 401 redirects to `/login` on all API calls
- **Copy key:** One-click copy with visual feedback (check icon + toast)
- **Key masking:** Keys shown masked by default, toggle to reveal
- **New key warning:** Clear warning that key is shown only once
- **API docs section:** Inline code examples for using the API
- **Status badges:** Active/inactive badges per key

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Medium** | **No scope selection** — The task requires checking scope selection, but there's no scope/permission selector when creating keys. Only a name field. |
| **Medium** | Copy on existing keys copies masked key (`${k.prefix}...${k.id}`) not actual key — user can't copy existing key value. This is intentional security but no UX indication. |
| **Low** | No loading skeleton on initial page load — page is blank until `fetchKeys` completes |
| **Low** | `fetchKeys` catch block is empty `catch {}` — silently swallows errors |
| **Low** | No confirmation dialog before revoking a key |
| **Low** | Keys with `!k.active` show no way to delete permanently (only active keys have revoke button) |

### API Endpoints
| Frontend Call | Backend Route | Status |
|---|---|---|
| `GET /api/api-keys` | `GET /api-keys` | ✅ Via rewrite + explicit route |
| `POST /api/api-keys` | `POST /api-keys` | ✅ Via rewrite + explicit route |
| `DELETE /api/api-keys/${id}` | `DELETE /api-keys/${id}` | ✅ Via rewrite + explicit route |

---

## 3. /dashboard — Dashboard Page (`frontend/app/dashboard/page.tsx`)

**948 lines** | Comprehensive dashboard with stats, subscription, billing.

### ✅ Strengths
- **Loading state:** Full skeleton for header, stat cards (×5), ledger, and content sections
- **Auth gate:** Shows login prompt with icon when not authenticated
- **Stats grid:** 5 stat cards (wallet balance, total spend, conversations, tokens, subscription status)
- **Subscription card:** Shows plan name, status badge, token usage progress bar, expiry date
- **Quick actions:** Links to chat, wallet, models, pricing, billing settings
- **Account info:** Email, username, phone, status, join date
- **PAYG toggle:** Pay-as-you-go toggle with custom switch UI
- **Hard limit:** Set spending hard limit with inline form
- **Ledger preview:** Recent 10 ledger entries with credit/debit styling
- **Error handling:** Uses `Promise.allSettled` — partial failures show partial data + info toast; total failure shows error toast
- **Responsive:** Grid layouts with `minmax` for various breakpoints

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Medium** | 7 concurrent API calls on page load (`/api/auth/me`, `/api/usage`, `/api/wallet`, `/api/wallet/ledger`, `/api/models`, `/api/subscription`, `/api/billing/settings`) — heavy load, could be slow on mobile |
| **Low** | Subscription status card hardcodes plan names (`free`, `pro`, `enterprise`) in `planLabels` — adding a new plan requires updating this map |
| **Low** | `billingSettings?.payg_hard_limit` comparison `!= null` — works for null but not undefined. Since state init is `null`, this is fine. |
| **Low** | Token usage progress bar color thresholds (70% warning, 90% danger) are hardcoded — should be configurable |
| **Info** | Dashboard links to `/pricing#credit-packages` — anchor link may not work with SPA routing |

### API Endpoints
| Frontend Call | Backend Route | Status |
|---|---|---|
| `GET /api/auth/me` | `GET /auth/me` | ✅ |
| `GET /api/usage` | `GET /me/usage` | ⚠️ **Mismatch**: Frontend calls `/api/usage` (rewrites to `/usage`), backend route is `/me/usage`. Explicit route at `app/api/usage/route.ts` likely handles this. |
| `GET /api/wallet` | `GET /wallet` | ✅ |
| `GET /api/wallet/ledger` | `GET /wallet/ledger` | ✅ |
| `GET /api/models` | `GET /v1/models` | ⚠️ Likely proxied by explicit route |
| `GET /api/subscription` | `GET /subscription` | ✅ Via rewrite |
| `GET /api/billing/settings` | `GET /billing/settings` | ✅ Via rewrite |
| `PUT /api/billing/settings` | `PUT /billing/settings` | ✅ Via rewrite |

---

## 4. /models — Models Page (`frontend/app/models/page.tsx`)

**196 lines** | Clean, well-structured model catalog.

### ✅ Strengths
- **Loading state:** 6 skeleton cards with staggered animation delays
- **Error state:** Dedicated error view with `EmptyState` component
- **Empty state:** `EmptyState` component for no search results
- **Search:** Real-time search by model name or provider
- **Filter:** Provider chip buttons, horizontally scrollable
- **Model cards:** Display name, provider, description, context window, capabilities, availability status
- **Capability tags:** Color-coded tags per capability type
- **CTA:** Each card has "Start chat with [model]" linking to `/chat?model=...`
- **Responsive:** `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`
- **Data source:** Uses `useCatalog()` hook — single source of truth, no hardcoded models

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Low** | No pricing display per model — task mentions "pricing display" but models page doesn't show cost per token. Pricing is in the catalog data but not rendered. |
| **Low** | Uses Tailwind classes (`py-6`, `mb-8`, `grid`, etc.) mixed with CSS class names — inconsistent styling approach compared to other pages that use inline styles |
| **Low** | Results count says `{filtered.length} مدل` without Persian numeral formatting |
| **Info** | `useCatalog()` fetches from `/api/catalog/models` — different from dashboard's `/api/models` |

---

## 5. /assistants — Assistants List (`frontend/app/assistants/page.tsx`)

**282 lines** | Well-implemented list page.

### ✅ Strengths
- **Loading state:** 6 skeleton cards
- **Empty state:** Context-aware messages (mine vs. public vs. all), CTA to create
- **Auth:** Redirects to `/login` if not authenticated
- **Filters:** All / Mine / Public filter buttons
- **Cards:** Icon, name, model_id, description (2-line clamp), public/private badge, date
- **Navigation:** Click card → `/assistants/${id}`
- **Create button:** Header button navigates to `/assistants/new`
- **Responsive:** `repeat(auto-fill, minmax(280px, 1fr))` grid

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Medium** | No 401 handling on `fetchAssistants` — if API returns 401, shows error toast but doesn't redirect to login (unlike the `!user` check which does redirect) |
| **Low** | No delete functionality from list view — must navigate to detail page |
| **Low** | Filter button `flexWrap: 'wrap'` but no scroll for many filters on mobile |

### API Endpoints
| Frontend Call | Backend Route | Status |
|---|---|---|
| `GET /api/assistants` | `GET /assistants` | ✅ Via rewrite + explicit route |

---

## 6. /assistants/new — Create Assistant (`frontend/app/assistants/new/page.tsx`)

**253 lines** | Clean form with good validation.

### ✅ Strengths
- **Auth:** Redirects to `/login` if not authenticated
- **Loading:** Skeleton during auth loading
- **Validation:** Name and system_prompt required, checked before submit
- **Form fields:** Name (required), description, system prompt (required), model select (from catalog), public toggle
- **Model select:** Uses `useCatalog()` to populate model dropdown
- **Public toggle:** Custom switch UI with contextual description
- **Character limits:** `maxLength={100}` on name, `maxLength={500}` on description
- **Submit:** Loading spinner, disables button during submission
- **Navigation:** Back button, cancel button, success → redirect to `/assistants`

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Low** | Model select uses `m.providerModelId || m.id` for value — could cause mismatch if backend expects different format |
| **Low** | No character count display for fields with maxLength |
| **Info** | System prompt placeholder text is helpful: `"تو یک دستیار متخصص در... هستی. وظیفه تو..."` |

### API Endpoints
| Frontend Call | Backend Route | Status |
|---|---|---|
| `POST /api/assistants` | `POST /assistants` | ✅ Via rewrite + explicit route |

---

## 7. /assistants/[id] — Edit Assistant (`frontend/app/assistants/[id]/page.tsx`)

**442 lines** | Full CRUD with ownership checks.

### ✅ Strengths
- **Auth:** Redirects to `/login` if not authenticated
- **Loading:** Skeleton during load
- **Error state:** "Assistant not found" view with back button
- **Ownership check:** `isOwner` flag controls edit vs. view-only mode
- **Non-owner view:** Shows assistant info + "Start chat" button
- **Edit form:** Same fields as create, pre-populated
- **Delete:** Two-step confirmation (click → "Confirm delete" label with 5s timeout)
- **Save:** PUT request with success toast
- **Start chat:** Button to `/chat?assistant=${id}`

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Medium** | No 401 handling on `fetchAssistant` — if API returns 401, sets `error: true` but doesn't redirect |
| **Low** | Delete confirmation uses `setTimeout` to reset after 5s — not a standard UX pattern, could confuse users |
| **Low** | `handleUpdate` calls `res.json()` twice on error (line 139 after checking `!res.ok`) — but `res.json()` may fail if body is not JSON |
| **Info** | Non-owner can't see system_prompt (intentional?) — form is only shown for owner |

### API Endpoints
| Frontend Call | Backend Route | Status |
|---|---|---|
| `GET /api/assistants/${id}` | `GET /assistants/${id}` | ✅ |
| `PUT /api/assistants/${id}` | `PUT /assistants/${id}` | ✅ |
| `DELETE /api/assistants/${id}` | `DELETE /assistants/${id}` | ✅ |

---

## 8. /pricing — Pricing Page (`frontend/app/pricing/page.tsx`)

**960 lines** | Rich pricing page with plans, packages, FAQ.

### ✅ Strengths
- **Loading state:** Skeletons for hero, plan cards, package cards, subscription banner
- **Subscription banner:** Shows current plan status, expiry, renew/cancel buttons
- **Plan cards:** Price, token quota, features list, daily limits, CTA button
- **Popular badge:** "⭐ محبوبترین" on pro plan
- **Unlimited glow:** Special visual treatment for unlimited plan
- **Current plan indicator:** "پلن فعلی" disabled button for active plan
- **Credit packages:** Separate section with bonus badges
- **FAQ section:** Accordion with 4 common questions
- **Bottom CTA:** "Start free chat" call-to-action
- **Hover effects:** Cards lift on hover with shadow
- **Auth-aware:** Redirects to login if not authenticated for purchases

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Medium** | Plans fetched without auth (`fetch('/api/plans')`) — public endpoint, OK. But subscription fetched with auth — if 401, silently ignored. |
| **Medium** | `handleSubscribe` and `handleBuyPackage` use `window.location.href` for redirect — causes full page reload instead of SPA navigation |
| **Low** | No error state for failed plan fetch — just shows empty page |
| **Low** | Plan colors map (`planColors`) only has `free`, `basic`, `pro`, `unlimited` — missing `enterprise` which exists in plan labels on dashboard |
| **Low** | FAQ section hardcoded in component — should be fetched from CMS or API |

### API Endpoints
| Frontend Call | Backend Route | Status |
|---|---|---|
| `GET /api/plans` | `GET /plans` | ✅ Via rewrite |
| `GET /api/subscription` | `GET /subscription` | ✅ Via rewrite |
| `POST /api/subscription/checkout` | `POST /subscription/checkout` | ✅ Via rewrite |
| `POST /api/subscription/cancel` | `POST /subscription/cancel` | ✅ Via rewrite |
| `POST /api/subscription/renew` | `POST /subscription/renew` | ✅ Via rewrite |
| `POST /api/credit-package/checkout` | `POST /credit-package/checkout` | ✅ Via rewrite |

---

## 9. /admin — Admin Panel (`frontend/app/admin/AdminPanel.tsx` + `page.tsx`)

**1089 + 27 lines** | Full admin dashboard with 8 tabs.

### ✅ Strengths
- **Dynamic import:** `page.tsx` uses `next/dynamic` with `ssr: false` — no server-side rendering for admin
- **Admin auth:** Separate token-based authentication (not user auth)
- **Login screen:** Clean login form with Enter key support
- **Sidebar:** Responsive sidebar with mobile hamburger menu
- **8 tabs:** Dashboard, Users, Pricing, Features, Discounts, About, Proxy, Models
- **Dashboard:** 5 stat cards + recent transactions table
- **Users:** Table with edit modal (username, email, plan, wallet balance) + ban action
- **Pricing:** CRUD for model pricing with table + form
- **Features:** CRUD with icon, title, description, order, active status
- **Discounts:** CRUD for discount codes with percentage
- **About:** Edit title and body for about page
- **Proxy:** Configure proxy type, URL, active status
- **Models:** View registered models
- **Org default model:** Set organization-wide default model
- **Loading:** Skeleton cards for dashboard stats
- **Empty states:** Per-section empty state messages
- **Error handling:** `api()` helper throws on 401 (clears token) and on non-ok responses
- **Responsive:** Mobile sidebar overlay, responsive grid layouts

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **High** | **Admin token stored in module-level `let TOKEN = ''`** — not persisted, lost on page refresh. Admin must re-login every time. |
| **High** | **No admin route protection** — Admin page renders login screen client-side. No server-side check. Anyone can see the login form. |
| **Medium** | **Many admin API routes missing from frontend proxy** — Admin panel calls `/api/admin/analytics`, `/api/admin/features`, `/api/admin/discounts`, `/api/admin/about`, `/api/admin/proxy`, `/api/admin/users`, `/api/admin/users/{id}/ban`, `/api/admin/users/{id}`, `/api/admin/org-default-model`. These are covered by the `/api/:path*` rewrite but there's only one explicit route: `app/api/admin/pricing/route.ts`. |
| **Medium** | No loading state for individual tab content — only dashboard has skeleton |
| **Medium** | Delete actions (features, discounts) have no confirmation dialog |
| **Low** | User edit modal doesn't validate email format |
| **Low** | `models` in admin fetched via `fetch('/api/models')` without auth — relies on public endpoint |
| **Low** | Mobile sidebar has no keyboard trap management (accessibility) |

---

## 10. /login — Login Page (`frontend/app/login/page.tsx`)

**70 lines** | Minimal but functional.

### ✅ Strengths
- **Validation:** Checks empty email/password before submit
- **Error display:** Red error banner with message
- **Loading:** Button text changes to "در حال ورود..."
- **Navigation:** Link to signup page
- **Centered layout:** `min-h-[80vh]` centered card

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Medium** | No email format validation on login (only on submit if empty) |
| **Medium** | No "forgot password" link |
| **Low** | No loading skeleton (page is simple enough it's not needed) |
| **Low** | Uses `<a href="/signup">` instead of `<Link>` — causes full page reload |
| **Low** | Password field placeholder says "حداقل ۶ کاراکتر" but login doesn't enforce minimum length (only signup does) |
| **Info** | After login, redirects to `/chat` — no "return to previous page" logic |

---

## 11. /signup — Registration Page (`frontend/app/signup/page.tsx`)

**137 lines** | Better UX than login.

### ✅ Strengths
- **Validation:** Email format regex, password min length (6), inline validation messages
- **Touched state:** Shows validation only after field blur
- **Positive feedback:** Green checkmark when password is valid
- **Error display:** Red error banner
- **Loading:** Spinner animation during signup
- **Trust signals:** SSL, no VPN needed, Rial charging
- **Navigation:** Link to login page
- **Logo:** Sparkles icon with Multiai branding

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Medium** | After signup, redirects to `/onboarding` — but if user closes browser during onboarding, they go to `/chat` next time (onboarding check is localStorage-based) |
| **Low** | `<a href="/login">` instead of `<Link>` — full page reload |
| **Low** | No password strength indicator (only length check) |
| **Low** | No terms of service / privacy policy checkbox |
| **Info** | Signup redirects to `/onboarding` — good flow |

---

## 12. /onboarding — Welcome Flow (`frontend/app/onboarding/page.tsx`)

**619 lines** | Premium 5-step onboarding experience.

### ✅ Strengths
- **5 steps:** Welcome → Goal selection → Model favorites → Recommendation → Quick tips
- **Step indicator:** Progress bars with labels
- **Auth guard:** Redirects to `/login` if not authenticated, `/chat` if already onboarded
- **Goal selection:** 5 goals (coding, writing, translation, analysis, general) with icons
- **Model catalog:** Uses `useCatalog()` to populate model selection
- **Favorites:** Persisted to localStorage, used for recommendation
- **Recommendation:** Smart model suggestion based on goal + favorites
- **Quick tips:** 3 tips (⌘K, model switching, wallet tracking)
- **Loading:** Skeleton during auth and catalog loading
- **Animations:** `fade-in slide-up` transitions between steps
- **Responsive:** `grid-cols-1 sm:grid-cols-2` for goals and models
- **Premium design:** Ambient glow background, gradient accents

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Low** | Typo in step 1 heading: `"قصد دارید چه کاریم؟"` should be `"قصد دارید چه کاری کنید؟"` or `"قصد دارید چه کاری انجام دهید؟"` (line 334) |
| **Low** | Typo in step 4: `"آماده میکارید"` should be `"آماده میشوید"` (line 563) |
| **Low** | Favorites are saved to localStorage under `multiai_favorite_models` — not synced to server |
| **Low** | `formatContext` uses `toFixed(1)` for millions but `Math.round` for thousands — inconsistent precision |
| **Info** | Fallback models (e.g., "Claude Sonnet 4", "GPT-4o") are hardcoded — could become stale |

---

## 13. /referral — Referral Page (`frontend/app/referral/page.tsx`)

**122 lines** | Simple referral code display.

### ✅ Strengths
- **Auth:** Redirects to `/login` if not authenticated
- **Loading:** Skeleton during auth loading
- **Referral code:** Displayed in monospace code block
- **Copy button:** One-click copy of referral link
- **How it works:** 3-step explanation

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **Medium** | **No referral stats** — Backend has `GET /referral/stats` endpoint but frontend doesn't fetch or display stats (referral count, rewards earned) |
| **Medium** | Copy function doesn't show toast feedback — `copyLink()` just calls `navigator.clipboard.writeText()` without success/error handling |
| **Low** | No loading state for referral code — shows "در حال بارگذاری..." if `user.referral_code` is null/undefined |
| **Low** | Referral link uses `window.location.origin` — correct for client-side but SSR would fail |
| **Low** | No share button (WhatsApp, Telegram, etc.) — only copy |
| **Info** | Profile page also has referral section — duplicate UI |

---

## 14. /profile — User Profile (`frontend/app/profile/page.tsx`)

**396 lines** | Feature-rich profile page.

### ✅ Strengths
- **Avatar:** Initial letter with gradient background
- **Stats grid:** Balance, daily usage, email
- **Settings toggles:** Email notifications, Telegram notifications, Dark mode (custom switch UI)
- **Change password:** Current + new + confirm fields with validation
- **Telegram link:** Connect Telegram account with numeric ID
- **Referral section:** Code + link with copy buttons
- **Danger zone:** Delete account (disabled, "coming soon")
- **Loading states:** Spinner on buttons during API calls

### ⚠️ Issues

| Severity | Issue |
|----------|-------|
| **High** | **Auth token inconsistency** — Profile page uses `localStorage.getItem('auth_token')` directly (lines 39, 48, 64, 96) instead of `useAuth().token`. This bypasses the auth context and could use stale tokens. Other pages consistently use `useAuth()` |
| **Medium** | **No 401 handling** — `fetchUsage` and `fetchBalance` silently fail on 401. `handleChangePassword` and `handleLinkTelegram` show generic error but don't redirect. |
| **Medium** | **Settings toggles are client-only** — Email/Telegram/Dark mode toggles change local state but are never saved to backend. Dark mode toggle doesn't actually change the theme. |
| **Medium** | **No loading skeleton** — Page shows nothing until data loads |
| **Low** | `fetchUsage` expects `usage.used_today` and `usage.daily_limit` — but backend `/me/usage` returns `total_spend`, `turns`, `total_tokens` (different shape) |
| **Low** | Password change requires minimum 8 characters (line 58) but signup only requires 6 — inconsistent |
| **Low** | No "back" navigation or breadcrumbs |
| **Info** | `useEffect` with `[user]` dependency but `user` from `useAuth()` — could cause re-renders |

---

## Cross-Cutting Issues

### 1. Missing Frontend API Proxy Routes (Covered by Rewrite)

The following API endpoints are called by frontend pages but don't have explicit Next.js API route files. They work through the `next.config.js` rewrite rule (`/api/:path*` → backend), but explicit routes would provide:
- Custom error handling
- Request transformation
- Caching headers

| Missing Route | Used By |
|---|---|
| `/api/subscription` | Dashboard, Pricing |
| `/api/subscription/checkout` | Pricing |
| `/api/subscription/cancel` | Pricing |
| `/api/subscription/renew` | Pricing |
| `/api/billing/settings` | Dashboard |
| `/api/plans` | Pricing |
| `/api/credit-packages` | Wallet |
| `/api/credit-package/checkout` | Wallet, Pricing |
| `/api/admin/analytics` | Admin |
| `/api/admin/features` | Admin |
| `/api/admin/discounts` | Admin |
| `/api/admin/about` | Admin |
| `/api/admin/proxy` | Admin |
| `/api/admin/users` | Admin |
| `/api/admin/org-default-model` | Admin |
| `/api/referral/stats` | Not called (but exists in backend) |

### 2. Inconsistent Auth Handling

| Pattern | Pages |
|---|---|
| Redirect to `/login` via `router.replace()` | Assistants, Assistants/new, Assistants/[id], Onboarding, Referral |
| Show login prompt (no redirect) | Wallet, Dashboard |
| Silent failure on 401 | API Keys (redirects), Wallet (silent), Dashboard (silent) |
| Direct `localStorage.getItem('auth_token')` | **Profile only** (should use `useAuth()`) |

### 3. Inconsistent Styling Approach

| Approach | Pages |
|---|---|
| Inline styles (React) | Wallet, API Keys, Dashboard, Assistants, Pricing, Profile, Admin |
| Tailwind utility classes | Models, Login, Signup, Onboarding |
| Mixed (both) | Onboarding, Signup |

### 4. No Global Error Boundary

No `error.tsx` or global error boundary exists for catching rendering errors per-route segment.

### 5. Responsive Design Summary

| Page | Mobile Support |
|---|---|
| Wallet | ✅ `auto-fit` grids, `flexWrap` on filters |
| API Keys | ✅ Flex layout, code blocks wrap |
| Dashboard | ✅ `auto-fit` grids, `minmax(180px, 1fr)` |
| Models | ✅ `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` |
| Assistants | ✅ `auto-fill, minmax(280px, 1fr)` |
| Pricing | ✅ `auto-fit, minmax(240px, 1fr)` |
| Admin | ✅ Mobile sidebar overlay, responsive grids |
| Login | ✅ `max-w-sm` centered card |
| Signup | ✅ `max-w-sm` centered card |
| Onboarding | ✅ `sm:grid-cols-2` responsive grids |
| Referral | ✅ Simple flex layout |
| Profile | ⚠️ Uses fixed pixel widths in places |

---

## Summary of Critical/High Issues

| # | Severity | Page | Issue |
|---|---|---|---|
| 1 | **High** | Admin | Admin token stored in module-level variable, lost on refresh |
| 2 | **High** | Profile | Uses `localStorage.getItem('auth_token')` instead of `useAuth().token` |
| 3 | **Medium** | Wallet | No 401 redirect handling |
| 4 | **Medium** | API Keys | No scope/permission selection for key creation |
| 5 | **Medium** | Dashboard | 7 concurrent API calls on load |
| 6 | **Medium** | Pricing | `window.location.href` for payment redirects (full reload) |
| 7 | **Medium** | Referral | No referral stats displayed despite backend endpoint existing |
| 8 | **Medium** | Profile | Settings toggles are client-only, never persisted |
| 9 | **Medium** | Profile | Usage data shape mismatch (`used_today` vs `total_spend`) |
| 10 | **Medium** | Onboarding | Two typos in Persian text |
| 11 | **Medium** | Wallet | Typo in toast message |
| 12 | **Low** | Models | No pricing display per model |
| 13 | **Low** | Login/Signup | Uses `<a href>` instead of `<Link>` |

---

## Files Audited

| # | File | Lines | Status |
|---|---|---|---|
| 1 | `frontend/app/wallet/page.tsx` | 747 | ✅ Audited |
| 2 | `frontend/app/api-keys/page.tsx` | 316 | ✅ Audited |
| 3 | `frontend/app/dashboard/page.tsx` | 948 | ✅ Audited |
| 4 | `frontend/app/models/page.tsx` | 196 | ✅ Audited |
| 5 | `frontend/app/assistants/page.tsx` | 282 | ✅ Audited |
| 6 | `frontend/app/assistants/new/page.tsx` | 253 | ✅ Audited |
| 7 | `frontend/app/assistants/[id]/page.tsx` | 442 | ✅ Audited |
| 8 | `frontend/app/pricing/page.tsx` | 960 | ✅ Audited |
| 9 | `frontend/app/admin/AdminPanel.tsx` | 1089 | ✅ Audited |
| 10 | `frontend/app/admin/page.tsx` | 27 | ✅ Audited |
| 11 | `frontend/app/login/page.tsx` | 70 | ✅ Audited |
| 12 | `frontend/app/signup/page.tsx` | 137 | ✅ Audited |
| 13 | `frontend/app/onboarding/page.tsx` | 619 | ✅ Audited |
| 14 | `frontend/app/referral/page.tsx` | 122 | ✅ Audited |
| 15 | `frontend/app/profile/page.tsx` | 396 | ✅ Audited |
| 16 | `frontend/next.config.js` | 49 | ✅ Reviewed |
| 17 | `frontend/lib/useCatalog.ts` | 50 | ✅ Reviewed |

**Total lines audited: ~6,703**
