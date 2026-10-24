import React from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, CornerDownRight, Loader2, Sparkles } from 'lucide-react';

export default function OpenQuestionsRibbon({ questions, sections, expanded, onToggle, inputs, onInputChange, resolving, onResolve, onJump }) {
  if (questions.length === 0) {
    return (
      <div className="mb-6 card p-4 flex items-center justify-between text-sm" role="status">
        <div className="flex items-center gap-2.5">
          <CheckCircle2 className="w-5 h-5 text-success flex-shrink-0" aria-hidden="true" />
          <span className="font-semibold text-ink">All information gaps resolved</span>
          <span className="hidden md:inline text-ink-muted">— no missing-data markers across generated drafts.</span>
        </div>
        <span className="chip chip-neutral font-mono">0 open</span>
      </div>
    );
  }

  return (
    <section className="mb-6 rounded-lg border-2 border-warning bg-warning-soft text-ink p-5" aria-labelledby="oq-heading">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-warning text-ink-inverse flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <h2 id="oq-heading" className="text-base sm:text-lg font-bold tracking-tight">
              {questions.length} open information gap{questions.length === 1 ? '' : 's'} need{questions.length === 1 ? 's' : ''} attention
            </h2>
            <p className="text-sm text-ink-muted mt-0.5">The model flagged missing facts or strategic decisions. Add a resolution to clear the marker and regenerate the section.</p>
          </div>
        </div>
        <button type="button" onClick={onToggle} className="btn-icon" aria-expanded={expanded} aria-controls="oq-list" aria-label={expanded ? 'Collapse open questions' : 'Expand open questions'}>
          {expanded ? <ChevronUp className="w-5 h-5" aria-hidden="true" /> : <ChevronDown className="w-5 h-5" aria-hidden="true" />}
        </button>
      </div>

      {expanded && (
        <ul id="oq-list" className="mt-5 pt-4 border-t border-warning/40 space-y-4">
          {questions.map((q) => {
            const targetSec = sections.find((s) => s.id === q.section_id);
            const secLabel = targetSec ? targetSec.heading : `Section #${q.section_id}`;
            const isResolving = Boolean(resolving[q.id]);
            const inputId = `res-input-${q.id}`;
            return (
              <li key={q.id} className="bg-surface rounded-md border border-border-strong p-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                  <button type="button" onClick={() => onJump(q.section_id)} className="inline-flex items-center gap-1 text-xs font-bold text-accent underline underline-offset-2 self-start">
                    <CornerDownRight className="w-3.5 h-3.5" aria-hidden="true" />
                    <span>Jump to {secLabel}</span>
                  </button>
                  <span className="text-xs text-ink-muted font-mono">Q#{q.id}</span>
                </div>
                <blockquote className="text-sm font-semibold text-ink mb-3 sub-card">{q.question}</blockquote>
                <label htmlFor={inputId} className="field-label">
                  Resolution & evidence
                </label>
                <textarea
                  id={inputId}
                  rows={2}
                  value={inputs[q.id] || ''}
                  onChange={(e) => onInputChange(q.id, e.target.value)}
                  placeholder="Enter the facts, team decision, or client evidence that resolves this gap…"
                  className="input-field"
                />
                <div className="flex justify-end mt-2">
                  <button type="button" onClick={() => onResolve(q.id, q.section_id)} disabled={isResolving || !(inputs[q.id] || '').trim()} className="btn-primary text-xs">
                    {isResolving ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" /> : <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />}
                    <span>{isResolving ? 'Resolving & regenerating…' : 'Resolve & regenerate section'}</span>
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
