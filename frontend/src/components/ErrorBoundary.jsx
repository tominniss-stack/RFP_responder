import React from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info?.componentStack);
  }

  reset = () => {
    this.setState({ error: null });
    this.props.onReset?.();
  };

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="max-w-xl mx-auto my-16 card border-danger/40">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-6 h-6 text-danger flex-shrink-0" aria-hidden="true" />
          <div className="flex-1">
            <h2 className="text-lg font-bold">Something went wrong</h2>
            <p className="help-text mt-1">
              The view hit an unexpected error. You can try again, or return to the tracker.
            </p>
            <pre className="mt-3 sub-card font-mono text-xs overflow-x-auto whitespace-pre-wrap">
              {String(this.state.error?.message || this.state.error)}
            </pre>
            <div className="mt-4 flex gap-2">
              <button type="button" className="btn-primary" onClick={this.reset}>
                <RotateCcw className="w-4 h-4" aria-hidden="true" />
                Try again
              </button>
              <a href="#/" className="btn-secondary" onClick={this.reset}>
                Back to tracker
              </a>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
