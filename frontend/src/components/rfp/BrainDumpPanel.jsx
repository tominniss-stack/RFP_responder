import React from 'react';
import { ChevronDown, ChevronUp, Edit3, Loader2, MessageSquare, Plus, Trash2 } from 'lucide-react';

export default function BrainDumpPanel({ notes, expanded, onToggle, text, onTextChange, saving, onSave, onDeleteNote }) {
  return (
    <section className="card mb-6" aria-labelledby="braindump-heading">
      <div className="flex items-center justify-between border-b border-border pb-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-accent-soft text-accent flex items-center justify-center">
            <Edit3 className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 id="braindump-heading" className="text-base font-bold text-ink">
                Account manager brain dump
              </h2>
              <span className="chip chip-neutral">
                {notes.length} note{notes.length === 1 ? '' : 's'}
              </span>
            </div>
            <p className="help-text">Global priorities, call notes and commercial instructions injected into every section's draft prompt.</p>
          </div>
        </div>
        <button type="button" onClick={onToggle} className="btn-icon" aria-expanded={expanded} aria-controls="braindump-body" aria-label={expanded ? 'Collapse brain dump' : 'Expand brain dump'}>
          {expanded ? <ChevronUp className="w-5 h-5" aria-hidden="true" /> : <ChevronDown className="w-5 h-5" aria-hidden="true" />}
        </button>
      </div>

      {expanded && (
        <div id="braindump-body" className="space-y-4">
          {notes.length > 0 && (
            <ul className="space-y-2">
              {notes.map((note) => (
                <li key={note.id} className="sub-card flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2">
                    <MessageSquare className="w-4 h-4 text-ink-muted mt-0.5 flex-shrink-0" aria-hidden="true" />
                    <p className="whitespace-pre-wrap leading-relaxed">{note.raw_content}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-xs text-ink-muted font-mono">{note.created_at ? new Date(note.created_at).toLocaleDateString('en-GB') : ''}</span>
                    <button type="button" onClick={() => onDeleteNote(note.id)} className="btn-icon p-1 hover:text-danger" aria-label="Delete note">
                      <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={onSave} className="space-y-3">
            <label htmlFor="brain-dump-input" className="field-label">
              Add a note or transcript excerpt
            </label>
            <textarea
              id="brain-dump-input"
              rows={3}
              value={text}
              onChange={(e) => onTextChange(e.target.value)}
              placeholder="e.g. Emphasise accessibility compliance, strict 12-week launch, and a 10% discount on the discovery sprint…"
              className="input-field"
            />
            <div className="flex justify-end">
              <button type="submit" disabled={saving || !text.trim()} className="btn-dark text-xs">
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" /> : <Plus className="w-3.5 h-3.5" aria-hidden="true" />}
                <span>{saving ? 'Saving…' : 'Save note'}</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
