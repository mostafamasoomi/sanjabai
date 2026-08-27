import { dict } from '@/lib/i18n'

/* Every user-visible string on /combos lives here — the manager, the editor
   and the page shell all read from this one dictionary. `EN: typeof FA` is
   what makes a missing or misspelled key a compile error (see lib/i18n.ts).

   Numbers arrive already formatted by `fmt(lang)` at the call site, which is
   why every count/limit is a `(n: string) => string` and never a number: the
   digits have to follow the language, and this file does not know it. */

const FA = {
  /* ── Page shell ─────────────────────────────────────────────── */
  pageTitle: 'ترکیب‌های مدل من',
  pageSubtitle:
    'چند مدل را در یک فهرست مرتب کنار هم بگذارید تا درخواست‌هایتان به‌جای تکیه بر یک مدل، بین آن‌ها مدیریت شود.',
  authLoading: 'در حال بررسی حساب…',

  /* ── List states ────────────────────────────────────────────── */
  loading: 'در حال بارگذاری ترکیب‌ها…',
  loadError: 'ترکیب‌ها بارگذاری نشد.',
  retry: 'تلاش دوباره',
  emptyTitle: 'هنوز ترکیبی نساخته‌اید',
  emptyDesc:
    'ترکیب، فهرستی مرتب از چند مدل است. اگر مدل اول در دسترس نباشد یا خطا بدهد، به‌جای اینکه درخواست شما شکست بخورد، مدل بعدی همان ترکیب پاسخ می‌دهد. می‌توانید یک مدل سریع و یک مدل دقیق‌تر را کنار هم بگذارید و انتخاب بین‌شان را به ترکیب بسپارید.',
  emptyCta: 'ساخت اولین ترکیب',

  /* ── List actions ───────────────────────────────────────────── */
  newCombo: 'ترکیب جدید',
  comboCount: (used: string, max: string) => `${used} از ${max} ترکیب`,
  comboLimitReached: (max: string) =>
    `به سقف ${max} ترکیب رسیده‌اید. برای ساختن ترکیب تازه، یکی از ترکیب‌های موجود را حذف کنید.`,
  edit: 'ویرایش',
  editAria: (name: string) => `ویرایش ترکیب ${name}`,
  remove: 'حذف',
  removeAria: (name: string) => `حذف ترکیب ${name}`,
  deleteConfirm: (name: string) => `ترکیب «${name}» حذف شود؟ این کار برگشت‌پذیر نیست.`,
  deletedToast: 'ترکیب حذف شد',
  createdToast: 'ترکیب ساخته شد',
  updatedToast: 'ترکیب به‌روزرسانی شد',
  connectionError: 'ارتباط با سرور برقرار نشد.',
  genericError: 'انجام نشد. دوباره تلاش کنید.',

  /* ── Enabled / disabled ─────────────────────────────────────── */
  enabled: 'فعال',
  disabled: 'غیرفعال',
  toggleAria: (name: string) => `فعال یا غیرفعال کردن ترکیب ${name}`,

  /* ── Policies, explained in plain Persian ───────────────────── */
  policyLabel: 'سیاست انتخاب مدل',
  policySequential: 'ترتیبی',
  policySequentialDesc:
    'مدل‌ها دقیقاً به همان ترتیبی که چیده‌اید امتحان می‌شوند و اولین مدلِ سالم پاسخ می‌دهد.',
  policyRoundRobin: 'چرخشی',
  policyRoundRobinDesc:
    'درخواست‌ها به‌نوبت بین مدل‌های ترکیب می‌چرخند؛ هر درخواست به مدل بعدی می‌رود.',

  /* ── Item list ──────────────────────────────────────────────── */
  modelsLabel: 'مدل‌های ترکیب',
  modelsCount: (n: string) => `${n} مدل`,
  itemsCount: (used: string, max: string) => `${used} از ${max} مدل`,
  itemsRangeHint: (min: string, max: string) => `هر ترکیب باید بین ${min} تا ${max} مدل داشته باشد.`,
  itemsMaxReached: (max: string) =>
    `به سقف ${max} مدل در یک ترکیب رسیده‌اید. برای افزودن مدل تازه، یکی را حذف کنید.`,
  itemsMinNotMet: (min: string) => `دست‌کم ${min} مدل انتخاب کنید.`,
  moveUp: 'انتقال به بالا',
  moveDown: 'انتقال به پایین',
  removeItem: (name: string) => `حذف ${name} از ترکیب`,
  unavailableModel: 'این مدل دیگر در فهرست ارائه نیست',

  /* ── Editor ─────────────────────────────────────────────────── */
  createTitle: 'ترکیب جدید',
  editTitle: 'ویرایش ترکیب',
  closeAria: 'بستن',
  nameLabel: 'نام ترکیب',
  namePlaceholder: 'مثلاً: پاسخ سریع',
  nameHint: (max: string) => `بین ۱ تا ${max} نویسه، و برای هر کاربر یکتا.`,
  enabledLabel: 'ترکیب فعال باشد',
  enabledHint: 'ترکیب غیرفعال ذخیره می‌ماند ولی استفاده نمی‌شود.',
  addModel: 'افزودن مدل',
  cancel: 'انصراف',
  save: 'ذخیره',
  saving: 'در حال ذخیره…',

  /* ── Model picker inside the editor ─────────────────────────── */
  pickerTitle: 'انتخاب مدل',
  searchPlaceholder: 'جستجوی مدل…',
  catalogLoading: 'در حال بارگذاری مدل‌ها…',
  catalogError: 'فهرست مدل‌ها بارگذاری نشد.',
  noModelFound: 'مدلی با این جستجو پیدا نشد.',
  allAdded: 'همهٔ مدل‌های موجود را اضافه کرده‌اید.',
  alreadyAdded: 'اضافه شده',
}

