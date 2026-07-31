'use client'

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { Icon, type IconName } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjabai Prompt Library — 10 Persian prompt templates with search & filter
   ═══════════════════════════════════════════════════════════════════════════ */

type PromptCategory = 'کدنویسی' | 'ترجمه' | 'تحلیل' | 'خلاقیت' | 'عمومی'

type PromptTemplate = {
  id: string
  title: string
  description: string
  category: PromptCategory
  prompt: string
  icon: IconName
}

const CATEGORY_ICONS: Record<PromptCategory, IconName> = {
  'کدنویسی': 'code',
  'ترجمه': 'chat',
  'تحلیل': 'search',
  'خلاقیت': 'sparkles',
  'عمومی': 'info',
}

const CATEGORY_COLORS: Record<PromptCategory, string> = {
  'کدنویسی': 'var(--accent)',
  'ترجمه': 'var(--success)',
  'تحلیل': 'var(--warning)',
  'خلاقیت': 'var(--accent-purple)',
  'عمومی': 'var(--text-secondary)',
}

const PROMPTS: PromptTemplate[] = [
  {
    id: 'p1',
    title: 'نوشتن کد پایتون',
    description: 'یک تابع یا اسکریپت پایتون با توضیحات کامل و بهینه',
    category: 'کدنویسی',
    prompt: 'یک تابع پایتون بنویس که ',
    icon: 'code',
  },
  {
    id: 'p2',
    title: 'ترجمه فارسی به انگلیسی',
    description: 'ترجمه روان و دقیق متن فارسی به انگلیسی',
    category: 'ترجمه',
    prompt: 'متن زیر را به انگلیسی روان ترجمه کن، لحن رسمی و حرفه‌ای:\n\n',
    icon: 'chat',
  },
  {
    id: 'p3',
    title: 'تحلیل داده‌های متنی',
    description: 'تحلیل و استخراج الگوها و اطلاعات کلیدی از متن',
    category: 'تحلیل',
    prompt: 'متن زیر را تحلیل کن و نکات کلیدی، الگوها و خلاصه آن را استخراج کن:\n\n',
    icon: 'search',
  },
  {
    id: 'p4',
    title: 'ایده‌پردازی خلاقانه',
    description: 'تولید ایده‌های خلاقانه برای پروژه‌ها و کسب‌وکارها',
    category: 'خلاقیت',
    prompt: '۱۰ ایده خلاقانه و نوآورانه برای ',
    icon: 'sparkles',
  },
  {
    id: 'p5',
    title: 'خلاصه‌سازی متن',
    description: 'خلاصه‌سازی هوشمند متن‌های طولانی به نکات اصلی',
    category: 'عمومی',
    prompt: 'متن زیر را به صورت خلاصه و مفید در ۳ پاراگراف خلاصه کن:\n\n',
    icon: 'info',
  },
  {
    id: 'p6',
    title: 'بررسی باگ و رفع اشکال',
    description: 'تحلیل کد و پیدا کردن باگ‌ها با پیشنهاد راه‌حل',
    category: 'کدنویسی',
    prompt: 'کد زیر را بررسی کن، باگ‌های احتمالی را پیدا کن و راه‌حل اصلاحی ارائه بده:\n\n',
    icon: 'code',
  },
  {
    id: 'p7',
    title: 'بازنویسی محتوا',
    description: 'بازنویسی و بهبود متن با حفظ معنی اصلی',
    category: 'خلاقیت',
    prompt: 'متن زیر را با لحن جذاب‌تر و روان‌تر بازنویسی کن، بدون تغییر در معنی اصلی:\n\n',
    icon: 'sparkles',
  },
  {
    id: 'p8',
    title: 'ترجمه انگلیسی به فارسی',
    description: 'ترجمه تخصصی و روان انگلیسی به فارسی',
    category: 'ترجمه',
    prompt: 'متن انگلیسی زیر را به فارسی روان و سلیس ترجمه کن، با حفظ اصطلاحات تخصصی:\n\n',
    icon: 'chat',
  },
  {
    id: 'p9',
    title: 'تحلیل SWOT',
    description: 'تحلیل نقاط قوت، ضعف، فرصت‌ها و تهدیدها',
    category: 'تحلیل',
    prompt: 'یک تحلیل SWOT کامل برای موضوع زیر ارائه بده (نقاط قوت، ضعف، فرصت‌ها و تهدیدها):\n\n',
    icon: 'search',
  },
  {
    id: 'p10',
    title: 'توضیح مفاهیم پیچیده',
    description: 'توضیح ساده و قابل فهم مفاهیم علمی و تخصصی',
    category: 'عمومی',
    prompt: 'مفهوم زیر را به زبان ساده و با مثال توضیح بده، طوری که یک فرد مبتدی هم متوجه شود:\n\n',
    icon: 'info',
  },
]

