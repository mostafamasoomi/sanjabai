import { dict } from '@/lib/i18n'

/* ═══════════════════════════════════════════════════════════════════════════
   P-UI-TOGGLES — copy for the two smart-feature switches.

   Both descriptions say what the setting DOES, matching the standard set by
   AUTONOMY_LEVELS in ../types.ts, not vague "smart"/"advanced" language.

   `smart_router_enabled` is deliberately honest that it is gated behind a
   site-wide admin flag that is off right now: turning this switch on saves
   the user's preference but does not change their conversations until an
   admin enables the flag. No "unavailable" banner is built for this (no
   endpoint reports the flag) -- the sentence lives in the normal copy
   instead, so the claim is correct without needing extra UI.

   `compression_enabled`'s copy was rewritten after the feature was measured
   on the real headroom library in the live container (2026-08-28):

     assistant prose (Persian)   0%   -- protected, never compressed
     assistant code block        0%   -- protected, never compressed
     user messages               0%   -- protected BY DESIGN by headroom
     assistant JSON            -47%
     assistant logs            -97%

   The first draft said older parts "are summarised so the conversation uses
   fewer tokens". True in principle, false for almost every real Persian
   conversation -- a promise the product does not keep. The copy now names
   what actually shrinks (bulk JSON and logs in assistant replies), names what
   is never touched, and says outright that a normal chat will feel no
   difference. It still promises no percentage: none is measured for real
   traffic. See middleware/compression.py's module docstring for the raw
   numbers.
   ═══════════════════════════════════════════════════════════════════════════ */

const FA = {
  title: 'قابلیت‌های هوشمند',
  intro: 'این دو کلید روی نحوهٔ پردازش پیام‌های شما در گفتگو اثر می‌گذارند؛ هرکدام مستقل روشن یا خاموش می‌شود.',
  smartRouterLabel: 'انتخاب هوشمند مدل',
  smartRouterDesc:
    'وقتی روشن است، به‌جای همیشه استفاده از مدل پیش‌فرض شما، سنجاب‌بای برای هر پرسش مدل مناسب را خودش انتخاب می‌کند. این قابلیت با یک کلید سراسری در سمت مدیر کنترل می‌شود که هنوز فعال نشده؛ تا وقتی مدیر آن را فعال نکند، روشن‌کردن این کلید هیچ تغییری در رفتار گفتگوهای شما ایجاد نمی‌کند.',
  compressionLabel: 'فشرده‌سازی گفتگوهای طولانی',
  compressionDesc:
    'وقتی روشن است، در گفتگوهای طولانی بخش‌های قدیمی‌ترِ پاسخ‌های دستیار که دادهٔ حجیم دارند — مثل JSON یا لاگ — پیش از ارسال دوباره به مدل خلاصه می‌شوند. متن معمولی، کد، و پیام‌های خودتان هرگز دست نمی‌خورند و کامل ارسال می‌شوند، پس در گفتگوی معمولی احتمالاً هیچ تفاوتی حس نمی‌کنید. اگر روی خروجی‌های حجیم کار می‌کنید به کارتان می‌آید.',
  saveError: 'ذخیرهٔ تنظیم انجام نشد. دوباره تلاش کنید.',
}

const EN: typeof FA = {
  title: 'Smart Features',
  intro: 'These two switches affect how your messages are processed in a conversation; each can be turned on or off independently.',
  smartRouterLabel: 'Smart Model Selection',
  smartRouterDesc:
    'When on, instead of always using your default model, Sanjabai picks a suitable model for each question itself. This is controlled by a site-wide switch on the admin side that is not enabled yet; until an admin turns it on, switching this on makes no difference to your conversations.',
  compressionLabel: 'Compress Long Conversations',
  compressionDesc:
    'When on, older assistant replies carrying bulk data — JSON or logs — are summarised before being sent to the model again. Ordinary prose, code, and your own messages are never touched and are always sent in full, so in a normal conversation you will probably notice no difference. It helps if you work with large outputs.',
  saveError: 'Could not save the setting. Try again.',
}

export const smartFeaturesSectionStrings = dict(FA, EN)
