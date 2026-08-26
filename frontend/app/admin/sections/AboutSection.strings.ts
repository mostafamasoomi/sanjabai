import { dict } from '@/lib/i18n'

const FA = {
  title: 'درباره ما',
  subtitle: 'محتوای صفحه درباره ما',
  loadError: 'خطا در دریافت محتوای درباره ما',
  saveSuccess: 'درباره ما ذخیره شد',
  saveError: 'خطا در ذخیره درباره ما',
  titleLabel: 'عنوان',
  bodyLabel: 'متن',
  save: 'ذخیره',
  // Placeholders, not content: they are a hint to the admin and are never
  // saved. The body hint still says «به فارسی» in both languages because the
  // page it feeds is Persian whichever language the panel is showing.
  titlePlaceholder: 'درباره Sanjabai',
  bodyPlaceholder: 'متن درباره ما به فارسی...',
}

const EN: typeof FA = {
  title: 'About us',
  subtitle: 'Content of the about-us page',
  loadError: 'Failed to load about-us content',
  saveSuccess: 'About-us content saved',
  saveError: 'Failed to save about-us content',
  titleLabel: 'Title',
  bodyLabel: 'Body',
  save: 'Save',
  titlePlaceholder: 'About Sanjabai',
  bodyPlaceholder: 'About-us text, in Persian…',
}

export const aboutStrings = dict(FA, EN)
