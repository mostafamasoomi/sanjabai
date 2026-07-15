# Multiai Frontend — UX/UI Review Report

**Date:** July 15, 2026  
**URL:** http://127.0.0.1:3003  
**Reviewer:** Hermes Agent (Browser-based automated review)  
**Test Account:** demo@multiai.com  
**Viewport:** 1280×577 (desktop)  
**Language:** Persian (Farsi) — RTL layout  

---

## Executive Summary

The Multiai frontend is a fully functional Persian-language AI platform with RTL support. The application features a consistent sidebar navigation, dark/light mode toggle, and a comprehensive set of 20+ pages. The overall design is clean and functional. Key strengths include consistent navigation, comprehensive feature coverage, and good Persian localization. Areas for improvement include sidebar overlap issues, some empty states needing better onboarding, and minor UX polish.

**Overall Score: 7.5/10**

---

## Page-by-Page Review

### 1. Landing Page (`/`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Hero Section:** Clear headline "هوش مصنوعی برای همه، به زبان فارسی" (AI for everyone, in Persian) with two CTAs: "شروع رایگان" (Start Free) and "مشاهده مدلها" (View Models)
- **Stats Bar:** Shows "+۵۰ مدل هوش مصنوعی", "+۱۰K کاربر فعال", "۹۹.۹٪ آپتایم", "< ۲ دقیقه شروع استفاده"
- **Features Section:** "چرا Multiai؟" with 6 feature cards in a 3×2 grid (همه مدلها، مدیریت هوشمند، قیمتگذاری شفاف، امن و مستقل، API آماده، فارسی واقعی)
- **How-to Section:** 4-step guide (ثبتنام → شارژ → چت → مدیریت)
- **FAQ Section:** 5 accordion items with common questions
- **CTA Section:** "آماده شروع هستید؟" with action button
- **Footer:** Basic footer present

**Issues:**
- ⚠️ Sidebar navigation appears to extend beyond viewport (x=1033-1280), suggesting the sidebar is positioned at the right edge and may overlap content on smaller screens
- ⚠️ The sidebar has two instances (one at x=1033, another at x=1280+), indicating a mobile/desktop dual sidebar pattern
- ✅ RTL layout appears correct
- ✅ Clean visual hierarchy
- ✅ Good use of whitespace

---

### 2. Login Page (`/login`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Form Layout:** Centered form with heading "ورود به حساب" (Login to Account)
- **Fields:** Email field (placeholder: "you@example.com") and Password field (placeholder: "حداقل ۸ کاراکتر" — min 8 characters)
- **Button:** "ورود" (Login) button
- **Links:** "رمز عبور را فراموش کردهاید؟" (Forgot password?) and "ثبتنام" (Signup) link
- **Login Flow:** Successfully redirected to `/chat` after login with demo credentials

**Issues:**
- ✅ Form validation works (email + password required)
- ✅ Clean, minimal design
- ✅ Proper RTL alignment
- ⚠️ No "Remember me" checkbox
- ⚠️ No social login options (Google, GitHub, etc.)
- ⚠️ No loading state indicator during login

---

### 3. Signup Page (`/signup`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Form Layout:** Centered form with heading "ثبتنام در Multiai"
- **Subtitle:** "دسترسی به همه مدلهای هوش مصنوعی" (Access to all AI models)
- **Fields:** Email and Password fields (same as login)
- **Button:** "ثبتنام" (Signup)
- **Link:** "قبلاً ثبتنام کردهاید؟ ورود" (Already registered? Login)
- **Trust Signals:** "رمزنگاری SSL", "بدون نیاز به VPN", "شارژ ریالی"

**Issues:**
- ✅ Trust signals are good for Iranian users
- ⚠️ No password confirmation field
- ⚠️ No terms of service checkbox
- ⚠️ No email verification step mentioned

---

