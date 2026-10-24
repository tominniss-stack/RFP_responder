import React, { useState, useEffect, useCallback } from 'react';
import { PoundSterling, Plus, Trash2, Edit2, ShieldCheck, Search } from 'lucide-react';
import { api } from '../services/api';
import { PricingUnitBadge } from '../components/Badge';
import Modal from '../components/Modal';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmDialog';

const EMPTY_FORM = { service_id: '', description: '', unit: 'day rate', amount: '' };

function formatGBP(amount) {
  return new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount);
}

export default function PricingAdmin() {
  const toast = useToast();
  const confirm = useConfirm();

  const [items, setItems] = useState([]);
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');
  const [unitFilter, setUnitFilter] = useState('');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [formData, setFormData] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [seeding, setSeeding] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pricingData, servicesData] = await Promise.all([api.getPriceItems({ service_id: serviceFilter || undefined }), api.getServices().catch(() => [])]);
      setItems(Array.isArray(pricingData) ? pricingData : []);
      setServices(Array.isArray(servicesData) ? servicesData : []);
    } catch (err) {
      setError(err.message || 'Failed to load price items.');
    } finally {
      setLoading(false);
    }
  }, [serviceFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  function openAdd() {
    setEditingItem(null);
    setFormData({ ...EMPTY_FORM, service_id: services[0] ? String(services[0].id) : '' });
    setFormError(null);
    setIsModalOpen(true);
  }

  function openEdit(item) {
    setEditingItem(item);
    setFormData({ service_id: item.service_id ? String(item.service_id) : '', description: item.description, unit: item.unit, amount: item.amount });
    setFormError(null);
    setIsModalOpen(true);
  }

  async function handleSeed() {
    setSeeding(true);
    try {
      const res = await api.seedPriceItems();
      toast.success(`Loaded ${res?.inserted ?? 'the'} seed price items.`);
      await loadData();
    } catch (err) {
      toast.error(err.message || 'Could not load seed rate card.');
    } finally {
      setSeeding(false);
    }
  }

  async function handleDelete(item) {
    const ok = await confirm({
      title: 'Delete price item?',
      message: `"${item.description}" will be removed from the rate card. Drafts already generated keep their figures.`,
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deletePriceItem(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      toast.success('Price item deleted.');
    } catch (err) {
      toast.error(err.message || 'Failed to delete item.');
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const numAmount = parseFloat(formData.amount);
    if (isNaN(numAmount) || numAmount < 0) {
      setFormError('Amount must be a non-negative number.');
      return;
    }
    if (!formData.description.trim()) {
      setFormError('Description is required.');
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const payload = {
        service_id: formData.service_id ? parseInt(formData.service_id, 10) : null,
        description: formData.description.trim(),
        unit: formData.unit,
        amount: numAmount,
      };
      if (editingItem) {
        await api.updatePriceItem(editingItem.id, payload);
        toast.success('Price item updated.');
      } else {
        await api.createPriceItem(payload);
        toast.success('Price item added.');
      }
      setIsModalOpen(false);
      await loadData();
    } catch (err) {
      setFormError(err.message || 'Failed to save price item.');
    } finally {
      setSubmitting(false);
    }
  }

  const getServiceName = (sid) => {
    if (!sid) return 'General / shared';
    const s = services.find((srv) => srv.id === sid);
    return s ? s.name : `Service #${sid}`;
  };

  const filteredItems = items.filter((item) => {
    if (unitFilter && item.unit !== unitFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return item.description.toLowerCase().includes(q) || getServiceName(item.service_id).toLowerCase().includes(q);
    }
    return true;
  });

  const counts = {
    total: items.length,
    day: items.filter((i) => i.unit === 'day rate').length,
    fixed: items.filter((i) => i.unit === 'fixed').length,
    retainer: items.filter((i) => i.unit === 'monthly retainer').length,
  };

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">Pricing rate card</h1>
          <p className="text-sm text-ink-muted mt-1">
            Authoritative rates, packages and retainers. Figures are injected into drafts verbatim — never estimated by the model.
          </p>
        </div>
        <button type="button" onClick={openAdd} className="btn-primary self-start md:self-auto">
          <Plus className="w-4 h-4" aria-hidden="true" />
          <span>Add price item</span>
        </button>
      </div>

      <ul className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6 list-none p-0 m-0" aria-label="Pricing summary">
        {[
          { label: 'Total price items', value: counts.total, glyph: <PoundSterling className="w-5 h-5" aria-hidden="true" /> },
          { label: 'Day-rate roles', value: counts.day, glyph: '/d' },
          { label: 'Fixed packages', value: counts.fixed, glyph: 'FIX' },
          { label: 'Monthly retainers', value: counts.retainer, glyph: '/mo' },
        ].map((m) => (
          <li key={m.label} className="card p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded bg-accent-soft text-accent flex items-center justify-center font-mono font-bold text-sm flex-shrink-0" aria-hidden="true">{m.glyph}</div>
            <div>
              <p className="text-2xl font-bold text-ink">{m.value}</p>
              <p className="text-xs text-ink-muted">{m.label}</p>
            </div>
          </li>
        ))}
      </ul>

      <div className="mb-6 p-4 rounded-lg bg-surface-raised border border-border flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-accent flex-shrink-0 mt-0.5" aria-hidden="true" />
        <p className="text-xs text-ink">
          <span className="font-bold">Deterministic pricing guarantee: </span>
          draft generation performs a direct lookup against this table and reproduces amounts exactly (e.g.{' '}
          <code className="font-mono bg-surface px-1 py-0.5 rounded border border-border">£850.00</code>). If no matching item exists the draft contains an explicit{' '}
          <code className="font-mono bg-surface px-1 py-0.5 rounded border border-border">[MORE INFO REQUIRED]</code> marker with zero invented figures.
        </p>
      </div>

      <div className="card p-4 mb-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="relative">
            <label htmlFor="pricing-search" className="sr-only">
              Search price items
            </label>
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" aria-hidden="true" />
            <input id="pricing-search" type="search" placeholder="Search description or service…" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="input-field pl-9" />
          </div>
          <div>
            <label htmlFor="pricing-service" className="sr-only">
              Filter by service
            </label>
            <select id="pricing-service" value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} className="input-field">
              <option value="">All services</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="pricing-unit" className="sr-only">
              Filter by unit
            </label>
            <select id="pricing-unit" value={unitFilter} onChange={(e) => setUnitFilter(e.target.value)} className="input-field">
              <option value="">All pricing units</option>
              <option value="day rate">Day rate</option>
              <option value="fixed">Fixed</option>
              <option value="monthly retainer">Monthly retainer</option>
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-md bg-danger-soft border border-danger/40 text-sm font-semibold text-ink">
          {error}
        </div>
      )}

      {loading ? (
        <p className="card text-center py-10 text-ink-muted text-sm" role="status">
          Loading rate card…
        </p>
      ) : items.length === 0 ? (
        <div className="card text-center py-12 px-6 border-2 border-dashed border-border-strong max-w-2xl mx-auto my-8">
          <div className="w-16 h-16 bg-accent-soft text-accent rounded-full flex items-center justify-center mx-auto mb-4">
            <PoundSterling className="w-8 h-8" aria-hidden="true" />
          </div>
          <h2 className="text-xl font-bold text-ink mb-2">The rate card is empty</h2>
          <p className="text-sm text-ink-muted max-w-md mx-auto mb-6">
            Add your first item, or load the sample rate card to see deterministic pricing injection in action.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <button type="button" onClick={openAdd} className="btn-primary">
              Add first price item
            </button>
            <button type="button" onClick={handleSeed} disabled={seeding} className="btn-secondary">
              {seeding ? 'Loading…' : 'Load sample rate card'}
            </button>
          </div>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <caption className="sr-only">Price items</caption>
              <thead>
                <tr className="border-b border-border bg-surface-raised text-xs uppercase tracking-wider text-ink-muted font-bold">
                  <th scope="col" className="py-3 px-4">
                    Service
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Description
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Unit
                  </th>
                  <th scope="col" className="py-3 px-4 text-right">
                    Amount (GBP)
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Draft injection string
                  </th>
                  <th scope="col" className="py-3 px-4 text-right">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-sm">
                {filteredItems.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-ink-muted text-sm">
                      No items match the current filters.
                    </td>
                  </tr>
                )}
                {filteredItems.map((item) => (
                  <tr key={item.id} className="hover:bg-surface-raised/60 transition-colors">
                    <td className="py-3.5 px-4 text-xs font-semibold text-ink-muted">{getServiceName(item.service_id)}</td>
                    <td className="py-3.5 px-4 font-bold text-ink">{item.description}</td>
                    <td className="py-3.5 px-4">
                      <PricingUnitBadge unit={item.unit} />
                    </td>
                    <td className="py-3.5 px-4 text-right font-mono font-bold text-ink">{formatGBP(item.amount)}</td>
                    <td className="py-3.5 px-4 font-mono text-xs text-ink-muted max-w-xs truncate">
                      - {item.description}: {formatGBP(item.amount)} ({item.unit})
                    </td>
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1">
                        <button type="button" onClick={() => openEdit(item)} className="btn-icon" aria-label={`Edit ${item.description}`}>
                          <Edit2 className="w-4 h-4" aria-hidden="true" />
                        </button>
                        <button type="button" onClick={() => handleDelete(item)} className="btn-icon hover:text-danger" aria-label={`Delete ${item.description}`}>
                          <Trash2 className="w-4 h-4" aria-hidden="true" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Modal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingItem ? 'Edit price item' : 'Add price item'}
        description="Amounts are stored to the penny and reproduced exactly in drafts."
        footer={
          <>
            <button type="button" onClick={() => setIsModalOpen(false)} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" form="price-item-form" disabled={submitting} className="btn-primary">
              {submitting ? 'Saving…' : editingItem ? 'Update item' : 'Add price item'}
            </button>
          </>
        }
      >
        <form id="price-item-form" onSubmit={handleSubmit} className="space-y-4">
          {formError && (
            <p role="alert" className="p-3 rounded-md bg-danger-soft border border-danger/40 text-sm text-ink">
              {formError}
            </p>
          )}
          <div>
            <label htmlFor="pi-service" className="field-label">
              Associated service
            </label>
            <select id="pi-service" value={formData.service_id} onChange={(e) => setFormData({ ...formData, service_id: e.target.value })} className="input-field">
              <option value="">General / shared</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="pi-description" className="field-label">
              Description <span className="text-danger" aria-hidden="true">*</span>
            </label>
            <input
              id="pi-description"
              type="text"
              required
              aria-required="true"
              placeholder="e.g. Senior full-stack engineer"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="input-field"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="pi-unit" className="field-label">
                Unit <span className="text-danger" aria-hidden="true">*</span>
              </label>
              <select id="pi-unit" value={formData.unit} onChange={(e) => setFormData({ ...formData, unit: e.target.value })} className="input-field font-mono">
                <option value="day rate">day rate</option>
                <option value="fixed">fixed</option>
                <option value="monthly retainer">monthly retainer</option>
              </select>
            </div>
            <div>
              <label htmlFor="pi-amount" className="field-label">
                Amount (£) <span className="text-danger" aria-hidden="true">*</span>
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted font-mono text-sm" aria-hidden="true">
                  £
                </span>
                <input
                  id="pi-amount"
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  aria-required="true"
                  placeholder="850.00"
                  value={formData.amount}
                  onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                  className="input-field pl-7 font-mono"
                />
              </div>
            </div>
          </div>

          {formData.description && formData.amount && (
            <div className="sub-card">
              <p className="field-label">Verbatim draft preview</p>
              <p className="font-mono text-xs text-ink">
                - {formData.description}: £{Number(formData.amount || 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })} ({formData.unit})
              </p>
            </div>
          )}
        </form>
      </Modal>
    </div>
  );
}
