import React from 'react';
import { AlertTriangle, ArrowDown, ArrowUp, Check, ChevronDown, Copy, Edit3, Loader2, MessageSquare, RefreshCw, Sparkles, Trash2 } from 'lucide-react';
import { ClassificationBadge, ProvenanceBadge, EngineBadge, normalizeClassification } from '../Badge';
import { MarkdownRenderer, MarkdownToolbar } from '../MarkdownRenderer';

const PRICING_RE = /(?:£\s*\d[\d,]*(?:\.\d{2})?|\bday rate:\s*£|\bhourly rate:\s*£|\bmonthly retainer:\s*£)/i;
const NOTES_RE = /Commercial terms note:|Delivery instruction:|Context note:|Special requirement note:|Resolved requirement:/i;

/** Heuristic provenance detection when the generation response is not in memory (e.g. after reload). */
export function detectProvenanceSources(section, notes = []) {
  const sources = new Set();
  const draft = section.draft_content || '';
  const normCat = normalizeClassification(section.classification);

  if (draft.includes('[MORE INFO REQUIRED:') || normCat === 'gap') sources.add('gap');
  if (normCat === 'pricing' || (normCat !== 'boilerplate' && PRICING_RE.test(draft))) sources.add('pricing');
  const hasNotes = notes.some((n) => n.section_id === section.id || n.section_id == null);
  if (hasNotes || NOTES_RE.test(draft)) sources.add('notes');
  if (normCat === 'boilerplate' || /company profile|insurance|certifications|accreditation|overview/i.test(draft)) sources.add('boilerplate');
  if (normCat === 'strategic_decision' || normCat === 'strategic' || /methodology|case study|proven experience/i.test(draft)) sources.add('rag');
  return Array.from(sources);
}

function AnnotatedDraft({ draft, normCat }) {
  return (
    <div className="bg-surface border border-border-strong rounded p-4 text-sm text-ink leading-relaxed whitespace-pre-wrap">
      {draft.split('\n\n').map((para, pIdx) => {
        if (para.includes('[MORE INFO REQUIRED:')) {
          return (
            <div key={pIdx} className="my-2 p-3 bg-warning-soft border-l-4 border-warning rounded-r">
              <div className="flex items-center gap-1.5 mb-1 text-xs font-bold uppercase tracking-wider text-ink">
                <AlertTriangle className="w-3.5 h-3.5 text-warning" aria-hidden="true" />
                <span>Information gap</span>
              </div>
              <p className="text-sm font-semibold">{para}</p>
            </div>
          );
        }
        const isPricing = normCat === 'pricing' || (normCat !== 'boilerplate' && PRICING_RE.test(para));
        if (isPricing) {
          return (
            <div key={pIdx} className="my-2 p-3 bg-accent-soft border border-accent/40 rounded font-mono text-xs sm:text-sm">
              <div className="mb-1">
                <ProvenanceBadge source="pricing" />
              </div>
              <p>{para}</p>
            </div>
          );
        }
        if (NOTES_RE.test(para)) {
          return (
            <div key={pIdx} className="my-2 p-3 bg-surface-raised border-l-4 border-ink rounded-r">
              <div className="mb-1">
                <ProvenanceBadge source="notes" />
              </div>
              <p>{para}</p>
            </div>
          );
        }
        return (
          <p key={pIdx} className="mb-2">
            {para}
          </p>
        );
      })}
    </div>
  );
}

