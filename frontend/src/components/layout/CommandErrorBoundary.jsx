/**
 * CommandErrorBoundary — class-based React error boundary for the command-centre shell.
 * Catches render errors in lazy-loaded pages and shows a recovery UI instead of a blank screen.
 *
 * Usage:
 *   <CommandErrorBoundary>
 *     <Suspense fallback={<PageLoadingFallback />}>
 *       <LazyPage />
 *     </Suspense>
 *   </CommandErrorBoundary>
 */
import { Component } from 'react'

export default class CommandErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, errorId: null, errorTime: null }
  }

  static getDerivedStateFromError() {
    return {
      hasError: true,
      errorId: Math.random().toString(36).slice(2, 10).toUpperCase(),
      errorTime: new Date().toISOString(),
    }
  }

  componentDidCatch(error, info) {
    console.error('[CommandErrorBoundary]', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-panel" role="alert" aria-live="assertive">
          <div className="error-boundary-panel__inner">
            <p className="eyebrow">System error</p>
            <h2>This section encountered an error</h2>
            <p className="muted">
              Error ID: <code>{this.state.errorId}</code> — {this.state.errorTime}
            </p>
            <div className="button-row">
              <button
                type="button"
                className="command-action-button"
                onClick={() => this.setState({ hasError: false, errorId: null, errorTime: null })}
              >
                Try again
              </button>
              <button
                type="button"
                className="command-action-button subtle"
                onClick={() => window.location.reload()}
              >
                Reload page
              </button>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