### 4. Models Page (`/models`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "مدلهای هوش مصنوعی" with subtitle
- **Search:** Search input for filtering models
- **Filter Tabs:** "همه" (All), "bynara2", "openrouter" — filters by provider
- **Model Count:** "13 مدل" displayed
- **Model Cards:** 13 models displayed with:
  - Model name (e.g., gpt-5.6-luna, kimi-k2.7-code-free, mimo-v2.5, etc.)
  - Provider name (bynara2 or openrouter)
  - Availability status ("در دسترس")
  - Description
  - Token limit (e.g., "1,000,000 token")
  - Capability badges (chat, vision, reasoning, function_calling, code-generation)
  - "شروع چت با [model]" action link

**Models Listed:**
| Model | Provider | Tokens | Capabilities |
|-------|----------|--------|--------------|
| gpt-5.6-luna | bynara2 | 1,000,000 | chat, vision |
| kimi-k2.7-code-free | bynara2 | 262,000 | chat, vision, reasoning |
| mimo-v2.5 | bynara2 | 1,000,000 | chat, vision, reasoning |
| mimo-v2.5-pro | bynara2 | 1,000,000 | chat, reasoning |
| mimo-v2.5-pro-ultraspeed | bynara2 | 1,000,000 | chat, reasoning |
| mistral-medium-3.5 | bynara2 | 128,000 | chat, reasoning, function_calling |
| tencent-hy3 | bynara2 | 1,000,000 | chat, reasoning |
| Gemma 4 31B | openrouter | 262,144 | chat |
| Hermes 3 405B | openrouter | 131,072 | chat |
| Llama 3.3 70B | openrouter | 131,072 | chat |
| Nemotron 3 Ultra 550B | openrouter | 1,000,000 | chat |
| Qwen3 Coder 480B | openrouter | 1,048,576 | chat, code-generation |
| Tencent Hy3 | openrouter | 262,144 | chat |

**Issues:**
- ✅ Good model documentation
- ✅ Clear capability badges
- ⚠️ Some model descriptions are generic ("Hermes/Bynara model") — could be more descriptive
- ⚠️ No pricing information per model
- ⚠️ No sorting options (by name, tokens, capabilities)

---

### 5. Compare Page (`/compare`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "مقایسه مدلها" (Compare Models)
- **Subtitle:** "یک prompt به چند مدل ارسال کنید و پاسخها را مقایسه کنید"
- **Model Selection:** 13 model toggle buttons (all models available)
- **Input:** Prompt input field
- **Button:** "مقایسه" (Compare) — disabled until models selected and prompt entered

**Issues:**
- ✅ Good feature for model comparison
- ⚠️ No pre-selected models for quick comparison
- ⚠️ No guidance on how many models can be selected at once
- ⚠️ Compare button is disabled without clear feedback on why

---

### 6. Playground Page (`/playground`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "🎮 Playground"
- **Subtitle:** "مدلها را تست کنید و بهترین prompt را پیدا کنید"
- **Model Selector:** Dropdown with all 13 models
- **Parameters:**
  - Temperature slider (default: 0.7)
  - Max Tokens slider (default: 1024)
- **Preset Prompts:** 6 quick-start buttons:
  - 💡 خلاقانه (Creative)
  - 📝 محتوا (Content)
  - 💻 کد (Code)
  - 📊 تحلیل (Analysis)
  - 🌐 ترجمه (Translation)
  - 🎯 خلاصه (Summary)
- **System Prompt:** Optional text input for role/behavior definition
- **User Prompt:** Main prompt input
- **Execute Button:** "🚀 اجرا" (Run) — disabled until prompt entered

**Issues:**
- ✅ Excellent parameter controls
- ✅ Good preset prompts for quick testing
- ✅ System prompt support
- ⚠️ No token counter showing estimated usage
- ⚠️ No history of previous playground runs

---

### 7. Pricing Page (`/pricing`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "پلن مناسب خودت رو انتخاب کن" (Choose your plan)
- **Subscription Plans:**
  - **رایگان (Free):** 3M tokens/month, 100K daily limit
  - **(Base):** 5M tokens/month, 500K daily limit
  - **⭐ محبوبترین (Most Popular):** 20M tokens/month, 2M daily limit
  - **نامحدود (Unlimited):** Unlimited tokens
