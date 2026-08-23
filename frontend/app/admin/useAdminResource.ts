/* One GET, owned by the section that renders it.
 *
 * Every admin section used to be fed by AdminPanel's `loadAll()`, a single
 * Promise.allSettled over ten endpoints whose rejections were dropped on the
 * floor. A page whose endpoint 405'd or 500'd rendered as "empty", which on
 * the درباره‌ما screen meant an empty textarea that overwrote live content on
 * save. So: three distinguishable states, never two.
 *
 *   loading -> skeleton
 *   error   -> the backend's own Persian `detail`, plus a retry
 *   data    -> the section
 *
 * A section that writes must gate its save on `error === null`; loading a
 * form and failing is not the same as loading an empty form.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errMessage } from './api'

export interface AdminResource<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => Promise<void>
  /** For optimistic row flips; a reload still wins. */
  setData: (updater: T | ((prev: T | null) => T | null)) => void
}

export function useAdminResource<T>(
  path: string,
  select: (raw: any) => T,
  genericError: string,
): AdminResource<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // `select` is written inline at every call site, so it is a new function
  // identity on each render. Holding it in a ref keeps `reload` stable and
  // stops the mount effect from re-firing forever.
  const selectRef = useRef(select)
  selectRef.current = select

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api(path)
      setData(selectRef.current(await res.json()))
    } catch (err) {
      setData(null)
      setError(errMessage(err, genericError))
    } finally {
      setLoading(false)
    }
  }, [path, genericError])

  useEffect(() => { reload() }, [reload])

  return { data, error, loading, reload, setData }
}
