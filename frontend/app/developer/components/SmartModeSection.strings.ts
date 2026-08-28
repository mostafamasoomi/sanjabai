import { dict } from '@/lib/i18n'

const FA = {
  title: 'حالت هوشمند برای مصرف‌کنندگان API',
  intro:
    'انتخاب مدل را می‌توانید به سنجاب بسپارید. این قابلیت روی endpoint اختصاصی خودش کار می‌کند و '
    + 'دقیقاً با همان کلید API بقیهٔ مسیرها در دسترس است — نیازی به احراز هویت جداگانه نیست.',
  requestHeaderTitle: 'هدر درخواست',
  requestHeaderDesc:
    'اگر این هدر را نفرستید، حالت قاعده‌محور اجرا می‌شود. مقدار نامعتبر هرگز خطا برنمی‌گرداند و '
    + 'به همان حالت قاعده‌محور برمی‌گردد؛ یعنی یک هدر ناخواستهٔ پراکسی نمی‌تواند سرویس شما را از کار بیندازد.',
  modesTitle: 'مقدارهای مجاز',
  modeAuto: 'انتخاب قاعده‌محور بر پایهٔ دستهٔ درخواست و موجودی کیف پول. پیش‌فرض.',
  modeRouter:
    'انتخاب با یک مدل سبک. یک فراخوان اضافه به مدل دارد و بنابراین هزینهٔ اضافه دارد؛ '
    + 'به همین دلیل فقط با درخواست صریح شما اجرا می‌شود و هرگز روی مسیر پیش‌فرض نمی‌آید.',
  modeCombo:
    'انتخاب از میان ترکیب مدلی که خودتان ساخته‌اید. شناسهٔ ترکیب را از فهرست ترکیب‌های حساب خود بگیرید.',
  responseTitle: 'هدرهای پاسخ — مرجع اینکه واقعاً چه چیزی اجرا شد',
  responseDesc:
    'مقداری که در هدر پاسخ می‌آید همان چیزی است که واقعاً اجرا شد، نه چیزی که درخواست کرده بودید. '
    + 'اگر حالت درخواستی برای حساب شما در دسترس نباشد یا ترکیب انتخابی غیرفعال شده باشد، درخواست '
    + 'بی‌صدا به حالت قاعده‌محور برمی‌گردد و همین را گزارش می‌کند. برای فهمیدن اینکه چه چیزی اجرا شد، '
    + 'به هدر پاسخ اعتماد کنید نه به هدر درخواست خودتان.',
  respMode: 'حالتی که واقعاً اجرا شد.',
  respModel: 'برچسب عمومی مدلی که انتخاب شد.',
  forceTitle: 'کنارگذاشتن انتخاب خودکار',
  forceDesc:
    'اگر خودتان مدل را می‌دانید، این هدر انتخاب خودکار را کنار می‌گذارد و بر هدر حالت هوشمند اولویت دارد.',
}

const EN: typeof FA = {
  title: 'Smart mode for API consumers',
  intro:
    'You can hand model selection to Sanjabai. It lives on its own endpoint and is reachable with '
    + 'exactly the same API key as every other route — there is no separate authentication.',
  requestHeaderTitle: 'Request header',
  requestHeaderDesc:
    'Omit the header and the rule-based selector runs. An invalid value never returns an error; it '
    + 'degrades to the same rule-based selector, so a stray proxy header cannot take your integration down.',
  modesTitle: 'Accepted values',
  modeAuto: 'Rule-based selection from the request category and the wallet balance. The default.',
  modeRouter:
    'Selection by a small model. It costs one extra model call, so it runs only when you ask for it '
    + 'explicitly and never on the default path.',
  modeCombo:
    'Selection from a model combo you built yourself. Take the combo id from your account’s combo list.',
  responseTitle: 'Response headers — the authority on what actually ran',
  responseDesc:
    'The response header reports what actually ran, not what you asked for. If the requested mode is '
    + 'not available to your account, or the chosen combo has been disabled, the request silently falls '
    + 'back to rule-based selection and says so. Trust the response header, not your own request header.',
  respMode: 'The mode that actually ran.',
  respModel: 'The public label of the model that was chosen.',
  forceTitle: 'Bypassing automatic selection',
  forceDesc:
    'If you already know the model, this header bypasses automatic selection and outranks the smart-mode header.',
}

export const smartModeSectionStrings = dict(FA, EN)