- **Credit Packages:**
  - بسته شروع (Starter): 50,000 تومان
  - بسته محبوب (Popular): 120,000 تومان (+20% bonus)
  - بسته مگا (Mega): 350,000 تومان (+40% bonus)
  - بسته ویژه (Special): 750,000 تومان (+50% bonus)
- **FAQ Section:** 4 accordion items about plans and pricing

**Issues:**
- ✅ Clear pricing tiers
- ✅ Good value proposition with bonus percentages
- ✅ FAQ addresses common concerns
- ⚠️ No prices shown for Base, Pro, Unlimited plans (missing actual prices)
- ⚠️ "خرید اشتراک" buttons without showing the cost
- ⚠️ No comparison table between plans

---

### 8. Chat Page (`/chat`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Layout:** Split layout with conversation sidebar and main chat area
- **Sidebar:**
  - "چت جدید" (New Chat) button
  - "هنوز مکالمهای ندارید" (No conversations yet) empty state
- **Main Area:**
  - Model selector dropdown (default: gpt-5.6-luna)
  - Smart Mode toggle (disabled by default)
  - Provider indicator ("openai")
  - Quick start suggestions:
    - کدنویسی (Coding)
    - ترجمه (Translation)
    - خلاصهسازی (Summarization)
    - تحلیل (Analysis)
  - Input area with:
    - File attachment button
    - Web search button
    - Message input (placeholder: "پیام خود را بنویسید...")
    - Send button (disabled until message typed)

**Issues:**
- ✅ Clean chat interface
- ✅ Good quick-start suggestions
- ✅ Smart Mode toggle is a nice feature
- ✅ File attachment and web search buttons present
- ⚠️ "کپی" (Copy) button visible in quick-start area — unclear what it copies
- ⚠️ No keyboard shortcut hints for send (Shift+Enter mentioned in placeholder)

---

### 9. Dashboard (`/dashboard`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Greeting:** "سلام، demo" with plan badge "رایگان" and "بروزرسانی" (Upgrade) button
- **Stats Cards:**
  - موجودی کیف پول: ۵۰۰٬۰۰۰ تومان
  - کل هزینه: ۰ تومان
  - تعداد مکالمات: ۰ مکالمه
  - کل توکنها: ۰ توکن
  - وضعیت اشتراک: رایگان (بدون اشتراک)
- **Recent Activity:** "هنوز تراکنشی ثبت نشده است" (No transactions yet)
- **Quick Access:** 5 action buttons:
  - شروع مکالمه (Start conversation)
  - کیف پول (Wallet)
  - مدلها (Models — 13 available)
  - خرید بسته اعتباری (Buy credit package)
  - تنظیمات صورتحساب (Billing settings)
- **Account Info:**
  - Email: demo@multiai.com
  - Status: غیرفعال (Inactive)
  - Member since: ۲۴ تیر ۱۴۰۵
- **Pay-as-you-go Section:**
  - Toggle: فعال (Active)
  - Cost limit: تعیین نشده (Not set)
  - Alert threshold: ۸۰٪

**Issues:**
- ✅ Comprehensive dashboard with good information architecture
- ✅ Quick access buttons are well-organized
- ✅ PAYG section is clear
- ⚠️ Account status shows "غیرفعال" (Inactive) — unclear if this is expected for demo account
- ⚠️ No usage charts or graphs
- ⚠️ No recent conversations list

---

### 10. Wallet Page (`/wallet`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "کیف پول" (Wallet)
- **Refresh Button:** "بروزرسانی"
- **Top-up Section:**
  - Quick amounts: 100K, 500K, 1M, 5M ریال
  - Custom amount input
  - "شارژ" (Charge) button
- **Credit Packages:** 4 packages with bonus percentages (same as pricing page)
- **Transaction History:**
  - Filter tabs: همه (All), واریز (Deposit), برداشت (Withdrawal)
  - Empty state: "تراکنشی ثبت نشده"
