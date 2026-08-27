import { dict } from '@/lib/i18n'

const FA = {
  loadError: 'خطا در دریافت اطلاعات — لطفاً دوباره تلاش کنید',
  empty: 'چیزی ثبت نشده',
  // ── ledger ──
  colId: 'شناسه',
  colAmount: 'مبلغ',
  colBalanceAfter: 'مانده پس از تراکنش',
  colReason: 'شرح',
  colDate: 'تاریخ',
  txCount: (n: string) => `${n} تراکنش`,
  // ── payments ──
  colStatus: 'وضعیت',
  colType: 'نوع',
  colRefCode: 'کد مرجع',
  paymentStatus: { verified: 'تایید شده', pending: 'در انتظار', failed: 'ناموفق' } as Record<string, string>,
  noPayments: 'هیچ پرداختی ثبت نشده',
  // ── usage ──
  usageByModelTitle: 'مصرف بر اساس مدل',
  colModel: 'مدل',
  colCalls: 'درخواست',
  colInput: 'ورودی',
  colOutput: 'خروجی',
  colCost: 'هزینه',
  colLastUsed: 'آخرین استفاده',
  dailyUsageTitle: 'مصرف توکن ۳۰ روز اخیر',
  chartAriaLabel: 'مصرف توکن روزانه',
  chartTooltip: (date: string, tokens: string) => `${date}: ${tokens} توکن`,
  // ── conversations ──
  colTitle: 'عنوان',
  colMessages: 'پیام‌ها',
  colLastUpdated: 'آخرین بروزرسانی',
  convCount: (n: string) => `${n} گفتگو`,
}

const EN: typeof FA = {
  loadError: 'Error loading data — please try again',
  empty: 'Nothing recorded',
  colId: 'ID',
  colAmount: 'Amount',
  colBalanceAfter: 'Balance after',
  colReason: 'Reason',
  colDate: 'Date',
  txCount: (n) => `${n} transactions`,
  colStatus: 'Status',
  colType: 'Type',
  colRefCode: 'Reference code',
  paymentStatus: { verified: 'Verified', pending: 'Pending', failed: 'Failed' },
  noPayments: 'No payments recorded',
  usageByModelTitle: 'Usage by model',
  colModel: 'Model',
  colCalls: 'Requests',
  colInput: 'Input',
  colOutput: 'Output',
  colCost: 'Cost',
  colLastUsed: 'Last used',
  dailyUsageTitle: 'Token usage, last 30 days',
  chartAriaLabel: 'Daily token usage',
  chartTooltip: (date, tokens) => `${date}: ${tokens} tokens`,
  colTitle: 'Title',
  colMessages: 'Messages',
  colLastUpdated: 'Last updated',
  convCount: (n) => `${n} conversations`,
}

export const userDetailTabsStrings = dict(FA, EN)
