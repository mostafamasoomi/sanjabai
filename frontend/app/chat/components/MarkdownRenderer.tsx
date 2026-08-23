'use client'

import React, {
  type ReactNode,
  type AnchorHTMLAttributes,
  type HTMLAttributes,
  type ImgHTMLAttributes,
  type TableHTMLAttributes,
} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import rehypeSanitize from 'rehype-sanitize'
import CodeBlock from './CodeBlock'
// Bug 2: rehypeHighlight tags code with hljs-* classes but no theme CSS was
// ever loaded (grep for `hljs` under app/ was a zero-hit). Next.js allows a
// plain (non-module) CSS import from node_modules inside a client component
// module; scoping it here (rather than the top of globals.css) keeps it out
// of the file's line-range this task is restricted to.
import 'highlight.js/styles/github-dark.css'

type MarkdownRendererProps = {
  content: string
}

function ExternalLinkIcon({ size = 12 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  )
}

const RTL_REGEX = /[\u0591-\u07FF\uFB1D-\uFDFD\uFE70-\uFEFC]/

function getDir(text: string): 'rtl' | 'ltr' | undefined {
  if (!text) return undefined
  for (const ch of text) {
    if (RTL_REGEX.test(ch)) return 'rtl'
    if (/[A-Za-z]/.test(ch)) return 'ltr'
  }
  return undefined
}

type CodeComponentProps = {
  className?: string
  children?: ReactNode
  node?: unknown
} & HTMLAttributes<HTMLElement>

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const containerDir = getDir(content)

  return (
    <div className="markdown-content" dir={containerDir ?? 'auto'}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize, rehypeHighlight]}
        components={{
          // Bug 1: react-markdown v10 removed the `inline` prop that `code`
          // used to receive (confirmed: `grep -c inline node_modules/react-markdown/lib/index.js`
          // → 0), so it was always undefined and every inline `` `code` ``
          // span rendered as a full CodeBlock card. v10 always produces
          // <pre><code>…</code></pre> for a fenced block and never wraps
          // inline code in <pre> — so detect block vs. inline from the tree
          // shape instead. `pre`'s `children` here is the *unrendered*
          // `<code>` React element (its own component function hasn't been
          // invoked yet), so its `props.className`/`props.children` still
          // carry rehype-highlight's original `hljs language-xxx` class and
          // highlighted spans — reach into those directly and hand them to
          // CodeBlock, bypassing the (always-inline) `code` component below.
          pre: ({ children }: { children?: ReactNode }) => {
            const child = React.Children.toArray(children)[0]
            if (React.isValidElement<{ className?: string; children?: ReactNode }>(child)) {
              return <CodeBlock className={child.props.className}>{child.props.children}</CodeBlock>
            }
            return <pre>{children}</pre>
          },
          // Only ever reached for genuine inline code — block-level `code`
          // nodes are intercepted (and rendered via CodeBlock) by `pre`
          // above before this component is invoked.
          code: ({ className: _className, children, node: _node, ...rest }: CodeComponentProps) => {
            return (
              <code className="inline-code" dir="ltr" {...rest}>
                {children}
              </code>
            )
          },
          a: (
            props: AnchorHTMLAttributes<HTMLAnchorElement> & { children?: ReactNode; node?: unknown },
          ) => {
            const { children, href, node: _node, ...rest } = props
            const hrefStr = href ?? ''
            const isExternal = /^https?:\/\//.test(hrefStr)
            return (
              <a
                href={hrefStr}
                target={isExternal ? '_blank' : undefined}
                rel={isExternal ? 'noopener noreferrer' : undefined}
                className="markdown-link"
                {...rest}
              >
                {children}
                {isExternal && (
                  <span className="markdown-external-icon" aria-hidden>
                    <ExternalLinkIcon size={11} />
                  </span>
                )}
              </a>
            )
          },
          table: (
            props: TableHTMLAttributes<HTMLTableElement> & { children?: ReactNode; node?: unknown },
          ) => {
            const { children, node: _node, ...rest } = props
            // Bug 6: dir was hardcoded to "ltr", which reverses column order
            // for Persian-content tables. Drop it and let it inherit from
            // the outer .markdown-content container (getDir(content) above).
            return (
              <div className="table-scroll">
                <table {...rest}>{children}</table>
              </div>
            )
          },
          p: (
            props: HTMLAttributes<HTMLParagraphElement> & { children?: ReactNode; node?: unknown },
          ) => {
            const { node: _node, ...rest } = props
            return <p dir="auto" {...rest} />
          },
          h1: (
            props: HTMLAttributes<HTMLHeadingElement> & { children?: ReactNode; node?: unknown },
          ) => {
            const { node: _node, ...rest } = props
            return <h1 dir="auto" {...rest} />
          },
          h2: (
            props: HTMLAttributes<HTMLHeadingElement> & { children?: ReactNode; node?: unknown },
          ) => {
            const { node: _node, ...rest } = props
            return <h2 dir="auto" {...rest} />
          },
          h3: (
            props: HTMLAttributes<HTMLHeadingElement> & { children?: ReactNode; node?: unknown },
          ) => {
            const { node: _node, ...rest } = props
            return <h3 dir="auto" {...rest} />
          },
          blockquote: (
            props: HTMLAttributes<HTMLQuoteElement> & { children?: ReactNode; node?: unknown },
          ) => {
            const { node: _node, ...rest } = props
            return <blockquote dir="auto" {...rest} />
          },
          li: (
            props: HTMLAttributes<HTMLLIElement> & { children?: ReactNode; node?: unknown },
          ) => {
            const { node: _node, ...rest } = props
            return <li dir="auto" {...rest} />
          },
          img: (props: ImgHTMLAttributes<HTMLImageElement> & { node?: unknown }) => {
            const { node: _node, alt, ...rest } = props
            return (
              <img
                {...rest}
                alt={alt ?? ''}
                loading="lazy"
                style={{ maxWidth: '100%', borderRadius: 'var(--radius-md)' }}
              />
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
