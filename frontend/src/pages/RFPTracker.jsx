import React, { useState, useEffect } from 'react';
import { Plus, Search, ArrowUpRight, FileText } from 'lucide-react';
import { api } from '../services/api';
import { StatusBadge, OpenQuestionBadge, DeadlineBadge, BudgetTypeBadge, formatGBP } from '../components/Badge';

const OUTCOME_STATUSES = ['won', 'lost', 'no decision'];

export default function RFPTracker({ onSelectRFP, onNewRFP }) {
  const [rfps, setRfps] = useState([]);
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [serviceFilter, setServiceFilter] = useState('all');
  const [valueFilter, setValueFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [outcomeFilter, setOutcomeFilter] = useState('all');

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setLoadError(null);
    try {
      const [rfpsData, servicesData] = await Promise.all([api.getRFPs(), api.getServices().catch(() => [])]);
      setRfps(Array.isArray(rfpsData) ? rfpsData : []);
      setServices(Array.isArray(servicesData) ? servicesData : []);
    } catch (err) {
      setLoadError(err.message || 'Could not load RFPs.');
    } finally {
      setLoading(false);
    }
  }

  const filteredRFPs = rfps.filter((rfp) => {
    const matchesSearch = (rfp.client_name || '').toLowerCase().includes(searchTerm.toLowerCase());

    let matchesService = true;
    if (serviceFilter !== 'all') {
      matchesService = (rfp.services || []).some((s) => {
        if (typeof s === 'object' && s !== null) return String(s.id) === String(serviceFilter) || s.name === serviceFilter;
        const svc = services.find((x) => String(x.id) === String(serviceFilter));
        return String(s) === String(serviceFilter) || (svc && s === svc.name);
      });
    }

    let matchesValue = true;
    const val = Number(rfp.value) || 0;
    if (valueFilter === 'under_25k') matchesValue = val > 0 && val < 25000;
    else if (valueFilter === '25k_50k') matchesValue = val >= 25000 && val <= 50000;
    else if (valueFilter === '50k_100k') matchesValue = val >= 50000 && val <= 100000;
    else if (valueFilter === 'over_100k') matchesValue = val > 100000;

    const status = (rfp.status || '').toLowerCase();
    const matchesStatus = statusFilter === 'all' || status === statusFilter;

    let matchesOutcome = true;
    if (outcomeFilter === 'pending') matchesOutcome = !OUTCOME_STATUSES.includes(status);
    else if (outcomeFilter !== 'all') matchesOutcome = status === outcomeFilter;

    return matchesSearch && matchesService && matchesValue && matchesStatus && matchesOutcome;
  });

  const wonCount = rfps.filter((r) => r.status === 'won').length;
  const decided = rfps.filter((r) => r.status === 'won' || r.status === 'lost').length;
  const winRate = decided ? Math.round((wonCount / decided) * 100) : null;

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">RFP Tracker</h1>
          <p className="mt-1 text-sm text-ink-muted">Monitor, draft and track responses from document intake through to export.</p>
        </div>
        <button type="button" onClick={onNewRFP} className="btn-primary self-start sm:self-auto">
          <Plus className="w-4 h-4" aria-hidden="true" />
          <span>New RFP response</span>
        </button>
      </div>

      <ul className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8 list-none p-0 m-0" aria-label="Pipeline summary">
        <li className="card p-4">
          <p className="field-label mb-0">Total proposals</p>
          <p className="text-2xl font-bold text-ink mt-1">{rfps.length}</p>
        </li>
        <li className="card p-4">
          <p className="field-label mb-0">In progress</p>
          <p className="text-2xl font-bold text-ink mt-1">{rfps.filter((r) => r.status === 'draft' || r.status === 'pending').length}</p>
        </li>
        <li className="card p-4">
          <p className="field-label mb-0">Won{winRate !== null ? ` · ${winRate}% win rate` : ''}</p>
          <p className="text-2xl font-bold text-success mt-1">{wonCount}</p>
        </li>
        <li className="card p-4">
          <p className="field-label mb-0">Open gaps</p>
          <p className={`text-2xl font-bold mt-1 ${rfps.some((r) => r.open_questions_count > 0) ? 'text-warning' : 'text-ink'}`}>
            {rfps.reduce((acc, r) => acc + (r.open_questions_count || 0), 0)}
          </p>
        </li>
      </ul>

      <div className="card mb-6 p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <div className="relative">
            <label htmlFor="tracker-search" className="sr-only">
              Search by client name
            </label>
            <Search className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
            <input
              id="tracker-search"
              type="search"
              placeholder="Search client name…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input-field pl-9"
            />
          </div>

          <div>
            <label htmlFor="tracker-service" className="sr-only">
              Filter by service
            </label>
            <select id="tracker-service" value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} className="input-field">
              <option value="all">All services</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="tracker-value" className="sr-only">
              Filter by budget size
            </label>
            <select id="tracker-value" value={valueFilter} onChange={(e) => setValueFilter(e.target.value)} className="input-field">
              <option value="all">All budget sizes</option>
              <option value="under_25k">Under £25,000</option>
              <option value="25k_50k">£25,000 – £50,000</option>
              <option value="50k_100k">£50,000 – £100,000</option>
              <option value="over_100k">Over £100,000</option>
            </select>
          </div>

          <div>
            <label htmlFor="tracker-status" className="sr-only">
              Filter by status
            </label>
            <select id="tracker-status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="input-field">
              <option value="all">All statuses</option>
              <option value="draft">Draft</option>
              <option value="pending">Pending</option>
              <option value="submitted">Submitted</option>
              <option value="won">Won</option>
              <option value="lost">Lost</option>
              <option value="no decision">No decision</option>
            </select>
          </div>

          <div>
            <label htmlFor="tracker-outcome" className="sr-only">
              Filter by outcome
            </label>
            <select id="tracker-outcome" value={outcomeFilter} onChange={(e) => setOutcomeFilter(e.target.value)} className="input-field">
              <option value="all">All outcomes</option>
              <option value="pending">Outcome pending</option>
              <option value="won">Won</option>
              <option value="lost">Lost</option>
              <option value="no decision">No decision</option>
            </select>
          </div>
        </div>
      </div>

      {loadError && (
        <div role="alert" className="mb-6 p-4 rounded-md bg-danger-soft border border-danger/40 text-sm font-semibold text-ink">
          {loadError}
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">RFP responses</caption>
            <thead className="bg-surface-raised border-b border-border text-xs font-bold text-ink-muted uppercase tracking-wider">
              <tr>
                <th scope="col" className="px-5 py-3.5">
                  Client & scope
                </th>
                <th scope="col" className="px-4 py-3.5">
                  Services
                </th>
                <th scope="col" className="px-4 py-3.5">
                  Budget
                </th>
                <th scope="col" className="px-4 py-3.5">
                  Deadline
                </th>
                <th scope="col" className="px-4 py-3.5">
                  Status
                </th>
                <th scope="col" className="px-4 py-3.5 text-center">
                  Gaps
                </th>
                <th scope="col" className="px-5 py-3.5 text-right">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center text-ink-muted" role="status">
                    Loading RFPs…
                  </td>
                </tr>
              ) : filteredRFPs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-ink-muted">
                    <FileText className="w-8 h-8 mx-auto mb-2" aria-hidden="true" />
                    <p className="font-semibold text-ink">No RFPs found</p>
                    <p className="text-xs mt-1">Create a new RFP response or adjust your filters.</p>
                  </td>
                </tr>
              ) : (
                filteredRFPs.map((rfp) => (
                  <tr key={rfp.id} className="hover:bg-surface-raised/60 transition-colors">
                    <td className="px-5 py-4">
                      <a
                        href={`#/rfp/${rfp.id}`}
                        onClick={(e) => {
                          e.preventDefault();
                          onSelectRFP?.(rfp.id);
                        }}
                        className="font-semibold text-ink hover:text-accent block rounded"
                      >
                        {rfp.client_name}
                      </a>
                      <span className="text-xs text-ink-muted">
                        {rfp.sections_count || 0} section{(rfp.sections_count || 0) === 1 ? '' : 's'}
                      </span>
                    </td>

                    <td className="px-4 py-4">
                      <div className="flex flex-wrap gap-1 max-w-xs">
                        {Array.isArray(rfp.services) && rfp.services.length > 0 ? (
                          rfp.services.map((svc, idx) => (
                            <span key={idx} className="chip chip-neutral">
                              {typeof svc === 'object' ? svc.name : svc}
                            </span>
                          ))
                        ) : (
                          <span className="text-xs text-ink-muted">—</span>
                        )}
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <div className="flex flex-col items-start gap-1">
                        <span className="font-mono text-sm font-semibold text-ink">{rfp.budget_type === 'unknown' ? 'TBD' : formatGBP(rfp.value)}</span>
                        {rfp.budget_type && rfp.budget_type !== 'fixed' && <BudgetTypeBadge type={rfp.budget_type} notes={rfp.budget_notes} />}
                      </div>
                    </td>

                    <td className="px-4 py-4">
                      <DeadlineBadge deadline={rfp.deadline || rfp.date_submitted} />
                    </td>

                    <td className="px-4 py-4">
                      <StatusBadge status={rfp.status} />
                    </td>

                    <td className="px-4 py-4 text-center">
                      <div className="flex justify-center">
                        <OpenQuestionBadge count={rfp.open_questions_count || 0} />
                      </div>
                    </td>

                    <td className="px-5 py-4 text-right">
                      <button type="button" onClick={() => onSelectRFP?.(rfp.id)} className="btn-secondary text-xs px-3 py-1" aria-label={`Open ${rfp.client_name}`}>
                        <span>Open</span>
                        <ArrowUpRight className="w-3 h-3" aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
