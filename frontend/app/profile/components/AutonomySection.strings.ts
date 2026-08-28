import { dict } from '@/lib/i18n'

const FA = {
  title: 'سطح خودمختاری',
  intro: 'این تنظیم مشخص می‌کند مدل در گفتگو حق دارد چه چیزی برایتان بسازد و کِی اول از شما بپرسد. روی ساختن وظیفه و دستیار اثر می‌گذارد، نه روی خود پاسخ‌ها.',
}

const EN: typeof FA = {
  title: 'Autonomy Level',
  intro: 'This controls what the model may create for you from a conversation, and when it asks first. It affects creating tasks and assistants, not the answers themselves.',
}

export const autonomySectionStrings = dict(FA, EN)
