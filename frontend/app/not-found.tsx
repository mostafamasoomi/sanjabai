import type { Metadata } from 'next'
import { NotFoundView } from './NotFoundView'

/* Stays a Server Component so it can keep exporting `metadata` — the custom
   title and, more importantly, the `noindex` directive that keeps 404s out of
   search results. A file that exports metadata cannot call a client hook, so
   the visible half lives in ./NotFoundView.
   The title itself stays Persian: page metadata is resolved on the server,
   before any client script has read the language, so there is nothing to
   branch on. Same reason app/layout.tsx's metadata is Persian. */
export const metadata: Metadata = {
  title: 'صفحه پیدا نشد',
  robots: { index: false, follow: false },
}

export default function NotFound() {
  return <NotFoundView />
}
