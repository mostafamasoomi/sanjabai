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

   `compression_enabled` never promises a token/cost saving figure (no
   measured number exists) and is explicit that only OLDER messages are
   summarised -- recent ones are sent untouched. That distinction is the one
   thing tests/lib/smartFeatures.test.ts checks for in the fa copy.
   ═══════════════════════════════════════════════════════════════════════════ */

const FA = {
  title: 'قابلیت‌های هوشمند',
  intro: 'این دو کلید روی نحوهٔ پردازش پیام‌های شما در گفتگو اثر می‌گذارند؛ هرکدام مستقل روشن یا خاموش می‌شود.',
  smartRouterLabel: 'انتخاب هوشمند مدل',
  smartRouterDesc:
    'وقتی روشن است، به‌جای همیشه استفاده از مدل پیش‌فرض شما، سنجاب‌بای برای هر پرسش مدل مناسب را خودش انتخاب می‌کند. این قابلیت با یک کلید سراسری در سمت مدیر کنترل می‌شود که هنوز فعال نشده؛ تا وقتی مدیر آن را فعال نکند، روشن‌کردن این کلید هیچ تغییری در رفتار گفتگوهای شما ایجاد نمی‌کند.',
  compressionLabel: 'فشرده‌سازی گفتگوهای طولانی',
  compressionDesc:
    'وقتی روشن است، در یک گفتگوی طولانی، بخش‌های قدیمی‌تر پیش از ارسال به مدل خلاصه می‌شوند تا گفتگو توکن کمتری مصرف کند. فقط پیام‌های قدیمی‌تر تحت تأثیر قرار می‌گیرند؛ پیام‌های اخیر بدون تغییر و کامل ارسال می‌شوند.',
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
    'When on, in a long conversation, older parts are summarised before being sent to the model, so the conversation uses fewer tokens. Only older messages are affected — recent ones are still sent in full, untouched.',
  saveError: 'Could not save the setting. Try again.',
}

export const smartFeaturesSectionStrings = dict(FA, EN)
