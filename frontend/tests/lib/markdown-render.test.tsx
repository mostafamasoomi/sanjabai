import { describe, it, expect } from 'vitest'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import MarkdownRenderer from '../../app/chat/components/MarkdownRenderer'

/**
 * Regression test for the "every inline code becomes a full code-block card"
 * bug: react-markdown v10 dropped the `inline` prop that MarkdownRenderer's
 * `code` component used to branch on, so `inline` was always `undefined`
 * and every `` `code` `` span -- inline or fenced -- rendered as <CodeBlock>.
 *
 * MarkdownRenderer is a 'use client' component with hooks (CodeBlock uses
 * useState), but renderToStaticMarkup works fine for a one-shot static
 * render -- no interactivity is needed to check which DOM classes came out.
 *
 * Written without JSX: the repo's tsconfig sets `"jsx": "preserve"`, which
 * vitest/esbuild cannot transform (confirmed by running a JSX-literal test
 * file under `npx vitest run` in this project -- it fails with "Failed to
 * parse source ... make sure to not set jsx to preserve"). React Testing
 * Library is also not installed (`node_modules/@testing-library` absent),
 * hence renderToStaticMarkup + React.createElement per the task brief.
 */

const CONTENT = [
  'متن فارسی با `myVariable` وسطش و بعد یک بلوک کد:',
  '',
  '```python',
  'print(1)',
  '```',
].join('\n')

function render() {
  return renderToStaticMarkup(React.createElement(MarkdownRenderer, { content: CONTENT }))
}

describe('MarkdownRenderer inline code vs fenced code block', () => {
  it('renders inline code as a plain inline-code span, not a code-block card', () => {
    const html = render()
    expect(html).toMatch(/<code class="inline-code"[^>]*>myVariable<\/code>/)
  })

  it('renders exactly one .code-block card, for the fenced block only', () => {
    const html = render()
    const codeBlockMatches = html.match(/class="code-block"/g) ?? []
    expect(codeBlockMatches).toHaveLength(1)
  })

  it('tags the fenced code-block card with the correct language', () => {
    const html = render()
    expect(html).toMatch(/<span class="code-lang">python<\/span>/)
  })
})
