import React from 'react';
import { AlertTriangle, ArrowRight } from 'lucide-react';

export default function MockExportBanner({ onGoToSettings }) {
  return (
    <aside aria-label="Export mode notice" className="bg-warning-soft border-b border-warning/50 px-4 py-2.5 text-ink transition-colors">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-xs sm:text-sm">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-warning flex-shrink-0" aria-hidden="true" />
          <span className="font-bold tracking-wide">NEEDS REAL GOOGLE CREDENTIALS TO TEST LIVE EXPORT</span>
          <span className="hidden md:inline text-ink-muted">— Google Docs export is running in mock / dry-run mode.</span>
        </div>
        {onGoToSettings && (
          <button
            type="button"
            onClick={onGoToSettings}
            className="inline-flex items-center gap-1 font-semibold underline underline-offset-2 text-ink hover:text-accent transition-colors"
          >
            <span>Configure in Settings</span>
            <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        )}
      </div>
    </aside>
  );
}
