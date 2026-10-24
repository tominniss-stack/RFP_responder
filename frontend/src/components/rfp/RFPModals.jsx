import React from 'react';
import { ArrowUpRight, FileText, Loader2, Plus, Save } from 'lucide-react';
import Modal from '../Modal';

export function EditDetailsModal({ open, onClose, form, onChange, saving, onSubmit }) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Edit RFP details"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button type="submit" form="edit-details-form" disabled={saving} className="btn-primary">
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" /> : <Save className="w-3.5 h-3.5" aria-hidden="true" />}
            <span>{saving ? 'Saving…' : 'Save changes'}</span>
          </button>
        </>
      }
    >
      <form id="edit-details-form" onSubmit={onSubmit} className="space-y-4">
        <div>
          <label htmlFor="ed-client" className="field-label">
            Client / opportunity name <span className="text-danger" aria-hidden="true">*</span>
          </label>
          <input id="ed-client" type="text" required aria-required="true" value={form.client_name} onChange={(e) => onChange({ client_name: e.target.value })} className="input-field" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="ed-value" className="field-label">
              Estimated budget (£)
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted text-sm" aria-hidden="true">
                £
              </span>
              <input id="ed-value" type="number" step="100" value={form.value} onChange={(e) => onChange({ value: e.target.value })} placeholder="25000" className="input-field pl-8 font-mono" />
            </div>
          </div>
          <div>
            <label htmlFor="ed-budget-type" className="field-label">
              Budget type
            </label>
            <select id="ed-budget-type" value={form.budget_type} onChange={(e) => onChange({ budget_type: e.target.value })} className="input-field">
              <option value="fixed">Fixed budget</option>
              <option value="under_budget">Target under budget</option>
              <option value="unknown">Unknown / not disclosed</option>
              <option value="retainer">Monthly retainer</option>
              <option value="time_and_materials">Time & materials</option>
            </select>
          </div>
        </div>
        <div>
          <label htmlFor="ed-budget-notes" className="field-label">
            Budget notes
          </label>
          <textarea id="ed-budget-notes" rows={2} value={form.budget_notes} onChange={(e) => onChange({ budget_notes: e.target.value })} placeholder="e.g. Client budget capped at £30k; target £24–26k." className="input-field" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="ed-deadline" className="field-label">
              Submission deadline
            </label>
            <input id="ed-deadline" type="date" value={form.deadline || ''} onChange={(e) => onChange({ deadline: e.target.value })} className="input-field" />
          </div>
          <div>
            <label htmlFor="ed-status" className="field-label">
              Status
            </label>
            <select id="ed-status" value={form.status} onChange={(e) => onChange({ status: e.target.value })} className="input-field">
              <option value="draft">Draft</option>
              <option value="pending">Pending</option>
              <option value="submitted">Submitted</option>
              <option value="won">Won</option>
              <option value="lost">Lost</option>
              <option value="no decision">No decision</option>
            </select>
          </div>
        </div>
        <div>
          <label htmlFor="ed-hubspot" className="field-label">
            HubSpot deal ID <span className="normal-case font-normal text-ink-muted">(optional)</span>
          </label>
          <input id="ed-hubspot" type="text" value={form.hubspot_deal_id || ''} onChange={(e) => onChange({ hubspot_deal_id: e.target.value })} placeholder="e.g. 1928471928" className="input-field font-mono" aria-describedby="ed-hubspot-help" />
          <p id="ed-hubspot-help" className="help-text mt-1">
            Links this proposal to a CRM deal so lifecycle status can sync to the pipeline stage.
          </p>
        </div>
        <div>
          <label htmlFor="ed-feedback" className="field-label">
            Outcome feedback
          </label>
          <textarea id="ed-feedback" rows={2} value={form.outcome_feedback} onChange={(e) => onChange({ outcome_feedback: e.target.value })} placeholder="Reasons for the decision or client feedback…" className="input-field" />
        </div>
      </form>
    </Modal>
  );
}

export function AddSectionModal({ open, onClose, form, onChange, saving, onSubmit }) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add custom section"
      size="sm"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button type="submit" form="add-section-form" disabled={saving || !form.heading.trim()} className="btn-primary">
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" /> : <Plus className="w-3.5 h-3.5" aria-hidden="true" />}
            <span>{saving ? 'Adding…' : 'Add section'}</span>
          </button>
        </>
      }
    >
      <form id="add-section-form" onSubmit={onSubmit} className="space-y-4">
        <div>
          <label htmlFor="as-heading" className="field-label">
            Section heading <span className="text-danger" aria-hidden="true">*</span>
          </label>
          <input id="as-heading" type="text" required aria-required="true" value={form.heading} onChange={(e) => onChange({ heading: e.target.value })} placeholder="e.g. 4. Technical architecture & hosting" className="input-field" />
        </div>
        <div>
          <label htmlFor="as-class" className="field-label">
            Classification
          </label>
          <select id="as-class" value={form.classification} onChange={(e) => onChange({ classification: e.target.value })} className="input-field">
            <option value="strategic_decision">Strategic decision</option>
            <option value="pricing">Pricing</option>
            <option value="boilerplate">Boilerplate</option>
            <option value="gap">Information gap</option>
            <option value="compliance_admin">Compliance / admin</option>
          </select>
        </div>
        <div>
          <label htmlFor="as-text" className="field-label">
            Original requirement <span className="normal-case font-normal text-ink-muted">(optional)</span>
          </label>
          <textarea id="as-text" rows={3} value={form.original_text} onChange={(e) => onChange({ original_text: e.target.value })} placeholder="Paste the client's requirement for this section…" className="input-field" />
        </div>
      </form>
    </Modal>
  );
}

export function ExportSuccessModal({ result, onClose }) {
  return (
    <Modal
      open={Boolean(result)}
      onClose={onClose}
      title="Export complete"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary">
            Close
          </button>
          {result?.docUrl && (
            <a href={result.docUrl} target="_blank" rel="noopener noreferrer" className="btn-primary">
              <span>Open Google Doc</span>
              <ArrowUpRight className="w-3.5 h-3.5" aria-hidden="true" />
            </a>
          )}
        </>
      }
    >
      {result && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-accent-soft text-accent flex items-center justify-center flex-shrink-0">
              <FileText className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm text-ink">
                <strong>{result.docTitle}</strong> has been processed.
              </p>
              <span className={`chip ${result.mode === 'mock' ? 'chip-warning' : 'chip-success'} mt-1`}>{result.mode === 'mock' ? 'Mock / dry-run' : 'Live Google Docs'}</span>
            </div>
          </div>
          {result.commentCount > 0 && (
            <p className="text-xs text-ink bg-warning-soft border border-warning/50 p-2.5 rounded">
              {result.commentCount} unresolved information gap{result.commentCount === 1 ? ' was' : 's were'} anchored as margin comments for reviewer attention.
            </p>
          )}
          <div className="sub-card">
            <p className="field-label">Document URL</p>
            <a href={result.docUrl} target="_blank" rel="noopener noreferrer" className="text-xs font-mono text-accent hover:underline break-all block">
              {result.docUrl}
            </a>
          </div>
          {result.mode === 'mock' && (
            <p className="help-text">
              The simulated payload was written to <code className="font-mono bg-surface-raised px-1 rounded">backend/data/exports/</code>. Configure Google credentials in Settings to export live.
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
