import React from 'react';
import { FileText, BookOpen, Copy, AlertTriangle, CheckCircle2, Clock, Calendar, AlertCircle, Cpu, Sparkles } from 'lucide-react';

/**
 * Badge variants map to the semantic chip classes defined in index.css.
 * Colour meaning is fixed across the app:
 *   warning  → gaps, open questions, pending / needs attention
 *   success  → won, resolved
 *   danger   → lost, overdue, destructive
 *   info     → submitted / in-flight with a third party
 *   accent   → brand highlight (active, primary emphasis)
 *   neutral  → everything else
 *   solid    → high-emphasis monochrome (strategic, notes provenance)
 */
export const CHIP = {
  neutral: 'chip chip-neutral',
  accent: 'chip chip-accent',
  success: 'chip chip-success',
  warning: 'chip chip-warning',
  danger: 'chip chip-danger',
  info: 'chip chip-info',
  solid: 'chip chip-solid',
};

export function Chip({ variant = 'neutral', icon: Icon, children, className = '', title }) {
  return (
    <span title={title} className={`${CHIP[variant] || CHIP.neutral} ${className}`}>
      {Icon && <Icon className="w-3 h-3 flex-shrink-0" aria-hidden="true" />}
      <span>{children}</span>
    </span>
  );
}

export function normalizeClassification(raw) {
  if (!raw) return 'boilerplate';
  return String(raw).toLowerCase().trim().replace(/[\s-]/g, '_');
}

/** Pound Sterling glyph sized like a lucide icon */
export function PoundIcon({ className = 'w-3 h-3' }) {
  return (
    <span className={`font-bold inline-flex items-center justify-center leading-none ${className}`} aria-hidden="true">
      £
    </span>
  );
}

/** Format numeric amount as GBP (£) */
export function formatGBP(amount) {
  if (amount === null || amount === undefined || isNaN(Number(amount))) {
    return '—';
  }
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'GBP',
    maximumFractionDigits: 0,
  }).format(Number(amount));
}

/** Open questions count — warning is the single "needs attention" colour */
export function OpenQuestionBadge({ count = 0, className = '' }) {
  const num = Number(count) || 0;
  if (num === 0) {
    return (
      <Chip variant="neutral" icon={CheckCircle2} className={className}>
        No gaps
      </Chip>
    );
  }
  return (
    <Chip variant="warning" icon={AlertTriangle} className={`font-semibold ${className}`}>
      {num} open question{num === 1 ? '' : 's'}
    </Chip>
  );
}

