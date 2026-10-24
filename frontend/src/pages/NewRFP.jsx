import React, { useState, useEffect, useRef } from 'react';
import { UploadCloud, FileText, Edit3, Check, X, ArrowLeft, AlertCircle, Loader2 } from 'lucide-react';
import { api } from '../services/api';

export default function NewRFP({ onSuccess, onCancel }) {
  const [mode, setMode] = useState('upload'); // 'upload' | 'manual'
  const [clientName, setClientName] = useState('');
  const [estimatedValue, setEstimatedValue] = useState('');
  const [deadline, setDeadline] = useState('');
  const [budgetType, setBudgetType] = useState('fixed');
  const [budgetNotes, setBudgetNotes] = useState('');
  const [rawDetails, setRawDetails] = useState('');
  const [selectedServices, setSelectedServices] = useState([]);

  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const [availableServices, setAvailableServices] = useState([]);
  const [servicesLoading, setServicesLoading] = useState(true);

  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getServices()
      .then((data) => {
        if (!cancelled) setAvailableServices(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        if (!cancelled) setAvailableServices([]);
      })
      .finally(() => {
        if (!cancelled) setServicesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function toggleService(serviceId) {
    setSelectedServices((prev) => (prev.includes(serviceId) ? prev.filter((id) => id !== serviceId) : [...prev, serviceId]));
  }

  function handleFileDrop(e) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files?.length) validateAndSetFile(e.dataTransfer.files[0]);
  }

  function handleFileInputChange(e) {
    if (e.target.files?.length) validateAndSetFile(e.target.files[0]);
  }

  function validateAndSetFile(selectedFile) {
    const lowerName = selectedFile.name.toLowerCase();
    if (!['.pdf', '.docx'].some((ext) => lowerName.endsWith(ext))) {
      setErrorMessage('Please upload a PDF (.pdf) or Word (.docx) document.');
      return;
    }
    if (selectedFile.size > 25 * 1024 * 1024) {
      setErrorMessage('File is larger than 25 MB.');
      return;
    }
    setFile(selectedFile);
    setErrorMessage(null);
    if (!clientName.trim()) {
      const cleanName = selectedFile.name
        .replace(/\.(pdf|docx)$/i, '')
        .replace(/[-_]/g, ' ')
        .replace(/\brfp\b/gi, '')
        .trim();
      if (cleanName) setClientName(cleanName.charAt(0).toUpperCase() + cleanName.slice(1));
    }
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setErrorMessage(null);

    if (!clientName.trim()) {
      setErrorMessage('Client name is required.');
      return;
    }
    if (mode === 'upload' && !file) {
      setErrorMessage('Select or drop an RFP document (.pdf or .docx).');
      return;
    }

    setSubmitting(true);
    try {
      if (mode === 'upload') {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('client_name', clientName.trim());
        if (estimatedValue) formData.append('value', parseFloat(estimatedValue));
        if (deadline) {
          formData.append('deadline', deadline);
          formData.append('date_submitted', deadline);
        }
        formData.append('budget_type', budgetType);
        if (budgetNotes) formData.append('budget_notes', budgetNotes);
        selectedServices.forEach((id) => formData.append('services', id));

        const res = await api.uploadRFP(formData);
        const rfpId = res.rfp_id || res.id;
        if (!rfpId) throw new Error('The server did not return an RFP identifier.');
        onSuccess(rfpId);
      } else {
        const res = await api.createRFP({
          client_name: clientName.trim(),
          value: estimatedValue ? parseFloat(estimatedValue) : null,
          deadline: deadline || null,
          date_submitted: deadline || null,
          budget_type: budgetType,
          budget_notes: budgetNotes || null,
          raw_details: rawDetails.trim() || null,
          services: selectedServices,
          service_ids: selectedServices,
        });
        const rfpId = res.id || res.rfp_id;
        if (!rfpId) throw new Error('Failed to create the RFP record.');
        onSuccess(rfpId);
      }
    } catch (err) {
      setErrorMessage(err.message || 'An error occurred during intake. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  const modeBtn = (active) =>
    `flex-1 flex items-center justify-center gap-2 py-2 text-xs font-bold rounded-md transition-colors ${
      active ? 'bg-accent text-accent-ink' : 'text-ink-muted hover:text-ink'
    }`;

  return (
    <div className="max-w-3xl mx-auto py-8 px-4 sm:px-6">
      <button type="button" onClick={onCancel} className="btn-ghost -ml-2 mb-6 text-xs">
        <ArrowLeft className="w-4 h-4" aria-hidden="true" />
        <span>Back to RFP Tracker</span>
      </button>

      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">New RFP response</h1>
        <p className="mt-1 text-sm text-ink-muted">Upload an RFP to extract sections automatically, or enter the brief by hand.</p>
      </div>

      <div role="tablist" aria-label="Intake method" className="flex border border-border-strong rounded-lg p-1 bg-surface-raised mb-6 max-w-sm">
        <button type="button" role="tab" aria-selected={mode === 'upload'} onClick={() => setMode('upload')} className={modeBtn(mode === 'upload')}>
          <UploadCloud className="w-4 h-4" aria-hidden="true" />
          <span>Upload document</span>
        </button>
        <button type="button" role="tab" aria-selected={mode === 'manual'} onClick={() => setMode('manual')} className={modeBtn(mode === 'manual')}>
          <Edit3 className="w-4 h-4" aria-hidden="true" />
          <span>Manual entry</span>
        </button>
      </div>

      {errorMessage && (
        <div role="alert" className="mb-6 p-4 rounded-md bg-danger-soft border border-danger/40 flex items-start gap-3 text-ink">
          <AlertCircle className="w-5 h-5 text-danger flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="text-sm font-medium">{errorMessage}</div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {mode === 'upload' && (
          <div className="card border-dashed border-2 border-border-strong p-6">
            <input
              ref={fileInputRef}
              id="rfp-file-input"
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={handleFileInputChange}
              className="sr-only"
            />

            {!file ? (
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleFileDrop}
                className={`flex flex-col items-center justify-center py-8 px-4 rounded-md transition-colors ${dragOver ? 'bg-accent-soft' : ''}`}
              >
                <UploadCloud className={`w-12 h-12 mb-3 ${dragOver ? 'text-accent' : 'text-ink-muted'}`} aria-hidden="true" />
                <label htmlFor="rfp-file-input" className="btn-secondary cursor-pointer">
                  Choose a file
                </label>
                <p className="text-sm font-semibold text-ink mt-3">or drag and drop your RFP document here</p>
                <p className="help-text mt-1">PDF (.pdf) or Word (.docx), up to 25 MB</p>
              </div>
            ) : (
              <div className="flex items-center justify-between p-3 sub-card">
                <div className="flex items-center gap-3 truncate">
                  <div className="w-10 h-10 bg-accent-soft text-accent rounded flex items-center justify-center flex-shrink-0">
                    <FileText className="w-5 h-5" aria-hidden="true" />
                  </div>
                  <div className="truncate">
                    <p className="text-sm font-bold text-ink truncate">{file.name}</p>
                    <p className="help-text font-mono">{formatFileSize(file.size)}</p>
                  </div>
                </div>
                <button type="button" onClick={() => setFile(null)} className="btn-icon hover:text-danger" aria-label={`Remove file ${file.name}`}>
                  <X className="w-5 h-5" aria-hidden="true" />
                </button>
              </div>
            )}
          </div>
        )}

        <div className="card space-y-4">
          <h2 className="text-base font-bold text-ink">Proposal details</h2>

          <div>
            <label htmlFor="client-name" className="field-label">
              Client name <span className="text-danger" aria-hidden="true">*</span>
            </label>
            <input
              id="client-name"
              type="text"
              required
              aria-required="true"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              placeholder="e.g. Acme Health Systems"
              className="input-field"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label htmlFor="estimated-value" className="field-label">
                Estimated value (£)
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-ink-muted" aria-hidden="true">
                  £
                </span>
                <input
                  id="estimated-value"
                  type="number"
                  min="0"
                  step="100"
                  value={estimatedValue}
                  onChange={(e) => setEstimatedValue(e.target.value)}
                  placeholder="25000"
                  className="input-field pl-8 font-mono"
                />
              </div>
            </div>

            <div>
              <label htmlFor="budget-type" className="field-label">
                Budget structure
              </label>
              <select id="budget-type" value={budgetType} onChange={(e) => setBudgetType(e.target.value)} className="input-field">
                <option value="fixed">Fixed budget</option>
                <option value="under_budget">Target: under budget</option>
                <option value="unknown">Budget unknown / TBD</option>
                <option value="retainer">Monthly retainer</option>
                <option value="time_and_materials">Time & materials</option>
              </select>
            </div>

            <div>
              <label htmlFor="deadline" className="field-label">
                Submission deadline
              </label>
              <input id="deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className="input-field" />
            </div>
          </div>

          {budgetType !== 'fixed' && (
            <div>
              <label htmlFor="budget-notes" className="field-label">
                Budget notes & target range
              </label>
              <input
                id="budget-notes"
                type="text"
                value={budgetNotes}
                onChange={(e) => setBudgetNotes(e.target.value)}
                placeholder="e.g. Client stated £30k ceiling; propose £22k to win on value"
                className="input-field"
              />
            </div>
          )}

          {mode === 'manual' && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <label htmlFor="raw-details" className="field-label mb-0">
                  RFP brief / specification / questions
                </label>
                <span className="help-text">Headings become draftable sections</span>
              </div>
              <textarea
                id="raw-details"
                rows={8}
                value={rawDetails}
                onChange={(e) => setRawDetails(e.target.value)}
                placeholder={
                  "Paste the client's brief, scope, questions or requirements…\n\n1.0 Executive Summary\nPlease introduce your agency and experience.\n\n2.0 Technical Approach\nDescribe your proposed CMS architecture."
                }
                className="input-field font-mono text-xs leading-relaxed"
              />
            </div>
          )}

          <fieldset>
            <div className="flex items-center justify-between mb-2">
              <legend className="field-label mb-0">Services involved</legend>
              <span className="help-text">{selectedServices.length} selected</span>
            </div>
            {servicesLoading ? (
              <p className="help-text py-2" role="status">
                Loading services…
              </p>
            ) : availableServices.length === 0 ? (
              <p className="help-text py-2">No services configured yet — add some under Settings → Services.</p>
            ) : (
              <div className="flex flex-wrap gap-2 pt-1">
                {availableServices.map((service) => {
                  const isSelected = selectedServices.includes(service.id);
                  return (
                    <button
                      key={service.id}
                      type="button"
                      role="checkbox"
                      aria-checked={isSelected}
                      onClick={() => toggleService(service.id)}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
                        isSelected ? 'bg-accent text-accent-ink border-accent' : 'bg-surface text-ink border-border-strong hover:bg-surface-raised'
                      }`}
                    >
                      {isSelected && <Check className="w-3.5 h-3.5" aria-hidden="true" />}
                      <span>{service.name}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </fieldset>
        </div>

        <div className="flex items-center justify-end gap-3 pt-2">
          <button type="button" onClick={onCancel} disabled={submitting} className="btn-secondary">
            Cancel
          </button>
          <button type="submit" disabled={submitting || !clientName.trim() || (mode === 'upload' && !file)} className="btn-primary px-6">
            {submitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                <span>{mode === 'upload' ? 'Parsing document…' : 'Creating RFP…'}</span>
              </>
            ) : (
              <span>{mode === 'upload' ? 'Upload & parse RFP' : 'Create RFP response'}</span>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
