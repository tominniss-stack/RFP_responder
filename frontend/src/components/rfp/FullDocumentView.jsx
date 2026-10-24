import React from 'react';
import { ArrowUpRight, Check, Copy, Edit2, FileText, Printer, Save } from 'lucide-react';
import { MarkdownRenderer, MarkdownToolbar } from '../MarkdownRenderer';
import { formatGBP } from '../Badge';
import { sortSections } from './markdownInsert';

export default function FullDocumentView({ rfp, sections, copied, onCopy, onExport, exporting, inline, onStartInline, onInlineChange, onInlineInsert, onInlineSave, onInlineCancel, inlinePreview, onToggleInlinePreview }) {
  const sorted = sortSections(sections);
  const wordCount = sections.reduce((acc, s) => acc + (s.final_content || s.draft_content || '').split(/\s+/).filter(Boolean).length, 0);

  return (
    <div className="space-y-6">
      <div className="card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded bg-accent-soft text-accent flex items-center justify-center flex-shrink-0">
            <FileText className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-bold text-ink">Complete proposal document</h2>
            <p className="help-text font-mono">
              {sections.length} sections · {wordCount} words drafted
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={onCopy} className="btn-secondary text-xs">
            {copied ? <Check className="w-3.5 h-3.5 text-success" aria-hidden="true" /> : <Copy className="w-3.5 h-3.5" aria-hidden="true" />}
            <span>{copied ? 'Copied' : 'Copy Markdown'}</span>
          </button>
          <button type="button" onClick={() => window.print()} className="btn-secondary text-xs">
            <Printer className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Print / save PDF</span>
          </button>
          <button type="button" onClick={onExport} disabled={exporting || sections.length === 0} className="btn-primary text-xs">
            <ArrowUpRight className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Export to Google Doc</span>
          </button>
        </div>
      </div>

      <div className="card p-6 sm:p-12 space-y-10 max-w-4xl mx-auto print:shadow-none print:border-0">
        <header className="border-b-2 border-ink pb-8">
          <p className="text-xs font-mono uppercase tracking-widest text-ink-muted mb-1">Another Marketing Agency · Proposal response</p>
          <h1 className="text-3xl sm:text-4xl font-black text-ink tracking-tight mb-4">{rfp.client_name}</h1>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
            <span>
              <strong className="text-ink">Budget:</strong> {formatGBP(rfp.value)} ({rfp.budget_type || 'fixed'})
            </span>
            <span aria-hidden="true">·</span>
            <span>
              <strong className="text-ink">Deadline:</strong> {rfp.deadline || 'TBD'}
            </span>
            <span aria-hidden="true">·</span>
            <span>
              <strong className="text-ink">Status:</strong> {rfp.status || 'Draft'}
            </span>
            {rfp.budget_notes && (
              <>
                <span aria-hidden="true">·</span>
                <span className="italic">{rfp.budget_notes}</span>
              </>
            )}
          </p>
        </header>

        {sorted.length === 0 ? (
          <p className="text-sm text-ink-muted italic text-center py-10">No sections defined for this proposal yet.</p>
        ) : (
          sorted.map((sec, idx) => {
            const content = sec.final_content || sec.draft_content;
            const isEditing = inline.sectionId === sec.id;
            return (
              <section key={sec.id || idx} className="space-y-3 pb-8 border-b border-border last:border-b-0" aria-labelledby={`doc-sec-${sec.id}`}>
                <div className="flex items-center justify-between gap-3">
                  <h2 id={`doc-sec-${sec.id}`} className="text-xl font-bold text-ink flex items-baseline gap-2">
                    <span className="text-xs font-mono font-bold text-ink-muted">{String(idx + 1).padStart(2, '0')}.</span>
                    {sec.heading}
                  </h2>
                  {!isEditing && (
                    <button type="button" onClick={() => onStartInline(sec)} className="btn-secondary text-xs px-2.5 py-1 print:hidden" aria-label={`Edit section ${sec.heading}`}>
                      <Edit2 className="w-3 h-3" aria-hidden="true" />
                      <span>Edit</span>
                    </button>
                  )}
                </div>

                {isEditing ? (
                  <div className="space-y-3">
                    <MarkdownToolbar onInsert={onInlineInsert} isPreview={inlinePreview} onTogglePreview={onToggleInlinePreview} />
                    {inlinePreview ? (
                      <div className="bg-surface border border-border-strong rounded-md p-4 min-h-[160px] text-sm">
                        <MarkdownRenderer content={inline.content || '*No content yet.*'} />
                      </div>
                    ) : (
                      <>
                        <label htmlFor={`inline-editor-${sec.id}`} className="sr-only">
                          Edit {sec.heading}
                        </label>
                        <textarea id={`inline-editor-${sec.id}`} rows={10} value={inline.content} onChange={(e) => onInlineChange(e.target.value)} className="input-field font-mono leading-relaxed" />
                      </>
                    )}
                    <div className="flex items-center justify-end gap-2">
                      <button type="button" onClick={onInlineCancel} className="btn-secondary text-xs">
                        Cancel
                      </button>
                      <button type="button" disabled={inline.saving} onClick={() => onInlineSave(sec.id)} className="btn-primary text-xs">
                        <Save className="w-3.5 h-3.5" aria-hidden="true" />
                        <span>{inline.saving ? 'Saving…' : 'Save'}</span>
                      </button>
                    </div>
                  </div>
                ) : content ? (
                  <MarkdownRenderer content={content} />
                ) : (
                  <p className="p-4 bg-surface-raised border border-dashed border-border-strong rounded text-xs text-ink-muted italic">No draft generated for this section yet.</p>
                )}
              </section>
            );
          })
        )}
      </div>
    </div>
  );
}
