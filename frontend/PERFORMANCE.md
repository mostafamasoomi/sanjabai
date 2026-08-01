# Sanjhubai Frontend — Performance Notes (Phase 10)

This document records the performance work done in Phase 10 and how to verify/extend it.

## 1. Self-hosted Vazirmatn font

**Before:** `app/layout.tsx` loaded Vazirmatn from Google Fonts via a render-blocking
`<link href="https://fonts.googleapis.com/...">`. This added a 3rd-party DNS + TLS + CSS
round-trip on every page load and broke in regions/networks that block Google.

**After:**
- The two weights are downloaded once into `public/fonts/`:
  - `public/fonts/Vazirmatn-Regular.woff2` (~50 KB, woff2)
  - `public/fonts/Vazirmatn-Bold.woff2` (~51 KB, woff2)
- `app/globals.css` declares them with `@font-face { font-family:'Vazirmatn'; font-display:swap }`.
  `font-display:swap` prevents invisible text (FOIT) while the woff2 streams in.
- The Google Fonts `<link>` was removed from `app/layout.tsx`.
- RTL is **preserved**: `<html dir="rtl">` is set in the root layout (server-rendered) and the
  Vazirmatn woff2 covers the Persian/Arabic script. No layout/CSS change to text direction.

**Effect:** Removes a blocking cross-origin stylesheet request; fonts now load same-origin
(~100 KB total, gzip/br further reduced by the static server). Works fully offline.

## 2. Dynamic imports for heavy routes

`/admin` and `/playground` now load through `next/dynamic` with `ssr:false`:
- `app/admin/page.tsx` → dynamically imports `app/admin/AdminPanel.tsx`
- `app/playground/page.tsx` → dynamically imports `app/playground/Playground.tsx`

Both are interactive, client-only tools (admin is auth-gated; playground needs auth + live
catalog + streaming), so server rendering them adds no SEO/SSR value while pulling their logic
into the server bundle. `ssr:false` defers them to the client. A lightweight spinner is shown
while the chunk loads. RTL is unaffected (root layout still emits `dir="rtl"` server-side).

> Note: App Router already code-splits every route segment, so `/admin` and `/playground` were
> already separate chunks and never bloated the home/shared bundle. The `next/dynamic` wrapper
> additionally removes them from server rendering and keeps their code client-only.

### Charts / recharts
**Not used.** `recharts` (and any chart library) is absent from `package.json` and there are no
`<ResponsiveContainer>` / `BarChart` / `LineChart` / `PieChart` usages in the codebase
(verified via grep). There is therefore nothing to lazy-load for charts. If charts are added
later, wrap them with `next/dynamic({ ssr:false })` (they rely on `window`/DOM measurement).

## 3. Bundle analyzer

- Added `@next/bundle-analyzer` as a dev dependency.
- `next.config.js` enables it **only** when `ANALYZE=true`, so the default `npm run build`
  never requires it to be installed (guarded with try/catch + warning).
- New script: `npm run analyze` — builds and opens an interactive treemap of every JS chunk.

```bash
npm run analyze
```

## 4. Verifying a build

```bash
cd frontend
npm run build      # default build (analyzer off)
npm run analyze    # build + open bundle treemap
```

The `next build` output prints `First Load JS` per route; compare `/`, `/admin`, `/playground`
before/after to quantify the effect of the dynamic wrappers and font change.
