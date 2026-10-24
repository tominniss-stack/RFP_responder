import React from 'react';
import { BookOpen, Copy } from 'lucide-react';

export function briefAsText(rfp, sections) {
  return rfp.raw_details || sections.map((s) => `### ${s.heading}\n${s.original_text || ''}`).join('\n\n');
}

export default function OriginalBriefView({ rfp, sections, onCopy }) {
  return (
    <div className="space-y-6">
      <div className="card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded bg-accent-soft text-accent flex items-center justify-center flex-shrink-0">
            <BookOpen className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-bold text-ink">Original RFP brief</h2>
            <p className="help-text font-mono">{rfp.source_document ? `File: ${rfp.source_document}` : 'Manual intake'}</p>
          </div>
        </div>
        <button type="button" onClick={onCopy} className="btn-secondary text-xs">
          <Copy className="w-3.5 h-3.5" aria-hidden="true" />
          <span>Copy brief</span>
        </button>
      </div>

      <div className="card p-6 sm:p-8 max-w-4xl mx-auto space-y-4">
        <div className="border-b border-border pb-3 flex items-center justify-between">
          <span className="field-label mb-0">Source text</span>
          <span className="help-text font-mono">{(rfp.raw_details || '').length} characters</span>
        </div>
        {rfp.raw_details ? (
          <div className="text-sm text-ink leading-relaxed whitespace-pre-wrap sub-card p-5">{rfp.raw_details}</div>
        ) : (
          <div className="space-y-4">
            <p className="help-text italic">The full source text was not retained; showing the extracted requirement for each section.</p>
            {sections.map((s, idx) => (
              <div key={s.id || idx} className="sub-card">
                <h3 className="text-xs font-bold uppercase text-ink mb-1">{s.heading}</h3>
                <p className="text-sm whitespace-pre-wrap">{s.original_text || 'No requirement text provided.'}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function OriginalBriefDrawer({ rfp, sections, onClose }) {
  return (
    <aside className="fixed inset-y-0 right-0 z-40 w-full sm:w-[480px] bg-surface border-l border-border-strong shadow-raised flex flex-col" aria-label="Original brief reference">
      <div className="p-4 border-b border-border flex items-center justify-between bg-surface-raised">
        <h3 className="text-sm font-bold text-ink flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-accent" aria-hidden="true" />
          Original brief
        </h3>
        <button type="button" onClick={onClose} className="btn-icon" aria-label="Close brief panel">
          ×
        </button>
      </div>
      <div className="p-4 overflow-y-auto flex-1 space-y-4 text-sm text-ink leading-relaxed">
        <p className="help-text font-mono sub-card p-2">{rfp.source_document ? `Source: ${rfp.source_document}` : `Client: ${rfp.client_name}`}</p>
        {rfp.raw_details ? (
          <div className="whitespace-pre-wrap sub-card p-4">{rfp.raw_details}</div>
        ) : (
          sections.map((s, idx) => (
            <div key={s.id || idx} className="sub-card">
              <h4 className="text-xs font-bold text-ink">{s.heading}</h4>
              <p className="text-xs text-ink-muted mt-1 whitespace-pre-wrap">{s.original_text || 'No requirement text.'}</p>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