export default function SectionCard({
  section,
  index,
  isFirst,
  isLast,
  notes,
  openQuestions,
  provenance,
  engine,
  busy,
  ui,
  actions,
  innerRef,
}) {
  const normCat = normalizeClassification(section.classification);
  const sectionNotes = notes.filter((n) => n.section_id === section.id);
  const sectionOpenQuestions = openQuestions.filter((q) => q.section_id === section.id && q.status === 'open');
  const activeSources = provenance ? provenance.map((p) => p.source) : detectProvenanceSources(section, notes);
  const viewMode = ui.viewMode || 'draft';
  const editorValue = ui.editorContent !== undefined ? ui.editorContent : section.final_content || section.draft_content || '';
  const headingId = `section-heading-${section.id}`;

  return (
    <article ref={innerRef} id={`section-${section.id}`} aria-labelledby={headingId} className="card scroll-mt-24 transition-shadow">
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4 mb-4">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="inline-flex items-center border border-border-strong rounded overflow-hidden">
            <button type="button" onClick={() => actions.move(section.id, 'up')} disabled={isFirst} className="btn-icon rounded-none min-w-[28px] min-h-[28px] p-1.5 disabled:opacity-30" aria-label={`Move section ${section.heading} up`}>
              <ArrowUp className="w-4 h-4" aria-hidden="true" />
            </button>
            <button type="button" onClick={() => actions.move(section.id, 'down')} disabled={isLast} className="btn-icon rounded-none min-w-[28px] min-h-[28px] p-1.5 border-l border-border-strong disabled:opacity-30" aria-label={`Move section ${section.heading} down`}>
              <ArrowDown className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
          <span className="font-mono text-xs font-bold text-ink-muted bg-surface-raised px-2 py-1 rounded">#{section.sort_order || index + 1}</span>
          <h3 id={headingId} className="text-base sm:text-lg font-bold text-ink truncate">
            {section.heading || `Section ${index + 1}`}
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
          <div className="relative inline-flex items-center">
            <label htmlFor={`status-${section.id}`} className="sr-only">
              Status for {section.heading}
            </label>
            <select id={`status-${section.id}`} value={section.status || 'pending'} disabled={busy.saving} onChange={(e) => actions.changeStatus(section.id, e.target.value)} className="input-field w-auto text-xs font-semibold py-1 pr-7 appearance-none">
              <option value="pending">Pending</option>
              <option value="drafted">Drafted</option>
              <option value="resolved">Resolved</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-ink-muted absolute right-2 pointer-events-none" aria-hidden="true" />
          </div>

          <ClassificationBadge classification={section.classification} />

          <div className="relative inline-flex items-center">
            <label htmlFor={`class-${section.id}`} className="sr-only">
              Classification for {section.heading}
            </label>
            <select id={`class-${section.id}`} value={normCat} disabled={busy.saving} onChange={(e) => actions.changeClassification(section.id, e.target.value)} className="input-field w-auto text-xs font-semibold py-1 pr-7 appearance-none">
              <option value="boilerplate">Boilerplate</option>
              <option value="pricing">Pricing</option>
              <option value="strategic_decision">Strategic decision</option>
              <option value="gap">Information gap</option>
              <option value="compliance_admin">Compliance / admin</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-ink-muted absolute right-2 pointer-events-none" aria-hidden="true" />
          </div>

          <button type="button" onClick={() => actions.toggleNotes(section.id)} aria-expanded={ui.notesExpanded} aria-controls={`notes-${section.id}`} className={`chip ${sectionNotes.length > 0 ? 'chip-solid' : 'chip-neutral'} hover:opacity-90`}>
            <MessageSquare className="w-3 h-3" aria-hidden="true" />
            <span>Notes ({sectionNotes.length})</span>
          </button>

          <button type="button" onClick={() => actions.generate(section.id)} disabled={busy.drafting} className={`${section.draft_content ? 'btn-secondary' : 'btn-primary'} text-xs py-1`}>
            {busy.drafting ? <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" /> : section.draft_content ? <RefreshCw className="w-3 h-3" aria-hidden="true" /> : <Sparkles className="w-3 h-3" aria-hidden="true" />}
            <span>{busy.drafting ? 'Drafting…' : section.draft_content ? 'Regenerate' : 'Generate draft'}</span>
          </button>

          <button type="button" onClick={() => actions.remove(section.id, section.heading)} disabled={busy.deleting} className="btn-icon hover:text-danger" aria-label={`Delete section ${section.heading}`}>
            {busy.deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" /> : <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />}
          </button>
        </div>
      </header>

      <div className="mb-4">
        <p className="field-label">Original RFP requirement</p>
        <div className="sub-card whitespace-pre-wrap leading-relaxed">{section.original_text || 'No requirement text provided.'}</div>
      </div>

      {ui.notesExpanded && (
        <div id={`notes-${section.id}`} className="mb-4 sub-card">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold text-ink uppercase tracking-wider inline-flex items-center gap-2">
              <Edit3 className="w-4 h-4 text-accent" aria-hidden="true" />
              Section-specific guidance
            </span>
            <span className="help-text">Takes precedence over global notes</span>
          </div>
          {sectionNotes.length > 0 ? (
            <ul className="space-y-2 mb-3">
              {sectionNotes.map((n) => (
                <li key={n.id} className="bg-surface border border-border rounded p-2.5 text-sm text-ink flex items-center justify-between gap-2">
                  <span>{n.raw_content}</span>
                  <button type="button" onClick={() => actions.deleteNote(n.id)} className="btn-icon p-1 hover:text-danger flex-shrink-0" aria-label="Delete note">
                    <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="help-text italic mb-3">No section-specific guidance yet.</p>
          )}
          <label htmlFor={`note-input-${section.id}`} className="sr-only">
            New note for {section.heading}
          </label>
          <textarea id={`note-input-${section.id}`} rows={2} value={ui.noteInput || ''} onChange={(e) => actions.setNoteInput(section.id, e.target.value)} placeholder="e.g. Propose a headless CMS with static rendering; offer a 10% discount…" className="input-field" />
          <div className="flex justify-end mt-2">
            <button type="button" onClick={() => actions.saveNote(section.id)} disabled={busy.savingNote || !(ui.noteInput || '').trim()} className="btn-dark text-xs">
              {busy.savingNote ? 'Saving…' : 'Save note'}
            </button>
          </div>
        </div>
      )}

      {sectionOpenQuestions.length > 0 && (
        <div className="mb-4 border-l-4 border-warning bg-warning-soft rounded-r-md p-4 text-ink">
          <p className="flex items-center gap-2 mb-2 text-xs font-bold uppercase tracking-wider">
            <AlertTriangle className="w-4 h-4 text-warning" aria-hidden="true" />
            Open gap requiring information
          </p>
          {sectionOpenQuestions.map((q) => (
            <div key={q.id} className="space-y-2 mt-2">
              <blockquote className="text-sm font-semibold bg-surface p-2.5 rounded border border-border-strong">{q.question}</blockquote>
              <label htmlFor={`inline-res-${q.id}`} className="sr-only">
                Resolution for question {q.id}
              </label>
              <textarea id={`inline-res-${q.id}`} rows={2} value={ui.resolutionInputs[q.id] || ''} onChange={(e) => actions.setResolutionInput(q.id, e.target.value)} placeholder="Enter the facts that resolve this gap, then regenerate…" className="input-field" />
              <div className="flex justify-end">
                <button type="button" onClick={() => actions.resolve(q.id, section.id)} disabled={busy.resolving[q.id] || !(ui.resolutionInputs[q.id] || '').trim()} className="btn-primary text-xs">
                  {busy.resolving[q.id] ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" /> : <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />}
                  <span>{busy.resolving[q.id] ? 'Regenerating…' : 'Resolve & regenerate'}</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {section.draft_content ? (
        <div className="border-t border-border pt-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="field-label mb-0 mr-1">Provenance</span>
              {activeSources.map((source) => (
                <ProvenanceBadge key={source} source={source} />
              ))}
              {engine && <EngineBadge engine={engine.engine} model={engine.model} />}
            </div>
            <div role="tablist" aria-label="Draft view" className="inline-flex rounded-md border border-border-strong p-0.5 bg-surface-raised">
              <button type="button" role="tab" aria-selected={viewMode === 'draft'} onClick={() => actions.setViewMode(section.id, 'draft')} className={`px-3 py-1 text-xs font-semibold rounded ${viewMode === 'draft' ? 'bg-accent text-accent-ink' : 'text-ink-muted hover:text-ink'}`}>
                Draft & provenance
              </button>
              <button type="button" role="tab" aria-selected={viewMode === 'editor'} onClick={() => actions.setViewMode(section.id, 'editor')} className={`px-3 py-1 text-xs font-semibold rounded ${viewMode === 'editor' ? 'bg-accent text-accent-ink' : 'text-ink-muted hover:text-ink'}`}>
                Editor{section.final_content ? ' · final' : ''}
              </button>
            </div>
          </div>

          {viewMode === 'draft' ? (
            <div className="space-y-3">
              <AnnotatedDraft draft={section.draft_content} normCat={normCat} />
              <div className="flex justify-end">
                <button type="button" onClick={() => actions.startEditing(section)} className="btn-ghost text-xs">
                  <Edit3 className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Edit final version</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between help-text">
                <span className="font-semibold uppercase tracking-wider">Final content editor</span>
                <span>
                  {editorValue.split(/\s+/).filter(Boolean).length} words · {editorValue.length} chars
                </span>
              </div>
              <MarkdownToolbar onInsert={(syntax) => actions.insertMarkdown(section.id, syntax)} isPreview={Boolean(ui.previewMode)} onTogglePreview={() => actions.togglePreview(section.id)} />
              {ui.previewMode ? (
                <div className="bg-surface border border-border-strong rounded-md p-4 min-h-[180px] text-sm leading-relaxed overflow-x-auto">
                  <MarkdownRenderer content={editorValue || '*No content yet.*'} />
                </div>
              ) : (
                <>
                  <label htmlFor={`editor-${section.id}`} className="sr-only">
                    Final content for {section.heading}
                  </label>
                  <textarea id={`editor-${section.id}`} rows={9} value={editorValue} onChange={(e) => actions.setEditorContent(section.id, e.target.value)} placeholder="Edit the final section response. Markdown supported." className="input-field font-mono leading-relaxed" />
                </>
              )}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button type="button" onClick={() => actions.setEditorContent(section.id, section.draft_content)} className="btn-ghost text-xs">
                  <Copy className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Reset to AI draft</span>
                </button>
                <button type="button" onClick={() => actions.saveFinal(section.id)} disabled={busy.savingEditor} className="btn-dark text-xs">
                  {busy.savingEditor ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" /> : <Check className="w-3.5 h-3.5" aria-hidden="true" />}
                  <span>{busy.savingEditor ? 'Saving…' : 'Save final response'}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="border-t border-border pt-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="help-text">No draft generated for this section yet.</p>
          <button type="button" onClick={() => actions.generate(section.id)} disabled={busy.drafting} className="btn-primary text-xs">
            {busy.drafting ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" /> : <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />}
            <span>{busy.drafting ? 'Synthesising context…' : 'Generate first draft'}</span>
          </button>
        </div>
      )}
    </article>
  );
}
