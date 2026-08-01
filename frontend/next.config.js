/** @type {import('next').NextConfig} */
const API_BACKEND = process.env.NEXT_PUBLIC_API_URL || 'http://sanjhubai-sanjhubai_api-1:8000'

const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ]
  },
  async rewrites() {
    return [
      // Proxy /api/* to backend
      { source: '/api/:path*', destination: `${API_BACKEND}/:path*` },
      // Proxy /v1/* to backend (chat completions)
      { source: '/v1/:path*', destination: `${API_BACKEND}/v1/:path*` },
      // Proxy /admin/* API calls to backend
      // { source: '/admin/:path+', destination: `${API_BACKEND}/admin/:path+` },
    ]
  },
}

// Bundle analyzer (Phase 10). Enabled only when ANALYZE=true so the default
// `next build` never requires the optional dev dependency to be present.
// Run: npm run analyze  (opens an interactive treemap of every chunk)
let config = nextConfig
if (process.env.ANALYZE) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const withBundleAnalyzer = require('@next/bundle-analyzer')({ enabled: true })
    config = withBundleAnalyzer(nextConfig)
  } catch (err) {
    console.warn(
      '[next.config] @next/bundle-analyzer not installed — skipping analyzer. ' +
        'Run `npm i -D @next/bundle-analyzer` to enable `npm run analyze`.',
    )
  }
}

module.exports = config