const EN: typeof FA = {
  pageTitle: 'My model combos',
  pageSubtitle:
    'Put several models into one ordered list so your requests are handled across them instead of relying on a single model.',
  authLoading: 'Checking your account…',

  loading: 'Loading combos…',
  loadError: 'Could not load your combos.',
  retry: 'Try again',
  emptyTitle: 'You have no combos yet',
  emptyDesc:
    'A combo is an ordered list of models. If the first one is unavailable or errors out, the next model in the same combo answers instead of your request failing. Pair a fast model with a more careful one and let the combo choose.',
  emptyCta: 'Create your first combo',

  newCombo: 'New combo',
  comboCount: (used, max) => `${used} of ${max} combos`,
  comboLimitReached: (max) =>
    `You have reached the limit of ${max} combos. Delete one to make room for a new combo.`,
  edit: 'Edit',
  editAria: (name) => `Edit combo ${name}`,
  remove: 'Delete',
  removeAria: (name) => `Delete combo ${name}`,
  deleteConfirm: (name) => `Delete the combo "${name}"? This cannot be undone.`,
  deletedToast: 'Combo deleted',
  createdToast: 'Combo created',
  updatedToast: 'Combo updated',
  connectionError: 'Could not reach the server.',
  genericError: 'That did not go through. Please try again.',

  enabled: 'Enabled',
  disabled: 'Disabled',
  toggleAria: (name) => `Enable or disable combo ${name}`,

  policyLabel: 'Model selection policy',
  policySequential: 'Sequential',
  policySequentialDesc:
    'Models are tried in exactly the order you arranged them, and the first healthy one answers.',
  policyRoundRobin: 'Round robin',
  policyRoundRobinDesc:
    'Requests rotate between the models in the combo; each request goes to the next one.',

  modelsLabel: 'Models in this combo',
  modelsCount: (n) => `${n} models`,
  itemsCount: (used, max) => `${used} of ${max} models`,
  itemsRangeHint: (min, max) => `A combo must contain between ${min} and ${max} models.`,
  itemsMaxReached: (max) =>
    `You have reached the limit of ${max} models in one combo. Remove one to add another.`,
  itemsMinNotMet: (min) => `Pick at least ${min} models.`,
  moveUp: 'Move up',
  moveDown: 'Move down',
  removeItem: (name) => `Remove ${name} from the combo`,
  unavailableModel: 'This model is no longer offered',

  createTitle: 'New combo',
  editTitle: 'Edit combo',
  closeAria: 'Close',
  nameLabel: 'Combo name',
  namePlaceholder: 'e.g. Fast answers',
  nameHint: (max) => `Between 1 and ${max} characters, unique to your account.`,
  enabledLabel: 'Keep this combo enabled',
  enabledHint: 'A disabled combo is kept but never used.',
  addModel: 'Add a model',
  cancel: 'Cancel',
  save: 'Save',
  saving: 'Saving…',

  pickerTitle: 'Pick a model',
  searchPlaceholder: 'Search models…',
  catalogLoading: 'Loading models…',
  catalogError: 'Could not load the model list.',
  noModelFound: 'No model matches that search.',
  allAdded: 'You have already added every available model.',
  alreadyAdded: 'Added',
}

export const comboStrings = dict(FA, EN)