/** Deadline with urgency states */
export function DeadlineBadge({ deadline, className = '' }) {
  if (!deadline) {
    return (
      <span className="text-ink-muted text-xs font-mono" aria-label="No deadline">
        —
      </span>
    );
  }
  const d = new Date(deadline);
  if (isNaN(d.getTime())) {
    return <span className="text-ink-muted text-xs">{deadline}</span>;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(d);
  target.setHours(0, 0, 0, 0);
  const diffDays = Math.ceil((target.getTime() - today.getTime()) / 86400000);
  const dateFormatted = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

  if (diffDays < 0) {
    return (
      <Chip variant="danger" icon={AlertCircle} className={`font-semibold ${className}`} title={`Deadline passed on ${dateFormatted}`}>
        Overdue · {dateFormatted}
      </Chip>
    );
  }
  if (diffDays === 0) {
    return (
      <Chip variant="warning" icon={Clock} className={`font-semibold ${className}`} title="Due today">
        Due today
      </Chip>
    );
  }
  if (diffDays <= 3) {
    return (
      <Chip variant="warning" icon={Clock} className={className} title={`Due ${dateFormatted}`}>
        Due in {diffDays}d
      </Chip>
    );
  }
  return (
    <Chip variant="neutral" icon={Calendar} className={className}>
      {dateFormatted}
    </Chip>
  );
}

/** Budget type — monochrome, differentiated by label only */
export function BudgetTypeBadge({ type, notes, className = '' }) {
  const norm = (type || 'fixed').toLowerCase().trim();
  const labels = {
    fixed: 'Fixed budget',
    under_budget: 'Target: under budget',
    unknown: 'Budget TBD',
    retainer: 'Monthly retainer',
    time_and_materials: 'Time & materials',
  };
  return (
    <Chip variant="neutral" className={className} title={notes || labels[norm] || labels.fixed}>
      {labels[norm] || labels.fixed}
    </Chip>
  );
}

export function ClassificationBadge({ classification }) {
  const norm = normalizeClassification(classification);
  const config = {
    gap: { variant: 'warning', label: 'Information gap' },
    strategic_decision: { variant: 'solid', label: 'Strategic decision' },
    strategic: { variant: 'solid', label: 'Strategic decision' },
    pricing: { variant: 'accent', label: 'Pricing' },
    compliance_admin: { variant: 'neutral', label: 'Compliance / admin' },
    boilerplate: { variant: 'neutral', label: 'Boilerplate' },
  };
  const item = config[norm] || { variant: 'neutral', label: classification || 'Boilerplate' };
  return (
    <Chip variant={item.variant} className="font-semibold">
      {item.label}
    </Chip>
  );
}

/** RFP / section status */
export function StatusBadge({ status, className = '' }) {
  const norm = (status || 'draft').toLowerCase().trim();
  const config = {
    won: { variant: 'success', icon: CheckCircle2, bold: true },
    resolved: { variant: 'success', icon: CheckCircle2 },
    pending: { variant: 'warning', icon: Clock },
    lost: { variant: 'danger', icon: AlertCircle },
    'no decision': { variant: 'neutral' },
    submitted: { variant: 'info' },
    draft: { variant: 'neutral' },
    drafted: { variant: 'neutral' },
  };
  const item = config[norm] || config.draft;
  return (
    <Chip variant={item.variant} icon={item.icon} className={`capitalize ${item.bold ? 'font-bold' : ''} ${className}`}>
      {status || 'Draft'}
    </Chip>
  );
}

/** Proposal outcome */
export function OutcomeBadge({ outcome, className = '' }) {
  const norm = (outcome || 'pending').toLowerCase().trim();
  if (norm === 'won') {
    return (
      <Chip variant="success" icon={CheckCircle2} className={`font-bold ${className}`}>
        Won
      </Chip>
    );
  }
  if (norm === 'lost') {
    return (
      <Chip variant="danger" icon={AlertCircle} className={`font-semibold ${className}`}>
        Lost
      </Chip>
    );
  }
  if (['abandoned', 'no decision', 'no_decision', 'cancelled'].includes(norm)) {
    return (
      <Chip variant="neutral" className={className}>
        No decision
      </Chip>
    );
  }
  if (norm === 'n/a') {
    return (
      <Chip variant="neutral" className={`uppercase tracking-wider ${className}`}>
        N/A
      </Chip>
    );
  }
  return (
    <Chip variant="warning" icon={Clock} className={className}>
      Pending
    </Chip>
  );
}

/**
 * Content provenance — where each part of a draft came from.
 */
export function ProvenanceBadge({ source, label, className = '' }) {
  const norm = (source || '').toLowerCase().trim();
  const config = {
    notes: { variant: 'solid', label: 'AM notes', icon: FileText, tooltip: 'Generated from account manager notes and guidance' },
    rag: { variant: 'accent', label: 'Knowledge base (RAG)', icon: BookOpen, tooltip: 'Retrieved from past proposals and case studies' },
    boilerplate: { variant: 'neutral', label: 'Boilerplate', icon: Copy, tooltip: 'Standard company credentials and boilerplate' },
    pricing: { variant: 'accent', label: 'Structured pricing', icon: PoundIcon, tooltip: 'Reproduced verbatim from the pricing rate card' },
    gap: { variant: 'warning', label: 'Information gap', icon: AlertTriangle, tooltip: 'Missing evidence requiring resolution' },
  };
  const item = config[norm] || { variant: 'neutral', label: label || source || 'Source', icon: FileText, tooltip: 'Source content' };
  return (
    <Chip variant={item.variant} icon={item.icon} className={`font-semibold ${className}`} title={item.tooltip}>
      {label || item.label}
    </Chip>
  );
}

/** Which engine produced a result — never hide mock output */
export function EngineBadge({ engine, model, className = '' }) {
  const norm = (engine || 'mock').toLowerCase();
  if (norm === 'mock') {
    return (
      <Chip variant="warning" icon={Cpu} className={className} title="Deterministic offline mock — no LLM API was called">
        Mock engine
      </Chip>
    );
  }
  const label = norm === 'claude' ? 'Claude' : norm === 'gemini' ? 'Gemini' : engine;
  return (
    <Chip variant="accent" icon={Sparkles} className={className} title={model ? `Model: ${model}` : undefined}>
      {label}
      {model ? ` · ${model}` : ''}
    </Chip>
  );
}

export function DocumentTypeBadge({ type }) {
  const norm = (type || 'boilerplate').toLowerCase().trim();
  const config = {
    past_proposal: { variant: 'accent', label: 'Past proposal' },
    case_study: { variant: 'solid', label: 'Case study' },
    testimonial: { variant: 'neutral', label: 'Testimonial' },
    pitch_deck: { variant: 'neutral', label: 'Pitch deck' },
    boilerplate: { variant: 'neutral', label: 'Boilerplate' },
  };
  const item = config[norm] || { variant: 'neutral', label: type };
  return <Chip variant={item.variant}>{item.label}</Chip>;
}

export function PricingUnitBadge({ unit }) {
  const norm = (unit || 'fixed').toLowerCase().trim();
  const config = {
    'day rate': 'neutral',
    fixed: 'solid',
    'monthly retainer': 'accent',
  };
  return (
    <Chip variant={config[norm] || 'neutral'} className="font-mono">
      {unit}
    </Chip>
  );
}
