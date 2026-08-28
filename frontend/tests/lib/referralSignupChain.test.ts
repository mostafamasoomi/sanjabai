import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { buildSignupBody } from '@/lib/auth'

/**
 * F-REF phase 5 — proves the `?ref=` -> signup request-body half of the
 * referral chain actually works, end to end through the real function
 * (not a reimplementation): `buildSignupBody` is the exact helper
 * `lib/auth.tsx`'s `signup()` useCallback calls to build the
 * `POST /api/auth/signup` body. It is exported from lib/auth.tsx
 * specifically so this test can exercise the real logic without needing
 * to render <AuthProvider> -- this repo has no @testing-library/react
 * installed (confirmed absent from package.json and node_modules; see
 * tests/lib/auth.test.ts's and tests/lib/markdown-render.test.tsx's
 * identical note) and installing one is out of scope for this change.
 *
 * The other half of the chain -- signup/page.tsx reading `useSearchParams()`
 * and passing it on, and signup() forwarding it into buildSignupBody -- is
 * NOT covered by the cases above, and tsc does not cover it either. That was
 * measured, not assumed: deleting the `ref` argument from signup()'s call to
 * buildSignupBody leaves `npx tsc --noEmit` clean (the parameter is optional,
 * so dropping it is legal TypeScript) and every buildSignupBody case below
 * still green -- the referral chain would be dead in production with a fully
 * green suite, which is exactly the failure this file exists to prevent.
 *
 * Hence the source scan at the bottom. It is a weaker instrument than
 * rendering the page, and it is here only because this repo has no
 * @testing-library/react (absent from package.json and node_modules; see the
 * identical note in tests/lib/auth.test.ts). It pins the two argument
 * hand-offs that carry the code from the URL to the request body.
 */
describe('referral signup chain: buildSignupBody', () => {
  it('includes ref in the body when ?ref= carried a code', () => {
    const body = buildSignupBody('a@b.com', 'password123', undefined, undefined, 'abcd1234')
    expect(body).toEqual({ email: 'a@b.com', password: 'password123', ref: 'abcd1234' })
  })

  it('omits the ref key entirely when there was no ?ref=', () => {
    const body = buildSignupBody('a@b.com', 'password123')
    expect(body).not.toHaveProperty('ref')
    expect(Object.keys(body).sort()).toEqual(['email', 'password'])
  })

  it('omits ref for an empty string (no ?ref= present -> searchParams.get returns null -> "")', () => {
    const body = buildSignupBody('a@b.com', 'password123', undefined, undefined, '')
    expect(body).not.toHaveProperty('ref')
  })

  it('omits ref for a whitespace-only value and never sends unsanitised whitespace', () => {
    const body = buildSignupBody('a@b.com', 'password123', undefined, undefined, '   ')
    expect(body).not.toHaveProperty('ref')
  })

  it('trims a ref with surrounding whitespace before sending it', () => {
    const body = buildSignupBody('a@b.com', 'password123', undefined, undefined, '  abcd1234  ')
    expect(body.ref).toBe('abcd1234')
  })

  it('still sends captcha fields alongside ref when both are present', () => {
    const body = buildSignupBody('a@b.com', 'password123', 'tok', 'ans', 'abcd1234')
    expect(body).toEqual({
      email: 'a@b.com', password: 'password123',
      captcha_token: 'tok', captcha_answer: 'ans', ref: 'abcd1234',
    })
  })

  it('an invalid-looking ref is still sent as-is: validity is the backend\'s call, not the client\'s', () => {
    // backend/auth.py:181-194 looks up the code and silently no-ops when it
    // matches no user -- the client's only job is "is there a ref at all",
    // never "is it a real code".
    const body = buildSignupBody('a@b.com', 'password123', undefined, undefined, 'not-a-real-code')
    expect(body.ref).toBe('not-a-real-code')
  })
})

describe('referral signup chain: the wiring the unit cases above cannot see', () => {
  const read = (rel: string) => readFileSync(join(__dirname, '../..', rel), 'utf8')

  it('signup() forwards its ref argument into buildSignupBody', () => {
    // Drop `ref` here and the chain is dead while tsc and every case above
    // stay green -- verified by mutation.
    const src = read('lib/auth.tsx')
    expect(src).toMatch(
      /buildSignupBody\(\s*email\s*,\s*password\s*,\s*captchaToken\s*,\s*captchaAnswer\s*,\s*ref\s*\)/,
    )
  })

  it('the signup page reads ?ref= and passes it to signup() in the ref position', () => {
    const src = read('app/signup/page.tsx')
    // The code has to come from the URL, not from a form field or a constant.
    expect(src).toMatch(/useSearchParams\(\)/)
    expect(src).toMatch(/searchParams\.get\(\s*'ref'\s*\)/)
    // 5th argument, matching AuthCtx['signup']. Position is load-bearing and
    // type-invisible: every trailing parameter of signup() is an optional
    // string, so a ref handed to the captcha slot compiles cleanly.
    expect(src).toMatch(/\bsignup\((?:[^()]|\([^()]*\))*,\s*ref\s*\)/)
  })
})
