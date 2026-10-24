import React, { useState, useEffect } from 'react';
import { Tag, Plus, Trash2 } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmDialog';

export default function ServicesAdmin() {
  const toast = useToast();
  const confirm = useConfirm();
  const [services, setServices] = useState([]);
  const [newServiceName, setNewServiceName] = useState('');
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadServices();
  }, []);

  async function loadServices() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getServices();
      setServices(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || 'Could not load services.');
      setServices([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleAddService(e) {
    e.preventDefault();
    const trimmed = newServiceName.trim();
    if (!trimmed) {
      setError('Service name cannot be empty.');
      return;
    }
    if (services.some((s) => s.name.toLowerCase() === trimmed.toLowerCase())) {
      setError(`A service named "${trimmed}" already exists.`);
      return;
    }

    setAdding(true);
    setError(null);
    try {
      const created = await api.createService({ name: trimmed });
      setServices((prev) => [...prev, created]);
      setNewServiceName('');
      toast.success(`Service "${trimmed}" added.`);
    } catch (err) {
      setError(err.message || 'Failed to add service.');
    } finally {
      setAdding(false);
    }
  }

  async function handleDeleteService(id, name) {
    const ok = await confirm({
      title: `Delete "${name}"?`,
      message: 'RFPs, knowledge base documents and price items tagged with this service will lose the tag. Deletion is blocked if any RFP still references it.',
      confirmLabel: 'Delete service',
      danger: true,
    });
    if (!ok) return;

    setDeletingId(id);
    setError(null);
    try {
      await api.deleteService(id);
      setServices((prev) => prev.filter((s) => s.id !== id));
      toast.success(`Service "${name}" deleted.`);
    } catch (err) {
      toast.error(err.message || 'Failed to delete service.');
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 sm:px-6">
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">Services</h1>
        <p className="mt-1 text-sm text-ink-muted">
          The extensible catalogue of agency capabilities. Services tag RFPs, knowledge base documents and price items.
        </p>
      </div>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-md bg-danger-soft border border-danger/40 text-sm font-semibold text-ink">
          {error}
        </div>
      )}

      <div className="card mb-8">
        <h2 className="text-base font-bold text-ink mb-3">Add a service</h2>
        <form onSubmit={handleAddService} className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <label htmlFor="new-service-name" className="sr-only">
              Service name
            </label>
            <input
              id="new-service-name"
              type="text"
              value={newServiceName}
              onChange={(e) => setNewServiceName(e.target.value)}
              placeholder="e.g. Brand Identity & Strategy"
              className="input-field"
              disabled={adding}
            />
          </div>
          <button type="submit" disabled={adding || !newServiceName.trim()} className="btn-primary flex-shrink-0">
            <Plus className="w-4 h-4" aria-hidden="true" />
            <span>{adding ? 'Adding…' : 'Add service'}</span>
          </button>
        </form>
      </div>

      <div className="card">
        <div className="flex items-center justify-between border-b border-border pb-3 mb-4">
          <div className="flex items-center gap-2">
            <Tag className="w-5 h-5 text-accent" aria-hidden="true" />
            <h2 className="text-base font-bold text-ink">Configured services</h2>
          </div>
          <span className="chip chip-neutral">
            {services.length} service{services.length === 1 ? '' : 's'}
          </span>
        </div>

        {loading ? (
          <p className="py-8 text-center text-ink-muted text-sm" role="status">
            Loading services…
          </p>
        ) : services.length === 0 ? (
          <div className="py-12 text-center text-ink-muted">
            <Tag className="w-8 h-8 mx-auto mb-2" aria-hidden="true" />
            <p className="text-sm font-medium text-ink">No services registered yet.</p>
            <p className="text-xs mt-1">Add your first service using the form above.</p>
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {services.map((service) => (
              <li key={service.id} className="py-3 flex items-center justify-between hover:bg-surface-raised px-2 rounded transition-colors">
                <div className="flex items-center gap-3">
                  <span className="w-8 text-xs text-ink-muted font-mono">#{service.id}</span>
                  <span className="text-sm font-semibold text-ink">{service.name}</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleDeleteService(service.id, service.name)}
                  disabled={deletingId === service.id}
                  className="btn-danger text-xs"
                  aria-label={`Delete service ${service.name}`}
                >
                  <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                  <span className="hidden sm:inline">Delete</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