- **Payment History:**
  - Empty state: "پرداختی ثبت نشده"

**Issues:**
- ✅ Good top-up options with quick amounts
- ✅ Transaction filtering is useful
- ⚠️ Balance not prominently displayed at top
- ⚠️ No visual balance indicator (progress bar, gauge, etc.)

---

### 11. API Keys Page (`/api-keys`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "کلیدهای API" (API Keys)
- **Create Section:**
  - Key name input (default: "Default")
  - "ساخت کلید" (Create Key) button
- **Existing Keys:**
  - 1 key listed: "test-key" (غیرفعال/Inactive)
  - Key shown as masked: `sk-Y6WTIaNQv••••••••••••••••••••••••15`
  - Show/Copy buttons
  - Creation date: ۲۴ تیر ۱۴۰۵
- **Usage Guide:**
  - 1. Authentication (curl example)
  - 2. Chat request (JSON example)
  - 3. List models (curl example)

**Issues:**
- ✅ Good API documentation with examples
- ✅ Key masking for security
- ⚠️ No delete/revoke key option visible
- ⚠️ No key expiration settings
- ⚠️ No usage statistics per key

---

### 12. Search Page (`/search`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "جستجوی مکالمات" (Search Conversations)
- **Subtitle:** "آخرین مکالمات شما" (Your recent conversations)
- **Search Input:** "جستجو در عنوان و محتوای مکالمات..."
- **Empty State:** "هنوز مکالمهای ندارید" with "شروع مکالمه" button

**Issues:**
- ✅ Clean search interface
- ⚠️ No search filters (date, model, etc.)
- ⚠️ No search suggestions or autocomplete

---

### 13. Skills Page (`/skills`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "مارکتپلیس اسکیلها" (Skills Marketplace)
- **Subtitle:** "اسکیلهای آماده رو کشف کن و استفاده کن"
- **Create Button:** "ایجاد اسکیل جدید" (Create New Skill)
- **Search:** "جستجوی اسکیل..."
- **Sort Options:** محبوبترین (Most Popular), جدیدترین (Newest), بهترین امتیاز (Best Rated)
- **Category Filters:** همه (All), نوشتن (Writing), برنامهنویسی (Programming), تحلیل (Analysis), ترجمه (Translation), بازاریابی (Marketing), سایر (Other)
- **Empty State:** "اسکیلی یافت نشد" — "هنوز اسکیلی ایجاد نشده است"

**Issues:**
- ✅ Good marketplace structure with categories and sorting
- ✅ Clear empty state with CTA
- ⚠️ No pre-built skills to showcase
- ⚠️ No skill templates or examples

---

### 14. Assistants Page (`/assistants`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "دستیارها" (Assistants)
- **Subtitle:** "دستیارهای هوشمند خود را بسازید و مدیریت کنید"
- **Create Button:** "دستیار جدید" (New Assistant)
- **Filter Tabs:** همه (All), دستیارهای من (My Assistants), عمومی (Public)
- **Empty State:** "دستیاری یافت نشد"

**Issues:**
- ✅ Good assistant management structure
- ⚠️ No sample assistants to demonstrate functionality
- ⚠️ No assistant templates

---

### 15. Memory Page (`/memory`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "حافظه هوشمند" (Smart Memory)
- **Subtitle:** "اطلاعات و ترجیحات شما برای چتهای بهتر"
- **Search:** "جستجو در حافظه..."
- **Category Filters:** همه (All), ترجیحات (Preferences), پروژهها (Projects), مهارتها (Skills), شخصی (Personal), سایر (Other)
- **Add Button:** "افزودن حافظه" (Add Memory)
- **Auto-Memory Section:** Explains automatic memory extraction from conversations
- **Empty State:** "هنوز حافظهای ذخیره نشده"

**Issues:**
- ✅ Good memory management concept
- ✅ Auto-memory feature is well-explained
- ⚠️ No examples of what memories look like
- ⚠️ No memory size/limit information

