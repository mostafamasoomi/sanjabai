'use client'

import React from 'react'
import { getLang } from '@/components/LanguageToggle'
import { errorBoundaryStrings } from './ErrorBoundary.strings'

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
      // A class component cannot call the useLang() hook -- getLang() is the
      // plain, non-reactive reader LanguageToggle.tsx exports for exactly
      // this case. This fallback is rare enough that not re-rendering on a
      // language flip mid-error is an acceptable trade.
      const s = errorBoundaryStrings(getLang())
      return (
        this.props.fallback || (
          <div className="rounded-xl border border-[var(--danger)]/30 bg-[var(--danger)]/5 p-6 text-center">
            <div className="text-3xl mb-2">⚠️</div>
            <h3 className="text-sm font-semibold text-[var(--danger)] mb-1">{s.loadError}</h3>
            <p className="text-xs text-[var(--text-muted)] mb-4">
              {this.state.error?.message || s.genericProblem}
            </p>
            <button
              onClick={() => this.setState({ hasError: false })}
              className="btn btn-ghost btn-sm"
            >
              {s.retry}
            </button>
          </div>
        )
      )
    }

    return this.props.children
  }
}