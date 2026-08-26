import { dict } from '@/lib/i18n'

const FA = {
  heading: 'صفحه مورد نظر پیدا نشد',
  body: 'متأسفانه صفحه‌ای که دنبالش هستید وجود ندارد یا منتقل شده است.',
  home: 'بازگشت به خانه',
  chat: 'شروع چت',
}

const EN: typeof FA = {
  heading: 'Page not found',
  body: 'The page you are looking for does not exist, or has moved.',
  home: 'Back to home',
  chat: 'Start a chat',
}

export const notFoundStrings = dict(FA, EN)