---

### 16. Tasks Page (`/tasks`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "تسکهای زمانبندی شده" (Scheduled Tasks)
- **Subtitle:** "اجرای خودکار پرامپتها طبق زمانبندی"
- **Create Button:** "ایجاد تسک جدید"
- **Sample Task:** "Test" task visible:
  - Model: mimo-v2.5
  - Schedule: "هر روز ساعت ۹ صبح" (Every day at 9 AM)
  - Cron: `0 9 * * *`
  - Status: فعال (Active)
  - Output: داشبورد (Dashboard)
  - Runs: ۰ بار (0 times)
  - Actions: اجرا (Run), تاریخچه (History), ویرایش (Edit), حذف (Delete)

**Issues:**
- ✅ Good task scheduling interface
- ✅ Cron expression visible for advanced users
- ✅ Clear task management actions
- ⚠️ Only one task visible — could show more examples
- ⚠️ No task templates for common use cases

---

### 17. Developer Page (`/developer`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "پلتفرم توسعهدهندگان" (Developer Platform)
- **Subtitle:** "API سازگار با OpenAI برای ادغام در اپلیکیشنهای شما"
- **API Info:**
  - Endpoint: `https://multiai.ir/v1`
  - OpenAI-compatible format
- **Rate Limits Table:**
  | Plan | Requests | Tokens |
  |------|----------|--------|
  | رایگان | 100 | 10,000/day |
  | پایه | 1,000 | 100,000/day |
  | حرفهای | 10,000 | 1,000,000/day |
  | سازمانی | Unlimited | Unlimited |
- **API Keys Section:** Same as api-keys page
- **Code Examples:** Python, cURL, JavaScript tabs
- **Endpoint Documentation:**
  - POST /v1/chat/completions
  - GET /v1/models

**Issues:**
- ✅ Excellent developer documentation
- ✅ Multiple language examples
- ✅ Clear rate limit information
- ⚠️ No interactive API explorer/tester
- ⚠️ No webhook documentation
- ⚠️ No SDK/library links

---

### 18. Profile Page (`/profile`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **User Info:**
  - Avatar: "D" (initial)
  - Email: demo@multiai.com
  - Member since: ۱۴۰۵ تیر
  - Balance: ۵۰۰٬۰۰۰ تومان
  - Today's usage: —
- **Settings:**
  - Email notifications: ON
  - Telegram notifications: OFF
  - Dark mode: ON
- **Change Password:** Current + New + Confirm fields
- **Telegram Connection:** Telegram ID input with "اتصال" (Connect) button
- **Referral Section:**
  - Code: demo2026
  - Link: http://127.0.0.1:3003/signup?ref=demo2026
- **Danger Zone:**
  - "حذف حساب (بهزودی)" — Delete account (coming soon, disabled)

**Issues:**
- ✅ Comprehensive profile settings
- ✅ Telegram integration is a nice feature for Iranian users
- ✅ Referral system integrated
- ⚠️ No profile picture upload
- ⚠️ No display name field
- ⚠️ Delete account is disabled (coming soon)

---

### 19. Referral Page (`/referral`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "دعوت از دوستان" (Invite Friends)
- **Subtitle:** "دوستان خود را دعوت کنید و پاداش بگیرید"
- **Referral Code:** demo2026 with copy button
- **How It Works:** 3-step process:
  1. Share referral link
  2. Friend signs up and makes first charge
  3. Both receive credit reward

**Issues:**
- ✅ Clear referral process
- ✅ Simple 3-step explanation
- ⚠️ No referral statistics (how many invited, rewards earned)
- ⚠️ No share buttons for social media
- ⚠️ No reward amount specified

---

### 20. Admin Page (`/admin`)
**Status:** ✅ Working  
**Console Errors:** None  

**Findings:**
- **Heading:** "پنل مدیریت" (Admin Panel)
- **Subtitle:** "Multiai Admin Dashboard"
- **Auth:** Admin token input with "ورود" (Login) button (disabled until token entered)

