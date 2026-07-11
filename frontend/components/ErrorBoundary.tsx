'use client'

import React from 'react'

interface Props {
  children: React.ReactNode
  fallback?: React.ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="rounded-xl border border-[var(--danger)]/30 bg-[var(--danger)]/5 p-6 text-center">
            <div className="text-3xl mb-2">⚠️</div>
            <h3 className="text-sm font-semibold text-[var(--danger)] mb-1">خطا در بارگذاری</h3>
            <p className="text-xs text-[var(--text-muted)] mb-4">
              {this.state.error?.message || 'مشکلی در این بخش پیش آمده'}
            </p>
            <button
              onClick={() => this.setState({ hasError: false })}
              className="btn btn-ghost btn-sm"
            >
              تلاش مجدد
            </button>
          </div>
        )
      )
    }

    return this.props.children
  }
}