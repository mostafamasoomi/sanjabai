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
import rehypeRaw from 'rehype-raw'
import CodeBlock from './CodeBlock'

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
  inline?: boolean
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
        rehypePlugins={[rehypeRaw, rehypeHighlight]}
        components={{
          pre: ({ children }: { children?: ReactNode }) => {
            // Avoid double <pre> nesting — CodeBlock already renders its own <pre>
            return <>{children}</>
          },
          code: ({ inline, className, children, node: _node, ...rest }: CodeComponentProps) => {
            if (inline) {
              return (
                <code className="inline-code" dir="ltr" {...rest}>
                  {children}
                </code>
              )
            }
            return <CodeBlock className={className}>{children}</CodeBlock>
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
            return (
              <div className="table-scroll" dir="ltr">
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
