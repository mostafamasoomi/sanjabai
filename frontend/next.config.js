/** @type {import('next').NextConfig} */
const API_BACKEND = process.env.NEXT_PUBLIC_API_URL || 'http://sanjabai-sanjabai_api-1:8000'

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
  // Next's rewrite proxy defaults to a 30s ceiling, which is *below* the
  // backend's own 90s httpx read timeout (app.py: httpx.Timeout(90, connect=10)).
  // A non-streaming completion that legitimately runs longer than 30s — measured
  // live: sanjab/claude-sonnet-5 on an 800-word Persian article answers in 55.9s
  // with a complete 4754-char body — was therefore killed here and surfaced to
  // the user as a bare "Internal Server Error", even though the API had produced
  // a perfect response. That hit /compare and /playground (both stream:false)
  // on every long answer.
  //
  // Must stay ABOVE the backend's own non-streaming ceiling
  // (providers.COMPLETION_TIMEOUT_SECONDS, 180s) so that upstream slowness
  // always surfaces as the backend's Persian `gateway_error` and never as a
  // proxy 500 the user cannot act on. Raise the backend value first if this
  // ever needs to go higher; the two are ordered on purpose.
  experimental: {
    proxyTimeout: 200_000,
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
