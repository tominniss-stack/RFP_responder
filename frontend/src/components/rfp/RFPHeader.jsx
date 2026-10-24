import React from 'react';
import { Edit3, FileText, Loader2, Sparkles, Layers } from 'lucide-react';
import { StatusBadge, DeadlineBadge, BudgetTypeBadge, formatGBP } from '../Badge';

export default function RFPHeader({ rfp, sectionCount, busy, onEditDetails, onExport, onGenerateAll, onClassify, batchProgress }) {
  const { isExporting, isClassifying, batchGenerating } = busy;
  const anyBusy = isExporting || isClassifying || batchGenerating;

  return (
    <div className="card mb-6">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-border pb-6 mb-6">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3 mb-1">
            <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">{rfp.client_name}</h1>
            <StatusBadge status={rfp.status || 'draft'} />
            <button type="button" onClick={onEditDetails} className="btn-ghost text-xs border border-border-strong">
              <Edit3 className="w-3 h-3" aria-hidden="true" />
              <span>Edit details</span>
            </button>
          </div>
          <p className="text-xs text-ink-muted font-mono">
            RFP #{rfp.id} · Created {rfp.created_at ? new Date(rfp.created_at).toLocaleDateString('en-GB') : 'recently'}
            {rfp.source_document && ` · ${rfp.source_document}`}
            {rfp.hubspot_deal_id && ` · HubSpot deal ${rfp.hubspot_deal_id}`}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={onClassify} disabled={anyBusy || sectionCount === 0} className="btn-secondary">
            {isClassifying ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <Layers className="w-4 h-4" aria-hidden="true" />}
            <span>{isClassifying ? 'Classifying…' : 'Classify sections'}</span>
          </button>
          <button type="button" onClick={onGenerateAll} disabled={anyBusy || sectionCount === 0} className="btn-secondary">
            {batchGenerating ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <Sparkles className="w-4 h-4" aria-hidden="true" />}
            <span>
              {batchGenerating && batchProgress ? `Drafting ${batchProgress.done}/${batchProgress.total}…` : 'Generate all drafts'}
            </span>
          </button>
          <button type="button" onClick={onExport} disabled={anyBusy || sectionCount === 0} className="btn-primary">
            {isExporting ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <FileText className="w-4 h-4" aria-hidden="true" />}
            <span>{isExporting ? 'Exporting…' : 'Export to Google Doc'}</span>
          </button>
        </div>
      </div>

      {batchGenerating && batchProgress && (
        <div className="mb-6" role="progressbar" aria-valuemin={0} aria-valuemax={batchProgress.total} aria-valuenow={batchProgress.done} aria-label="Batch draft progress">
          <div className="h-1.5 w-full bg-surface-raised rounded-full overflow-hidden">
            <div className="h-full bg-accent transition-all" style={{ width: `${Math.round((batchProgress.done / Math.max(batchProgress.total, 1)) * 100)}%` }} />
          </div>
        </div>
      )}

      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div>
          <dt className="field-label">Estimated budget</dt>
          <dd className="flex flex-wrap items-center gap-1.5">
            <span className="text-base font-bold font-mono text-ink">{formatGBP(rfp.value)}</span>
            <BudgetTypeBadge type={rfp.budget_type || 'fixed'} />
          </dd>
          {rfp.budget_notes && (
            <dd className="help-text mt-1 italic truncate" title={rfp.budget_notes}>
              {rfp.budget_notes}
            </dd>
          )}
        </div>
        <div>
          <dt className="field-label">Submission deadline</dt>
          <dd>
            <DeadlineBadge deadline={rfp.deadline} />
          </dd>
        </div>
        <div>
          <dt className="field-label">Submitted</dt>
          <dd className="text-sm font-semibold text-ink">{rfp.date_submitted ? new Date(rfp.date_submitted).toLocaleDateString('en-GB') : 'Not submitted'}</dd>
        </div>
        <div>
          <dt className="field-label">Services</dt>
          <dd className="flex flex-wrap gap-1.5">
            {Array.isArray(rfp.services) && rfp.services.length > 0 ? (
              rfp.services.map((svc, idx) => (
                <span key={idx} className="chip chip-neutral">
                  {typeof svc === 'object' ? svc.name : svc}
                </span>
              ))
            ) : (
              <span className="help-text">None assigned</span>
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}
