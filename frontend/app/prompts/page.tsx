'use client'

import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { Icon, type IconName } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt, navIcon } from '@/lib/i18n'
import { promptsPageStrings } from './page.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjabai Prompt Library — 10 prompt templates with search & filter.

   `category`/`icon` and the template metadata (title, description) are UI
   chrome and are translated via page.strings.ts. `prompt` — the text that
   actually gets sent to the model when a card is used — is CONTENT, not
   chrome: it stays Persian in both languages, per the i18n spec's rule that
   a Persian prompt a user picked must never be silently swapped for an
   English one. See the handoff report for the full reasoning.
   ═══════════════════════════════════════════════════════════════════════════ */

type PromptCategoryKey = 'coding' | 'translation' | 'analysis' | 'creativity' | 'general'

type PromptId = 'p1' | 'p2' | 'p3' | 'p4' | 'p5' | 'p6' | 'p7' | 'p8' | 'p9' | 'p10'

type PromptTemplate = {
  id: PromptId
  category: PromptCategoryKey
  prompt: string
  icon: IconName
}

const CATEGORY_ICONS: Record<PromptCategoryKey, IconName> = {
  coding: 'code',
  translation: 'chat',
  analysis: 'search',
  creativity: 'sparkles',
  general: 'info',
}

const CATEGORY_COLORS: Record<PromptCategoryKey, string> = {
  coding: 'var(--accent)',
  translation: 'var(--success)',
  analysis: 'var(--warning)',
  creativity: 'var(--accent-purple)',
  general: 'var(--text-secondary)',
}

const PROMPTS: PromptTemplate[] = [
  { id: 'p1', category: 'coding', prompt: 'یک تابع پایتون بنویس که ', icon: 'code' },
  {
    id: 'p2',
    category: 'translation',
    prompt: 'متن زیر را به انگلیسی روان ترجمه کن، لحن رسمی و حرفه‌ای:\n\n',
    icon: 'chat',
  },
  {
    id: 'p3',
    category: 'analysis',
    prompt: 'متن زیر را تحلیل کن و نکات کلیدی، الگوها و خلاصه آن را استخراج کن:\n\n',
    icon: 'search',
  },
  { id: 'p4', category: 'creativity', prompt: '۱۰ ایده خلاقانه و نوآورانه برای ', icon: 'sparkles' },
  {
    id: 'p5',
    category: 'general',
    prompt: 'متن زیر را به صورت خلاصه و مفید در ۳ پاراگراف خلاصه کن:\n\n',
    icon: 'info',
  },
  {
    id: 'p6',
    category: 'coding',
    prompt: 'کد زیر را بررسی کن، باگ‌های احتمالی را پیدا کن و راه‌حل اصلاحی ارائه بده:\n\n',
    icon: 'code',
  },
  {
    id: 'p7',
    category: 'creativity',
    prompt: 'متن زیر را با لحن جذاب‌تر و روان‌تر بازنویسی کن، بدون تغییر در معنی اصلی:\n\n',
    icon: 'sparkles',
  },
  {
    id: 'p8',
    category: 'translation',
    prompt: 'متن انگلیسی زیر را به فارسی روان و سلیس ترجمه کن، با حفظ اصطلاحات تخصصی:\n\n',
    icon: 'chat',
  },
  {
    id: 'p9',
    category: 'analysis',
    prompt: 'یک تحلیل SWOT کامل برای موضوع زیر ارائه بده (نقاط قوت، ضعف، فرصت‌ها و تهدیدها):\n\n',
    icon: 'search',
  },
  {
    id: 'p10',
    category: 'general',
    prompt: 'مفهوم زیر را به زبان ساده و با مثال توضیح بده، طوری که یک فرد مبتدی هم متوجه شود:\n\n',
    icon: 'info',
  },
]

const ALL_CATEGORIES: PromptCategoryKey[] = ['coding', 'translation', 'analysis', 'creativity', 'general']

export default function PromptsPage() {
  const router = useRouter()
  const lang = useLang()
  const s = promptsPageStrings(lang)
  const f = fmt(lang)
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState<PromptCategoryKey | 'all'>('all')

  const filteredPrompts = useMemo(() => {
    let list = PROMPTS
    if (activeCategory !== 'all') {
      list = list.filter(p => p.category === activeCategory)
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter(p => {
        const meta = s.prompts[p.id]
        return (
          meta.title.toLowerCase().includes(q) ||
          meta.description.toLowerCase().includes(q) ||
          s.categories[p.category].toLowerCase().includes(q)
        )
      })
    }
    return list
  }, [search, activeCategory, s])

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
            <h1 className="prompts-title">{s.headerTitle}</h1>
            <p className="prompts-subtitle">{s.headerSubtitle}</p>
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
            placeholder={s.searchPlaceholder}
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {search && (
            <button
              className="prompts-search-clear"
              onClick={() => setSearch('')}
              aria-label={s.clearSearchAria}
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
            {s.allCategories}
          </button>
          {ALL_CATEGORIES.map(cat => (
            <button
              key={cat}
              className={`prompts-cat-btn ${activeCategory === cat ? 'prompts-cat-active' : ''}`}
              onClick={() => setActiveCategory(cat)}
            >
              <Icon name={CATEGORY_ICONS[cat]} size={14} />
              {s.categories[cat]}
            </button>
          ))}
        </div>
      </div>

      {/* Results count */}
      <div className="prompts-count">
        {s.countBase(f.num(filteredPrompts.length))}
        {activeCategory !== 'all' && s.countInCategory(s.categories[activeCategory])}
        {search && s.countForSearch(search)}
      </div>

      {/* Prompt Grid */}
      {filteredPrompts.length === 0 ? (
        <div className="prompts-empty">
          <Icon name="search" size={32} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>{s.emptyText}</p>
          <button className="btn btn-ghost" onClick={() => { setSearch(''); setActiveCategory('all') }}>
            {s.clearFilters}
          </button>
        </div>
      ) : (
        <div className="prompts-grid">
          {filteredPrompts.map(prompt => {
            const meta = s.prompts[prompt.id]
            return (
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
                    {s.categories[prompt.category]}
                  </span>
                </div>
                <h2 className="prompt-card-title">{meta.title}</h2>
                <p className="prompt-card-desc">{meta.description}</p>
                <div className="prompt-card-footer">
                  <span className="prompt-card-cta">
                    {s.useAction}
                    <Icon name={navIcon(lang, 'forward')} size={14} />
                  </span>
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
