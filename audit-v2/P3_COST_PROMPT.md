# Phase 3 — Cost Tracker + Prompt Library Report

**Date:** 2026-07-16  
**Engineer:** Senior Frontend Engineer  
**Status:** ✅ Complete — Build passes

---

## 1. Summary

Phase 3 implements:
- **Pre-send cost estimate** in the chat composer — shows estimated tokens & تومان cost while typing
- **Wallet balance warning** — yellow warning when balance < 5,000 تومان
- **Prompt Library** page (`/prompts`) with 10 Persian templates, search, and category filtering
- **Prompt Library quick-access button** in the chat composer

All changes are client-side only (no new backend endpoints needed for prompt library).

---

## 2. Files Modified

### 2.1 `frontend/app/chat/page.tsx` — Cost Tracker + Wallet + Prompt Library Button

**Changes:**

1. **Pre-send cost estimate** (`useMemo`):
   - Calculates `Math.round(input.length / 4)` tokens from input text
   - Cost = `tokens / 1_000_000 * model.pricing.inputPerMillion`
   - Displayed in composer footer as: `~X tokens · ~Y تومان` (with a dollar SVG icon)
   - Only shown when there is text input and not streaming

2. **Wallet balance display + warning**:
   - Fetches balance from `/api/wallet` on mount (when authenticated)
   - If balance < 5,000 تومان: shows yellow warning pill with triangle icon linking to `/wallet`
   - If balance ≥ 5,000 تومان: shows inline balance with wallet icon
   - Uses `useEffect` + `fetch` — silent on error

3. **Prompt library button**:
   - Star icon + "پرامپت‌ها" link in composer footer
   - Links to `/prompts` (full page navigation, not a modal)

4. **Prompt query param handling**:
   - Reads `prompt` query param from URL
   - Pre-fills composer input when navigating from prompt library
   - Auto-focuses the textarea

### 2.2 `frontend/app/prompts/page.tsx` — NEW: Prompt Library Page

**Features:**

- **10 Persian prompt templates** across 5 categories:
  - کدنویسی (2): Python code writing, bug analysis
  - ترجمه (2): FA→EN, EN→FA translation
  - تحلیل (2): Text analysis, SWOT analysis
  - خلاقیت (2): Creative ideation, content rewriting
  - عمومی (2): Text summarization, concept explanation

- **Search** by title, description, or category
- **Category filter** pills (all 5 categories + "All")
- **Result count** display
- **Empty state** with clear filters button
- **Prompt cards** with:
  - Category-colored icon
  - Category badge
  - Title + description
  - "Use this prompt" CTA with arrow
  - Hover effects (elevation, accent border, glow)
- **Click → navigate** to `/chat?prompt=...` with pre-filled text

### 2.3 `frontend/app/globals.css` — Prompt Library + Cost Tracker Styles

Added ~300 lines of CSS:
- `.prompts-page`, `.prompts-header`, `.prompts-toolbar`, `.prompts-categories`
- `.prompt-card` with hover animations
- `.cost-estimate` for the inline token/cost preview
- `.wallet-warning` with pulse animation
- `.wallet-balance-inline` for the balance display
- `.prompt-lib-btn` for the composer button

---

## 3. Cost Calculation Formula

```
estimatedTokens = Math.max(1, Math.round(input.length / 4))
estimatedCost   = (estimatedTokens / 1_000_000) * model.pricing.inputPerMillion
```

- `inputPerMillion` is in تومان (IRT) per million tokens
- Result is displayed in تومان
- Approximation: ~4 characters per token (standard for Persian text)

---

## 4. Wallet Warning Threshold

- Warning triggers when balance < 5,000 تومان (as specified)
- Balance is fetched from `/api/wallet` endpoint
- Warning is a clickable yellow pill linking to `/wallet` for top-up
- Warning has a subtle pulse animation for attention

---

## 5. Prompt Library Seed Data

| # | Title | Category | Prompt Prefix |
|---|-------|----------|---------------|
| 1 | نوشتن کد پایتون | کدنویسی | یک تابع پایتون بنویس که |
| 2 | ترجمه فارسی به انگلیسی | ترجمه | متن زیر را به انگلیسی روان ترجمه کن... |
| 3 | تحلیل داده‌های متنی | تحلیل | متن زیر را تحلیل کن و نکات کلیدی... |
| 4 | ایده‌پردازی خلاقانه | خلاقیت | ۱۰ ایده خلاقانه و نوآورانه برای |
| 5 | خلاصه‌سازی متن | عمومی | متن زیر را به صورت خلاصه و مفید... |
| 6 | بررسی باگ و رفع اشکال | کدنویسی | کد زیر را بررسی کن، باگ‌های احتمالی... |
| 7 | بازنویسی محتوا | خلاقیت | متن زیر را با لحن جذاب‌تر و روان‌تر... |
| 8 | ترجمه انگلیسی به فارسی | ترجمه | متن انگلیسی زیر را به فارسی روان... |
| 9 | تحلیل SWOT | تحلیل | یک تحلیل SWOT کامل برای موضوع زیر... |
| 10 | توضیح مفاهیم پیچیده | عمومی | مفهوم زیر را به زبان ساده و با مثال... |

---

## 6. Build Verification

```
npm run build → ✅ Compiled successfully (19.9s)
Routes: /prompts (6.54 kB, static), /chat (9.79 kB, 270 kB first load)
All 43 pages generated successfully
No type errors, no lint failures
```

---

## 7. Design Decisions

- **No backend for prompt library**: Data is stored as a TypeScript constant array. No database, no API. This is intentional for MVP — can be migrated to backend later.
- **Full page navigation for prompt library**: Uses `<a href>` instead of `router.push` for simplicity and proper SEO. The `/prompts` page is statically generated.
- **Cost estimate is input-only**: Only estimates the cost of the user's input text, not the assistant's response (which is unpredictable). The actual cost is shown post-streaming via billing SSE events.
- **Wallet balance is fetched once on mount**: No polling. User can refresh by navigating to `/wallet`. This keeps the UI simple and avoids unnecessary API calls.
- **All inline SVGs use the same 24×24 viewBox pattern**: Consistent with the existing `Icon` component system.

---

## 8. Future Improvements

- Add prompt library CRUD (save custom prompts, edit, delete)
- Add "favorite" / "bookmark" for prompt templates
- Server-side prompt library with user-specific prompts
- More accurate token estimation (use tiktoken or similar)
- Real-time wallet balance via WebSocket
- Add "use this prompt" button as a modal instead of full page navigation