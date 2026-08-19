import { MetadataRoute } from 'next'

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = 'https://sanjabai.ir'

  const pages = [
    { path: '', priority: 1, changeFreq: 'weekly' as const },
    { path: '/chat', priority: 0.9, changeFreq: 'daily' as const },
    { path: '/models', priority: 0.8, changeFreq: 'weekly' as const },
    { path: '/compare', priority: 0.7, changeFreq: 'weekly' as const },
    { path: '/pricing', priority: 0.9, changeFreq: 'weekly' as const },
    { path: '/dashboard', priority: 0.6, changeFreq: 'daily' as const },
    { path: '/wallet', priority: 0.5, changeFreq: 'weekly' as const },
    { path: '/login', priority: 0.4, changeFreq: 'monthly' as const },
    { path: '/signup', priority: 0.5, changeFreq: 'monthly' as const },
    { path: '/topup', priority: 0.4, changeFreq: 'monthly' as const },
  ]

  return pages.map((page) => ({
    url: `${baseUrl}${page.path}`,
    lastModified: new Date(),
    changeFrequency: page.changeFreq,
    priority: page.priority,
  }))
}