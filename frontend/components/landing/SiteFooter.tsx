import { BrandMark } from './primitives'
import { FOOTER_COLUMNS } from './content'

export function SiteFooter() {
  return (
    <footer className="lp-footer">
      <div className="lp-container">
        <div className="lp-footer__top">
          <div className="lp-footer__about">
            <a href="/" className="lp-brand">
              <BrandMark />
              Sanjhubai
            </a>
            <p className="lp-footer__tagline">
              پلتفرم فارسی دسترسی به مدل‌های هوش مصنوعی. چت کنید، عامل بسازید و با یک API
              به محصولتان وصل شوید — با پرداخت ریالی و پشتیبانی محلی.
            </p>
          </div>

          {FOOTER_COLUMNS.map((column) => (
            <nav key={column.title} className="lp-footer__col" aria-label={column.title}>
              <h3>{column.title}</h3>
              {column.links.map((link) => (
                <a key={link.href} href={link.href}>
                  {link.label}
                </a>
              ))}
            </nav>
          ))}
        </div>

        <div className="lp-footer__bottom">
          <span>© ۱۴۰۴ Sanjhubai — تمامی حقوق محفوظ است.</span>
          <span>ساخته‌شده برای کاربران فارسی‌زبان</span>
        </div>
      </div>
    </footer>
  )
}
