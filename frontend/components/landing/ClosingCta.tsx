import { Reveal } from './Reveal'
import { ForwardArrow } from './primitives'

export function ClosingCta() {
  return (
    <section className="lp-section">
      <div className="lp-container">
        <Reveal className="lp-cta">
          <h2 className="lp-title">امروز شروع کنید</h2>
          <p className="lp-lead">
            ثبت‌نام کمتر از یک دقیقه طول می‌کشد و رایگان است. کارت اعتباری لازم نیست — کیف
            پول را هر وقت خواستید شارژ کنید.
          </p>
          <div className="lp-hero__actions">
            <a href="/signup" className="lp-btn lp-btn--primary lp-btn--lg">
              ساخت حساب رایگان
              <ForwardArrow />
            </a>
            <a href="/developer" className="lp-btn lp-btn--ghost lp-btn--lg">
              مطالعه‌ی مستندات
            </a>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
