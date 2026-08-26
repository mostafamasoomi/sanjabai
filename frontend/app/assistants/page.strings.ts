import { dict } from '@/lib/i18n'

const FA = {
  toastFetchError: 'خطا در دریافت دستیارها',
  toastServerError: 'خطا در ارتباط با سرور',
  publicBadge: 'عمومی',
  privateBadge: 'خصوصی',
  pageTitle: 'دستیارها',
  pageSubtitle: 'دستیارهای هوشمند خود را بسازید و مدیریت کنید',
  newAssistant: 'دستیار جدید',
  filterAll: 'همه',
  filterMine: 'دستیارهای من',
  filterPublic: 'عمومی',
  emptyTitle: 'دستیاری یافت نشد',
  emptyMineDesc: 'هنوز دستیاری نساخته‌اید. یک دستیار جدید بسازید!',
  emptyOtherDesc: 'دستیاری در این دسته‌بندی وجود ندارد.',
  createAction: 'ساخت دستیار',
}

const EN: typeof FA = {
  toastFetchError: 'Failed to load assistants',
  toastServerError: 'Server connection error',
  publicBadge: 'Public',
  privateBadge: 'Private',
  pageTitle: 'Assistants',
  pageSubtitle: 'Build and manage your smart assistants',
  newAssistant: 'New assistant',
  filterAll: 'All',
  filterMine: 'My assistants',
  filterPublic: 'Public',
  emptyTitle: 'No assistants found',
  emptyMineDesc: "You haven't created any assistants yet. Create one!",
  emptyOtherDesc: 'There are no assistants in this category.',
  createAction: 'Create assistant',
}

export const assistantsPageStrings = dict(FA, EN)
