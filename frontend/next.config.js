/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
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