**Issues:**
- ✅ Proper admin authentication required
- ⚠️ No indication of what admin features are available
- ⚠️ No documentation link for admin access

---

## Global Issues & Observations

### Navigation & Layout
1. **Sidebar Behavior:** The sidebar appears to have a dual-instance pattern (one visible, one off-screen for mobile). The desktop sidebar extends to x=1033-1280, which may cause content overlap on screens smaller than 1280px.
2. **RTL Support:** Generally good RTL support throughout the application. Text alignment, form layouts, and navigation all follow RTL conventions.
3. **Consistent Navigation:** All pages share the same sidebar navigation structure with sections: اصلی (Main), ابزارها (Tools), حساب (Account).
4. **User Menu:** "D demo@multiai.com" button visible in sidebar when logged in, with "خروج" (Logout) option.

### Design & Visual
5. **Color Scheme:** Dark mode appears to be the default. Light mode toggle is available (☀️ button).
6. **Typography:** Persian text appears well-rendered with appropriate font sizes.
7. **Spacing:** Generally good whitespace and padding throughout.
8. **Icons:** Emoji icons used (🎮, 🧠, ⚙️, 📋, 💡, 📝, 💻, 📊, 🌐, 🎯, 🚀) — consistent but could be more professional with SVG icons.

### Functionality
9. **Search (⌘K):** Global search button visible in header — good UX pattern.
10. **Empty States:** Most pages have appropriate empty states with CTAs, but some could be more engaging.
11. **Loading States:** No loading indicators observed during page transitions.
12. **Error Handling:** No console errors detected across all 20 pages — good stability.

### Localization
13. **Persian Content:** All UI text is in Persian. Some technical terms remain in English (API, Playground, Smart Mode, etc.) which is appropriate for the target audience.
14. **Mixed Language:** Some pages mix Persian and English (e.g., "Playground", "Smart Mode", "API") — this is acceptable for a tech platform.
15. **Date Format:** Persian date format used (e.g., "۲۴ تیر ۱۴۰۵") — good localization.

### Responsive Design
16. **Viewport:** Tested at 1280px width. Mobile responsiveness could not be fully evaluated but the dual-sidebar pattern suggests mobile support exists.
17. **Sidebar Toggle:** "بستن سایدبار" (Close sidebar) button present on chat page — good mobile support.

---

## Recommendations

### High Priority
1. **Fix sidebar overlap** on screens between 1024-1280px width
2. **Add loading states** for page transitions and form submissions
3. **Add pricing display** to subscription plan buttons on pricing page
4. **Add password confirmation** field on signup page

### Medium Priority
5. **Add profile picture upload** functionality
6. **Add usage charts/graphs** to dashboard
7. **Add referral statistics** to referral page
8. **Add social share buttons** for referral links
9. **Improve model descriptions** — replace generic "Hermes/Bynara model" with actual descriptions
10. **Add terms of service** checkbox on signup

### Low Priority
11. **Add interactive API explorer** to developer page
12. **Add task templates** for common scheduled tasks
13. **Add skill templates** to skills marketplace
14. **Add search filters** (date, model, etc.) to search page
15. **Replace emoji icons** with professional SVG icons
16. **Add keyboard shortcuts** documentation
17. **Add "Remember me"** option on login
18. **Add social login** options (Google, GitHub)

---

## Technical Notes

- **Framework:** Likely Next.js/React (based on page structure and routing)
- **API:** OpenAI-compatible API at https://multiai.ir/v1
- **Authentication:** JWT-based (inferred from login flow)
- **State Management:** Client-side state with server synchronization
- **Console Errors:** None detected across all 20 pages
- **Performance:** Page transitions appear fast with no noticeable loading delays

---

## Screenshots

Screenshots were captured for each page during the review. The application demonstrates a consistent, professional design with good Persian localization and RTL support.

---

*Report generated by Hermes Agent on July 15, 2026*
