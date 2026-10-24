import React, { useState, useEffect, useCallback } from 'react';
import { BookOpen, Search, Plus, Trash2, Upload, Award, Layers, Sparkles, ChevronDown, ChevronUp, RefreshCw, ExternalLink, Eye, Copy, Check, Sliders, TrendingUp, CheckCircle2, AlertCircle } from 'lucide-react';
import { api } from '../services/api';
import { DocumentTypeBadge, OutcomeBadge } from '../components/Badge';
import MarkdownRenderer from '../components/MarkdownRenderer';
import Modal from '../components/Modal';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmDialog';

const BENCHMARK_QUERY = 'headless CMS architecture and digital marketing';
const EMPTY_FORM = { title: '', type: 'past_proposal', outcome: 'won', content: '', service_ids: [] };

export default function KnowledgeBase() {
  const toast = useToast();
  const confirm = useConfirm();

  const [activeTab, setActiveTab] = useState('catalog');
  const [documents, setDocuments] = useState([]);
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [inputMode, setInputMode] = useState('paste');
  const [formData, setFormData] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [seeding, setSeeding] = useState(false);

  const [viewerDoc, setViewerDoc] = useState(null);
  const [copied, setCopied] = useState(false);
  const [expandedDocs, setExpandedDocs] = useState({});

  const [weightWon, setWeightWon] = useState(1.25);
  const [weightLost, setWeightLost] = useState(0.9);
  const [savingWeights, setSavingWeights] = useState(false);

  const [inspectorQuery, setInspectorQuery] = useState(BENCHMARK_QUERY);
  const [inspectorResults, setInspectorResults] = useState([]);
  const [inspecting, setInspecting] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [docsData, srvData, settingsData] = await Promise.all([
        api.getKBDocuments({ type: typeFilter || undefined, outcome: outcomeFilter || undefined, service_id: serviceFilter || undefined, query: searchQuery || undefined }),
        api.getServices().catch(() => []),
        api.getSettings().catch(() => null),
      ]);
      setDocuments(Array.isArray(docsData) ? docsData : []);
      setServices(Array.isArray(srvData) ? srvData : []);
      if (settingsData) {
        if (settingsData.weight_won != null) setWeightWon(Number(settingsData.weight_won));
        if (settingsData.weight_lost != null) setWeightLost(Number(settingsData.weight_lost));
      }
    } catch (err) {
      setError(err.message || 'Failed to load the knowledge base.');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeFilter, outcomeFilter, serviceFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleSeed() {
    setSeeding(true);
    try {
      const res = await api.seedKBDocuments();
      toast.success(`Loaded ${res?.inserted ?? 'the'} sample documents.`);
      await loadData();
    } catch (err) {
      toast.error(err.message || 'Could not load sample documents.');
    } finally {
      setSeeding(false);
    }
  }

  async function handleDelete(doc) {
    const ok = await confirm({
      title: 'Delete document?',
      message: `"${doc.title}" will be removed from the knowledge base and the vector index.`,
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteKBDocument(doc.id);
      setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
      toast.success('Document deleted.');
    } catch (err) {
      toast.error(err.message || 'Failed to delete document.');
    }
  }

  function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const baseTitle = file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
    setFormData((prev) => ({ ...prev, title: prev.title || baseTitle }));
    const reader = new FileReader();
    reader.onload = (ev) => setFormData((prev) => ({ ...prev, content: String(ev.target.result || '') }));
    reader.readAsText(file);
  }

  function toggleFormService(sid) {
    setFormData((prev) => ({
      ...prev,
      service_ids: prev.service_ids.includes(sid) ? prev.service_ids.filter((id) => id !== sid) : [...prev.service_ids, sid],
    }));
  }

  async function handleCreateSubmit(e) {
    e.preventDefault();
    if (!formData.title.trim() || !formData.content.trim()) {
      setFormError('Title and content are required.');
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createKBDocument(formData);
      setIsModalOpen(false);
      setFormData(EMPTY_FORM);
      toast.success('Document saved and indexed.');
      await loadData();
    } catch (err) {
      setFormError(err.message || 'Failed to save document.');
    } finally {
      setSubmitting(false);
    }
  }

  async function runInspectorSearch(queryTerm) {
    const q = queryTerm !== undefined ? queryTerm : inspectorQuery;
    setInspecting(true);
    try {
      const results = await api.getKBDocuments({ query: q });
      setInspectorResults(Array.isArray(results) ? results : []);
    } catch (err) {
      toast.error(err.message || 'Search failed.');
    } finally {
      setInspecting(false);
    }
  }

  async function runBiasingBenchmark() {
    setInspecting(true);
    try {
      const results = await api.getKBDocuments({ query: BENCHMARK_QUERY });
      const won = results.find((d) => d.outcome === 'won');
      const lost = results.find((d) => d.outcome === 'lost');
      if (won && lost) {
        const ratio = won.similarity_score / lost.similarity_score;
        setBenchmarkResult({ wonTitle: won.title, wonScore: won.similarity_score, lostTitle: lost.title, lostScore: lost.similarity_score, ratio, passed: ratio >= 1.2 && results[0]?.id === won.id });
      } else {
        setBenchmarkResult({ error: 'Add at least one won and one lost proposal to run the benchmark.' });
      }
      setInspectorQuery(BENCHMARK_QUERY);
      setInspectorResults(results);
    } catch (err) {
      toast.error(err.message || 'Benchmark failed.');
    } finally {
      setInspecting(false);
    }
  }

  async function handleSaveWeights(e) {
    e.preventDefault();
    setSavingWeights(true);
    try {
      await api.updateSettings({ weight_won: parseFloat(weightWon) || 1.25, weight_lost: parseFloat(weightLost) || 0.9 });
      toast.success('Biasing multipliers saved — re-running benchmark.');
      await runBiasingBenchmark();
    } catch (err) {
      toast.error(err.message || 'Failed to save multipliers.');
    } finally {
      setSavingWeights(false);
    }
  }

  function copyDoc(doc) {
    navigator.clipboard.writeText(`# ${doc.title}\n\n**Type:** ${doc.type} | **Outcome:** ${doc.outcome}\n\n---\n\n${doc.content}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
    toast.info('Document copied as Markdown.');
  }

  function openInGoogleDocs(doc) {
    copyDoc(doc);
    window.open('https://docs.google.com/document/create', '_blank', 'noopener,noreferrer');
  }

  const getServiceName = (sid) => services.find((s) => s.id === sid)?.name || `Service #${sid}`;

  const metrics = [
    { label: 'Documents', value: documents.length, icon: BookOpen },
    { label: 'Won proposals (boosted)', value: documents.filter((d) => d.outcome === 'won').length, icon: Award },
    { label: 'Boilerplate', value: documents.filter((d) => d.type === 'boilerplate').length, icon: Layers },
    { label: 'Case studies', value: documents.filter((d) => d.type === 'case_study').length, icon: TrendingUp },
  ];

  const ratio = (weightWon / (weightLost || 1)).toFixed(3);

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">Knowledge base</h1>
          <p className="text-sm text-ink-muted mt-1">Past proposals, case studies, testimonials and boilerplate — retrieved with outcome-weighted ranking.</p>
        </div>
        <button type="button" onClick={() => setIsModalOpen(true)} className="btn-primary self-start md:self-auto">
          <Plus className="w-4 h-4" aria-hidden="true" />
          <span>Add document</span>
        </button>
      </div>

      <ul className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6 list-none p-0 m-0" aria-label="Knowledge base summary">
        {metrics.map((m) => {
          const Icon = m.icon;
          return (
            <li key={m.label} className="card p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded bg-accent-soft text-accent flex items-center justify-center flex-shrink-0" aria-hidden="true">
                <Icon className="w-5 h-5" aria-hidden="true" />
              </div>
              <div>
                <p className="text-2xl font-bold text-ink">{m.value}</p>
                <p className="text-xs text-ink-muted">{m.label}</p>
              </div>
            </li>
          );
        })}
      </ul>

      <div role="tablist" aria-label="Knowledge base views" className="flex border-b border-border mb-6 gap-1">
        <button type="button" role="tab" aria-selected={activeTab === 'catalog'} onClick={() => setActiveTab('catalog')} className={`tab -mb-px flex items-center gap-2 ${activeTab === 'catalog' ? 'tab-active' : ''}`}>
          <BookOpen className="w-4 h-4" aria-hidden="true" />
          <span>Catalogue ({documents.length})</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'inspector'}
          onClick={() => {
            setActiveTab('inspector');
            if (inspectorResults.length === 0) runInspectorSearch();
          }}
          className={`tab -mb-px flex items-center gap-2 ${activeTab === 'inspector' ? 'tab-active' : ''}`}
        >
          <Sparkles className="w-4 h-4" aria-hidden="true" />
          <span>Retrieval inspector</span>
        </button>
      </div>

      {error && (
        <div role="alert" className="mb-6 p-4 rounded-md bg-danger-soft border border-danger/40 text-sm font-semibold text-ink">
          {error}
        </div>
      )}

      {activeTab === 'catalog' && (
        <>
          <div className="card p-4 mb-6">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                loadData();
              }}
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3"
            >
              <div className="relative lg:col-span-2">
                <label htmlFor="kb-search" className="sr-only">
                  Search documents
                </label>
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" aria-hidden="true" />
                <input id="kb-search" type="search" placeholder="Semantic search — press Enter" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="input-field pl-9" />
              </div>
              <div>
                <label htmlFor="kb-type" className="sr-only">
                  Document type
                </label>
                <select id="kb-type" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="input-field">
                  <option value="">All types</option>
                  <option value="past_proposal">Past proposal</option>
                  <option value="case_study">Case study</option>
                  <option value="boilerplate">Boilerplate</option>
                  <option value="testimonial">Testimonial</option>
                  <option value="pitch_deck">Pitch deck</option>
                </select>
              </div>
              <div>
                <label htmlFor="kb-outcome" className="sr-only">
                  Outcome
                </label>
                <select id="kb-outcome" value={outcomeFilter} onChange={(e) => setOutcomeFilter(e.target.value)} className="input-field">
                  <option value="">All outcomes</option>
                  <option value="won">Won</option>
                  <option value="lost">Lost</option>
                  <option value="n/a">N/A</option>
                </select>
              </div>
              <div>
                <label htmlFor="kb-service" className="sr-only">
                  Service
                </label>
                <select id="kb-service" value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} className="input-field">
                  <option value="">All services</option>
                  {services.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            </form>
          </div>

          {loading ? (
            <p className="card text-center py-10 text-ink-muted text-sm" role="status">
              Loading documents…
            </p>
          ) : documents.length === 0 ? (
            <div className="card text-center py-12 px-6 border-2 border-dashed border-border-strong max-w-2xl mx-auto my-8">
              <div className="w-16 h-16 bg-accent-soft text-accent rounded-full flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-8 h-8" aria-hidden="true" />
              </div>
              <h2 className="text-xl font-bold text-ink mb-2">The knowledge base is empty</h2>
              <p className="text-sm text-ink-muted max-w-md mx-auto mb-6">Add your own credentials and case studies, or load the sample documents to see retrieval and provenance in action.</p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
                <button type="button" onClick={() => setIsModalOpen(true)} className="btn-primary">
                  Add first document
                </button>
                <button type="button" onClick={handleSeed} disabled={seeding} className="btn-secondary">
                  {seeding ? 'Loading…' : 'Load sample documents'}
                </button>
              </div>
            </div>
          ) : (
            <ul className="space-y-3">
              {documents.map((doc) => {
                const isExpanded = expandedDocs[doc.id];
                const snippet = doc.content.length > 240 && !isExpanded ? `${doc.content.slice(0, 240)}…` : doc.content;
                return (
                  <li key={doc.id} className="card p-5 hover:border-border-strong transition-colors">
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-1.5">
                          <DocumentTypeBadge type={doc.type} />
                          <OutcomeBadge outcome={doc.outcome} />
                          {doc.similarity_score !== undefined && doc.similarity_score !== null && <span className="chip chip-neutral font-mono">Score {Number(doc.similarity_score).toFixed(4)}</span>}
                        </div>
                        <button type="button" onClick={() => setViewerDoc(doc)} className="text-base font-bold text-ink hover:text-accent text-left rounded">
                          {doc.title}
                        </button>
                      </div>
                      <div className="flex items-center gap-2 self-end sm:self-start flex-shrink-0">
                        <button type="button" onClick={() => setViewerDoc(doc)} className="btn-secondary text-xs px-2.5 py-1.5">
                          <Eye className="w-3.5 h-3.5" aria-hidden="true" />
                          <span>View</span>
                        </button>
                        <button type="button" onClick={() => openInGoogleDocs(doc)} className="btn-secondary text-xs px-2.5 py-1.5" title="Copies the document and opens a new Google Doc">
                          <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                          <span>Google Docs</span>
                        </button>
                        <button type="button" onClick={() => handleDelete(doc)} className="btn-icon hover:text-danger" aria-label={`Delete ${doc.title}`}>
                          <Trash2 className="w-4 h-4" aria-hidden="true" />
                        </button>
                      </div>
                    </div>

                    <p className="text-sm text-ink leading-relaxed whitespace-pre-wrap">{snippet}</p>

                    {doc.content.length > 240 && (
                      <button type="button" onClick={() => setExpandedDocs((p) => ({ ...p, [doc.id]: !p[doc.id] }))} className="mt-2 text-xs font-semibold text-accent hover:underline inline-flex items-center gap-1" aria-expanded={Boolean(isExpanded)}>
                        <span>{isExpanded ? 'Show less' : 'Show more'}</span>
                        {isExpanded ? <ChevronUp className="w-3 h-3" aria-hidden="true" /> : <ChevronDown className="w-3 h-3" aria-hidden="true" />}
                      </button>
                    )}

                    {doc.services?.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-1.5 items-center">
                        <span className="text-xs text-ink-muted font-medium">Services:</span>
                        {doc.services.map((sid) => (
                          <span key={sid} className="chip chip-neutral">
                            {getServiceName(sid)}
                          </span>
                        ))}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}

      {activeTab === 'inspector' && (
        <div className="space-y-6">
          <section className="card" aria-labelledby="weights-heading">
            <div className="flex items-center gap-2 border-b border-border pb-3 mb-5">
              <Sliders className="w-5 h-5 text-accent" aria-hidden="true" />
              <div>
                <h2 id="weights-heading" className="text-lg font-bold text-ink">
                  Outcome biasing multipliers
                </h2>
                <p className="help-text">How much won proposals are boosted over lost proposals in semantic ranking.</p>
              </div>
            </div>
            <form onSubmit={handleSaveWeights} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 items-end">
              <div>
                <label htmlFor="kb-weight-won" className="field-label">
                  Won multiplier
                </label>
                <input id="kb-weight-won" type="number" step="0.05" min="1.00" max="2.50" value={weightWon} onChange={(e) => setWeightWon(parseFloat(e.target.value) || 1.0)} className="input-field font-mono" />
                <span className="help-text mt-1 block">Default 1.25× (+25%)</span>
              </div>
              <div>
                <label htmlFor="kb-weight-lost" className="field-label">
                  Lost multiplier
                </label>
                <input id="kb-weight-lost" type="number" step="0.05" min="0.10" max="1.00" value={weightLost} onChange={(e) => setWeightLost(parseFloat(e.target.value) || 0.9)} className="input-field font-mono" />
                <span className="help-text mt-1 block">Default 0.90× (−10%)</span>
              </div>
              <button type="submit" disabled={savingWeights} className="btn-primary w-full">
                {savingWeights ? 'Saving…' : 'Save multipliers'}
              </button>
            </form>
            <p className="mt-4 sub-card text-xs flex items-center justify-between gap-4">
              <span>
                Current ratio: <strong className="font-mono">{ratio}×</strong>
              </span>
              <span className="text-ink-muted">Won proposals score {ratio}× higher than equivalent lost proposals.</span>
            </p>
          </section>

          <section className="card" aria-labelledby="benchmark-heading">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
              <div>
                <h2 id="benchmark-heading" className="text-lg font-bold text-ink flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-accent" aria-hidden="true" />
                  <span>Won-biasing benchmark</span>
                </h2>
                <p className="help-text mt-0.5">Runs a fixed query and checks that won content outranks lost content by the configured ratio.</p>
              </div>
              <button type="button" onClick={runBiasingBenchmark} disabled={inspecting} className="btn-primary self-start">
                <RefreshCw className={`w-3.5 h-3.5 ${inspecting ? 'animate-spin' : ''}`} aria-hidden="true" />
                <span>Run benchmark</span>
              </button>
            </div>

            {benchmarkResult && (
              <div role="status" className={`mb-6 p-4 rounded-lg border ${benchmarkResult.error || !benchmarkResult.passed ? 'bg-danger-soft border-danger/40' : 'bg-success-soft border-success/40'}`}>
                {benchmarkResult.error ? (
                  <p className="text-sm font-semibold text-ink flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-danger" aria-hidden="true" />
                    {benchmarkResult.error}
                  </p>
                ) : (
                  <div>
                    <p className="flex items-center gap-2 mb-3 text-sm font-bold text-ink">
                      {benchmarkResult.passed ? <CheckCircle2 className="w-5 h-5 text-success" aria-hidden="true" /> : <AlertCircle className="w-5 h-5 text-danger" aria-hidden="true" />}
                      {benchmarkResult.passed ? 'Won-biasing verified' : 'Benchmark failed'}
                    </p>
                    <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                      <div className="bg-surface p-2.5 rounded border border-border">
                        <dt className="text-ink-muted">Won proposal score</dt>
                        <dd className="font-mono font-bold text-sm text-ink">{Number(benchmarkResult.wonScore).toFixed(4)}</dd>
                        <dd className="text-ink-muted truncate">{benchmarkResult.wonTitle}</dd>
                      </div>
                      <div className="bg-surface p-2.5 rounded border border-border">
                        <dt className="text-ink-muted">Lost proposal score</dt>
                        <dd className="font-mono font-bold text-sm text-ink">{Number(benchmarkResult.lostScore).toFixed(4)}</dd>
                        <dd className="text-ink-muted truncate">{benchmarkResult.lostTitle}</dd>
                      </div>
                      <div className="bg-surface p-2.5 rounded border border-accent">
                        <dt className="text-ink-muted font-semibold">Ratio</dt>
                        <dd className="font-mono font-bold text-base text-ink">{Number(benchmarkResult.ratio).toFixed(3)}×</dd>
                        <dd className="text-ink-muted">Target ≥ 1.20×</dd>
                      </div>
                    </dl>
                  </div>
                )}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                runInspectorSearch();
              }}
              className="flex gap-2 mb-4"
            >
              <label htmlFor="inspector-query" className="sr-only">
                Retrieval query
              </label>
              <input id="inspector-query" type="search" value={inspectorQuery} onChange={(e) => setInspectorQuery(e.target.value)} placeholder="Enter a query to inspect ranking…" className="input-field" />
              <button type="submit" disabled={inspecting} className="btn-dark">
                Search
              </button>
            </form>

            <h3 className="field-label">Ranked results ({inspectorResults.length})</h3>
            <ol className="space-y-3 mt-2">
              {inspectorResults.map((r, idx) => {
                const multiplier = r.outcome === 'won' ? Number(weightWon).toFixed(2) : r.outcome === 'lost' ? Number(weightLost).toFixed(2) : '1.00';
                return (
                  <li key={r.id} className="p-4 rounded-lg border border-border bg-surface flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className={`w-8 h-8 rounded-full flex items-center justify-center font-bold font-mono text-xs flex-shrink-0 ${idx === 0 ? 'bg-accent text-accent-ink' : 'bg-surface-raised text-ink'}`}>#{idx + 1}</span>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-0.5">
                          <DocumentTypeBadge type={r.type} />
                          <OutcomeBadge outcome={r.outcome} />
                          <span className="text-xs text-ink-muted font-mono">×{multiplier}</span>
                        </div>
                        <button type="button" onClick={() => setViewerDoc(r)} className="text-sm font-bold text-ink hover:text-accent text-left rounded">
                          {r.title}
                        </button>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 self-end sm:self-auto">
                      <button type="button" onClick={() => setViewerDoc(r)} className="btn-secondary text-xs px-2 py-1">
                        <Eye className="w-3.5 h-3.5" aria-hidden="true" />
                        <span>View</span>
                      </button>
                      <div className="text-right">
                        <div className="text-xs text-ink-muted">Score</div>
                        <div className="font-mono font-bold text-base text-ink">{Number(r.similarity_score || 0).toFixed(4)}</div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        </div>
      )}

      <Modal
        open={Boolean(viewerDoc)}
        onClose={() => setViewerDoc(null)}
        title={viewerDoc?.title}
        size="xl"
        footer={
          <>
            <button type="button" onClick={() => viewerDoc && copyDoc(viewerDoc)} className="btn-secondary">
              {copied ? <Check className="w-3.5 h-3.5 text-success" aria-hidden="true" /> : <Copy className="w-3.5 h-3.5" aria-hidden="true" />}
              <span>{copied ? 'Copied' : 'Copy Markdown'}</span>
            </button>
            <button type="button" onClick={() => viewerDoc && openInGoogleDocs(viewerDoc)} className="btn-primary">
              <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Open in Google Docs</span>
            </button>
          </>
        }
      >
        {viewerDoc && (
          <>
            <div className="flex flex-wrap items-center gap-2 mb-4 text-xs text-ink-muted">
              <DocumentTypeBadge type={viewerDoc.type} />
              <OutcomeBadge outcome={viewerDoc.outcome} />
              <span>{viewerDoc.content.split(/\s+/).filter(Boolean).length} words</span>
              {viewerDoc.services?.length > 0 && <span>· {viewerDoc.services.map(getServiceName).join(', ')}</span>}
            </div>
            <MarkdownRenderer content={viewerDoc.content} />
          </>
        )}
      </Modal>

      <Modal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Add knowledge base document"
        description="Documents are chunked and indexed for retrieval immediately on save."
        size="lg"
        footer={
          <>
            <button type="button" onClick={() => setIsModalOpen(false)} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" form="kb-create-form" disabled={submitting} className="btn-primary">
              {submitting ? 'Indexing…' : 'Save & index'}
            </button>
          </>
        }
      >
        <form id="kb-create-form" onSubmit={handleCreateSubmit} className="space-y-4">
          {formError && (
            <p role="alert" className="p-3 rounded-md bg-danger-soft border border-danger/40 text-sm text-ink">
              {formError}
            </p>
          )}

          <div role="tablist" aria-label="Input method" className="flex border border-border-strong rounded-md p-1 bg-surface-raised gap-1">
            {[
              { id: 'paste', label: 'Paste text' },
              { id: 'upload', label: 'Upload file (.txt, .md)' },
            ].map((m) => (
              <button key={m.id} type="button" role="tab" aria-selected={inputMode === m.id} onClick={() => setInputMode(m.id)} className={`flex-1 py-1.5 text-xs font-semibold rounded transition-colors ${inputMode === m.id ? 'bg-accent text-accent-ink' : 'text-ink-muted hover:text-ink'}`}>
                {m.label}
              </button>
            ))}
          </div>

          {inputMode === 'upload' && (
            <div className="border-2 border-dashed border-border-strong rounded-lg p-6 text-center">
              <Upload className="w-8 h-8 text-ink-muted mx-auto mb-2" aria-hidden="true" />
              <label htmlFor="kb-file" className="btn-secondary cursor-pointer text-xs">
                Browse file
              </label>
              <input id="kb-file" type="file" accept=".txt,.md,.markdown" onChange={handleFileUpload} className="sr-only" />
              <p className="help-text mt-2">Plain-text and Markdown files are read in the browser.</p>
            </div>
          )}

          <div>
            <label htmlFor="kb-title" className="field-label">
              Title <span className="text-danger" aria-hidden="true">*</span>
            </label>
            <input id="kb-title" type="text" required aria-required="true" placeholder="e.g. Retail replatforming proposal — 2024" value={formData.title} onChange={(e) => setFormData({ ...formData, title: e.target.value })} className="input-field" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="kb-doc-type" className="field-label">
                Document type <span className="text-danger" aria-hidden="true">*</span>
              </label>
              <select id="kb-doc-type" value={formData.type} onChange={(e) => setFormData({ ...formData, type: e.target.value })} className="input-field">
                <option value="past_proposal">Past proposal</option>
                <option value="case_study">Case study</option>
                <option value="boilerplate">Boilerplate</option>
                <option value="testimonial">Testimonial</option>
                <option value="pitch_deck">Pitch deck</option>
              </select>
            </div>
            <div>
              <label htmlFor="kb-doc-outcome" className="field-label">
                Outcome
              </label>
              <select id="kb-doc-outcome" value={formData.outcome} onChange={(e) => setFormData({ ...formData, outcome: e.target.value })} className="input-field">
                <option value="won">Won (boosted)</option>
                <option value="lost">Lost (penalised)</option>
                <option value="n/a">N/A (neutral)</option>
              </select>
            </div>
          </div>

          <fieldset>
            <legend className="field-label">Tag services</legend>
            <div className="flex flex-wrap gap-1.5">
              {services.map((s) => {
                const on = formData.service_ids.includes(s.id);
                return (
                  <button key={s.id} type="button" role="checkbox" aria-checked={on} onClick={() => toggleFormService(s.id)} className={`text-xs px-2.5 py-1 rounded border transition-colors ${on ? 'bg-accent text-accent-ink border-accent font-semibold' : 'bg-surface text-ink border-border-strong hover:bg-surface-raised'}`}>
                    {s.name}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label htmlFor="kb-content" className="field-label mb-0">
                Content <span className="text-danger" aria-hidden="true">*</span>
              </label>
              <span className="help-text font-mono">{formData.content.length} chars</span>
            </div>
            <textarea id="kb-content" required aria-required="true" rows={8} placeholder="Paste proposal text, case-study metrics, or boilerplate credentials…" value={formData.content} onChange={(e) => setFormData({ ...formData, content: e.target.value })} className="input-field font-mono leading-relaxed" />
          </div>
        </form>
      </Modal>
    </div>
  );
}
