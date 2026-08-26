import { dict } from '@/lib/i18n'

const FA = {
  title: 'امروز شروع کنید',
  lead: 'ثبت‌نام کمتر از یک دقیقه طول می‌کشد و رایگان است. کارت اعتباری لازم نیست — کیف پول را هر وقت خواستید شارژ کنید.',
  signupCta: 'ساخت حساب رایگان',
  docsCta: 'مطالعه‌ی مستندات',
}

const EN: typeof FA = {
  title: 'Get started today',
  lead: "Signing up takes under a minute and it's free. No credit card needed — top up your wallet whenever you want.",
  signupCta: 'Create a free account',
  docsCta: 'Read the docs',
}

export const closingCtaStrings = dict(FA, EN)