const ALL_CATEGORIES: PromptCategory[] = ['کدنویسی', 'ترجمه', 'تحلیل', 'خلاقیت', 'عمومی']

export default function PromptsPage() {
  const router = useRouter()
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState<PromptCategory | 'all'>('all')

  const filteredPrompts = useMemo(() => {
    let list = PROMPTS
    if (activeCategory !== 'all') {
      list = list.filter(p => p.category === activeCategory)
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter(p =>
        p.title.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q)
      )
    }
    return list
  }, [search, activeCategory])

  const handleUsePrompt = (prompt: PromptTemplate) => {
    router.push(`/chat?prompt=${encodeURIComponent(prompt.prompt)}`)
  }

  return (
    <div className="prompts-page">
      {/* Header */}
      <div className="prompts-header">
        <div className="prompts-header-title">
          <div className="prompts-header-icon">
            <Icon name="sparkles" size={22} className="text-accent" />
          </div>
          <div>
            <h1 className="prompts-title">کتابخانه پرامپت</h1>
            <p className="prompts-subtitle">پرامپت‌های آماده فارسی برای شروع سریع گفتگو</p>
          </div>
        </div>
      </div>

      {/* Search & Filter */}
      <div className="prompts-toolbar">
        <div className="prompts-search-wrapper">
          <Icon name="search" size={16} className="prompts-search-icon" />
          <input
            type="text"
            className="prompts-search-input"
            placeholder="جستجوی پرامپت..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            dir="rtl"
          />
          {search && (
            <button
              className="prompts-search-clear"
              onClick={() => setSearch('')}
              aria-label="پاک کردن"
            >
              <Icon name="close" size={12} />
            </button>
          )}
        </div>

        <div className="prompts-categories">
          <button
            className={`prompts-cat-btn ${activeCategory === 'all' ? 'prompts-cat-active' : ''}`}
            onClick={() => setActiveCategory('all')}
          >
            همه
          </button>
          {ALL_CATEGORIES.map(cat => (
            <button
              key={cat}
              className={`prompts-cat-btn ${activeCategory === cat ? 'prompts-cat-active' : ''}`}
              onClick={() => setActiveCategory(cat)}
            >
              <Icon name={CATEGORY_ICONS[cat]} size={14} />
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Results count */}
      <div className="prompts-count">
        {faNum(filteredPrompts.length)} پرامپت
        {activeCategory !== 'all' && ` در دسته «${activeCategory}»`}
        {search && ` برای «${search}»`}
      </div>

      {/* Prompt Grid */}
      {filteredPrompts.length === 0 ? (
        <div className="prompts-empty">
          <Icon name="search" size={32} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>پرامپتی با این مشخصات یافت نشد</p>
          <button className="btn btn-ghost" onClick={() => { setSearch(''); setActiveCategory('all') }}>
            پاک کردن فیلترها
          </button>
        </div>
      ) : (
        <div className="prompts-grid">
          {filteredPrompts.map(prompt => (
            <button
              key={prompt.id}
              className="prompt-card"
              onClick={() => handleUsePrompt(prompt)}
            >
              <div className="prompt-card-header">
                <div
                  className="prompt-card-icon"
                  style={{ background: `${CATEGORY_COLORS[prompt.category]}20`, color: CATEGORY_COLORS[prompt.category] }}
                >
                  <Icon name={prompt.icon} size={20} />
                </div>
                <span
                  className="prompt-card-category"
                  style={{ color: CATEGORY_COLORS[prompt.category], background: `${CATEGORY_COLORS[prompt.category]}15` }}
                >
                  {prompt.category}
                </span>
              </div>
              <h2 className="prompt-card-title">{prompt.title}</h2>
              <p className="prompt-card-desc">{prompt.description}</p>
              <div className="prompt-card-footer">
                <span className="prompt-card-cta">
                  استفاده از پرامپت
                  <Icon name="arrowLeft" size={14} />
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}