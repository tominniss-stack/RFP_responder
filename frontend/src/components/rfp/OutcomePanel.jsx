import React from 'react';
import { CheckCircle2, Loader2, Save } from 'lucide-react';

const OPTIONS = [
  { id: 'won', label: 'Won', desc: 'Boosts future retrieval', cls: 'bg-success text-ink-inverse border-success' },
  { id: 'lost', label: 'Lost', desc: 'Discounted in retrieval', cls: 'bg-danger text-ink-inverse border-danger' },
  { id: 'pending', label: 'Pending decision', desc: 'Awaiting client', cls: 'bg-accent text-accent-ink border-accent' },
  { id: 'no decision', label: 'No decision', desc: 'Cancelled or shelved', cls: 'bg-ink text-ink-inverse border-ink' },
];

export default function OutcomePanel({ selection, onSelect, feedback, onFeedbackChange, saving, onSave }) {
  return (
    <section className="card mb-6" aria-labelledby="outcome-heading">
      <div className="flex items-center gap-2 border-b border-border pb-3 mb-4">
        <CheckCircle2 className="w-5 h-5 text-accent" aria-hidden="true" />
        <h2 id="outcome-heading" className="text-base font-bold text-ink">
          Outcome & feedback
        </h2>
      </div>

      <fieldset className="mb-4">
        <legend className="field-label mb-2">Proposal outcome</legend>
        <div className="flex flex-wrap gap-2">
          {OPTIONS.map((opt) => {
            const active = selection === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => onSelect(opt.id)}
                title={opt.desc}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition-colors ${active ? opt.cls : 'bg-surface text-ink border-border-strong hover:bg-surface-raised'}`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </fieldset>

      <div>
        <label htmlFor="outcome-feedback" className="field-label">
          Client feedback & decision notes
        </label>
        <p className="help-text mb-2">Reasons for the award or loss, evaluation scores, or competitor pricing — this improves future retrieval.</p>
        <textarea
          id="outcome-feedback"
          rows={3}
          value={feedback}
          onChange={(e) => onFeedbackChange(e.target.value)}
          placeholder="e.g. Client chose us for the headless CMS approach and accessibility credentials; pricing was within 5% of the nearest competitor."
          className="input-field"
        />
      </div>

      <div className="flex justify-end mt-4">
        <button type="button" onClick={onSave} disabled={saving} className="btn-dark text-xs">
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" /> : <Save className="w-3.5 h-3.5" aria-hidden="true" />}
          <span>{saving ? 'Saving…' : 'Save outcome'}</span>
        </button>
      </div>
    </section>
  );
}
