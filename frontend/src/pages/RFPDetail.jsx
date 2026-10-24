import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ArrowLeft, Loader2, AlertCircle, FileText, Search, BookOpen, List, Plus, ArrowUpRight, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import { normalizeClassification } from '../components/Badge';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmDialog';
import RFPHeader from '../components/rfp/RFPHeader';
import OutcomePanel from '../components/rfp/OutcomePanel';
import OpenQuestionsRibbon from '../components/rfp/OpenQuestionsRibbon';
import BrainDumpPanel from '../components/rfp/BrainDumpPanel';
import SectionCard from '../components/rfp/SectionCard';
import FullDocumentView from '../components/rfp/FullDocumentView';
import OriginalBriefView, { OriginalBriefDrawer, briefAsText } from '../components/rfp/OriginalBriefView';
import { EditDetailsModal, AddSectionModal, ExportSuccessModal } from '../components/rfp/RFPModals';
import { appendMarkdown, sortSections } from '../components/rfp/markdownInsert';
import { formatGBP } from '../components/Badge';

const EMPTY_EDIT = { client_name: '', value: '', budget_type: 'fixed', budget_notes: '', deadline: '', status: 'draft', outcome_feedback: '', hubspot_deal_id: '' };
const EMPTY_SECTION = { heading: '', original_text: '', classification: 'strategic_decision' };

function useMap(initial = {}) {
  const [map, setMap] = useState(initial);
  const set = useCallback((key, value) => setMap((prev) => ({ ...prev, [key]: value })), []);
  const unset = useCallback(
    (key) =>
      setMap((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      }),
    []
  );
  return [map, set, unset, setMap];
}

export default function RFPDetail({ rfpId, onBack }) {
  const toast = useToast();
  const confirm = useConfirm();

  const [rfp, setRfp] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [isClassifying, setIsClassifying] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [batchGenerating, setBatchGenerating] = useState(false);
  const [batchProgress, setBatchProgress] = useState(null);
  const [exportResult, setExportResult] = useState(null);

  const [generating, setGenerating, unsetGenerating] = useMap();
  const [updatingSection, setUpdatingSection, unsetUpdatingSection] = useMap();
  const [savingEditor, setSavingEditor, unsetSavingEditor] = useMap();
  const [savingNote, setSavingNote, unsetSavingNote] = useMap();
  const [resolving, setResolving, unsetResolving] = useMap();
  const [deletingSectionId, setDeletingSectionId] = useState(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [mainViewTab, setMainViewTab] = useState('sections');
  const [showOriginalDrawer, setShowOriginalDrawer] = useState(false);

  const [brainDumpExpanded, setBrainDumpExpanded] = useState(true);
  const [brainDumpText, setBrainDumpText] = useState('');
  const [isSavingBrainDump, setIsSavingBrainDump] = useState(false);

  const [openQuestionsExpanded, setOpenQuestionsExpanded] = useState(true);
  const [resolutionInputs, setResolutionInput] = useMap();

  const [notesExpanded, setNotesExpanded] = useMap();
  const [noteInputs, setNoteInput] = useMap();
  const [viewModes, setViewMode] = useMap();
  const [editorContents, setEditorContent, , setEditorContents] = useMap();
  const [previewModes, setPreviewMode] = useMap();
  const [provenanceMap, setProvenance] = useMap();
  const [engineMap, setEngine] = useMap();

  const [outcomeSelection, setOutcomeSelection] = useState('pending');
  const [outcomeFeedback, setOutcomeFeedback] = useState('');
  const [isSavingOutcome, setIsSavingOutcome] = useState(false);

  const [showEditDetails, setShowEditDetails] = useState(false);
  const [editForm, setEditForm] = useState(EMPTY_EDIT);
  const [isSavingDetails, setIsSavingDetails] = useState(false);

  const [showAddSection, setShowAddSection] = useState(false);
  const [sectionForm, setSectionForm] = useState(EMPTY_SECTION);
  const [isAddingSection, setIsAddingSection] = useState(false);

  const [copiedFullDoc, setCopiedFullDoc] = useState(false);
  const [inline, setInline] = useState({ sectionId: null, content: '', saving: false });
  const [inlinePreview, setInlinePreview] = useState(false);

  const sectionRefs = useRef({});

  const refresh = useCallback(async () => {
    const data = await api.getRFP(rfpId);
    setRfp(data);
    return data;
  }, [rfpId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const data = await api.getRFP(rfpId);
        if (cancelled) return;
        setRfp(data);
        const status = (data.status || 'draft').toLowerCase();
        setOutcomeSelection(['won', 'lost', 'no decision'].includes(status) ? status : 'pending');
        setOutcomeFeedback(data.outcome_feedback || '');
        const initial = {};
        (data.sections || []).forEach((s) => {
          initial[s.id] = s.final_content || s.draft_content || '';
        });
        setEditorContents(initial);
      } catch (err) {
        if (!cancelled) setLoadError(err.message || 'Could not load the RFP.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [rfpId, setEditorContents]);

  async function run(fn, { success, failure }) {
    try {
      await fn();
      if (success) toast.success(success);
    } catch (err) {
      toast.error(err.message || failure || 'Something went wrong.');
    }
  }

  // ---- Header actions -------------------------------------------------------
  async function handleExport() {
    setIsExporting(true);
    await run(
      async () => {
        const res = await api.exportToGoogleDocs(rfp.id);
        await refresh();
        setExportResult({
          docUrl: res.doc_url,
          mode: res.mode || 'mock',
          commentCount: res.payload?.comments?.length || 0,
          docTitle: res.payload?.create_document?.title || `RFP response — ${rfp.client_name}`,
        });
      },
      { failure: 'Export failed.' }
    );
    setIsExporting(false);
  }

  async function handleClassify() {
    setIsClassifying(true);
    await run(
      async () => {
        const result = await api.classifyRFP(rfp.id);
        const refreshed = await refresh();
        const engine = result?.engine ? { engine: result.engine, model: result.model } : null;
        if (engine) (refreshed.sections || []).forEach((s) => setEngine(`classify-${s.id}`, engine));
        const n = Array.isArray(result?.classifications) ? result.classifications.length : refreshed.sections?.length || 0;
        toast.success(`Classified ${n} sections${engine ? ` with ${engine.engine === 'mock' ? 'the mock engine' : engine.model}` : ''}.`);
      },
      { failure: 'Classification failed.' }
    );
    setIsClassifying(false);
  }

  async function generateOne(sectionId, { quiet = false } = {}) {
    setGenerating(sectionId, true);
    try {
      const res = await api.generateSectionDraft(rfp.id, sectionId);
      if (res?.provenance) setProvenance(sectionId, res.provenance);
      if (res?.engine) setEngine(sectionId, { engine: res.engine, model: res.model });
      if (res?.draft_content) setEditorContent(sectionId, res.draft_content);
      if (!quiet) {
        await refresh();
        toast.success('Draft generated.');
      }
      return true;
    } catch (err) {
      if (!quiet) toast.error(err.message || 'Draft generation failed.');
      return false;
    } finally {
      unsetGenerating(sectionId);
    }
  }

  async function handleGenerateAll() {
    const pending = (rfp.sections || []).filter((s) => !s.draft_content || s.status === 'pending');
    if (pending.length === 0) {
      toast.info('Every section already has a draft.');
      return;
    }
    setBatchGenerating(true);
    setBatchProgress({ done: 0, total: pending.length });
    let ok = 0;
    for (let i = 0; i < pending.length; i += 1) {
      if (await generateOne(pending[i].id, { quiet: true })) ok += 1;
      setBatchProgress({ done: i + 1, total: pending.length });
    }
    await refresh();
    setBatchGenerating(false);
    setBatchProgress(null);
    if (ok === pending.length) toast.success(`Drafted ${ok} section${ok === 1 ? '' : 's'}.`);
    else toast.warning(`Drafted ${ok} of ${pending.length} sections — some failed.`);
  }

  // ---- Outcome --------------------------------------------------------------
  async function handleSaveOutcome() {
    setIsSavingOutcome(true);
    const targetStatus = outcomeSelection === 'pending' ? (rfp.status === 'draft' ? 'draft' : 'submitted') : outcomeSelection;
    await run(
      async () => {
        await api.updateRFP(rfp.id, { status: targetStatus, outcome_feedback: outcomeFeedback.trim() });
        setRfp((prev) => ({ ...prev, status: targetStatus, outcome_feedback: outcomeFeedback.trim() }));
      },
      { success: 'Outcome saved.', failure: 'Failed to save outcome.' }
    );
    setIsSavingOutcome(false);
  }

  // ---- Details & sections ---------------------------------------------------
  function openEditDetails() {
    setEditForm({
      client_name: rfp.client_name || '',
      value: rfp.value != null ? String(rfp.value) : '',
      budget_type: rfp.budget_type || 'fixed',
      budget_notes: rfp.budget_notes || '',
      deadline: rfp.deadline || '',
      status: rfp.status || 'draft',
      outcome_feedback: rfp.outcome_feedback || '',
      hubspot_deal_id: rfp.hubspot_deal_id || '',
    });
    setShowEditDetails(true);
  }

  async function handleSaveDetails(e) {
    e.preventDefault();
    setIsSavingDetails(true);
    await run(
      async () => {
        await api.updateRFP(rfp.id, {
          client_name: editForm.client_name.trim(),
          value: editForm.value ? parseFloat(editForm.value) : null,
          budget_type: editForm.budget_type,
          budget_notes: editForm.budget_notes.trim(),
          deadline: editForm.deadline || null,
          status: editForm.status,
          outcome_feedback: editForm.outcome_feedback.trim(),
          hubspot_deal_id: editForm.hubspot_deal_id?.trim() || null,
        });
        await refresh();
        setShowEditDetails(false);
      },
      { success: 'RFP details updated.', failure: 'Failed to update details.' }
    );
    setIsSavingDetails(false);
  }

  async function handleAddSection(e) {
    e.preventDefault();
    if (!sectionForm.heading.trim()) return;
    setIsAddingSection(true);
    await run(
      async () => {
        await api.addSection(rfp.id, { heading: sectionForm.heading.trim(), original_text: sectionForm.original_text.trim(), classification: sectionForm.classification });
        await refresh();
        setShowAddSection(false);
        setSectionForm(EMPTY_SECTION);
      },
      { success: 'Section added.', failure: 'Failed to add section.' }
    );
    setIsAddingSection(false);
  }

  async function handleDeleteSection(sectionId, heading) {
    const ok = await confirm({ title: `Delete "${heading || 'this section'}"?`, message: 'The section, its draft and any notes or open questions attached to it will be removed.', confirmLabel: 'Delete section', danger: true });
    if (!ok) return;
    setDeletingSectionId(sectionId);
    await run(
      async () => {
        await api.deleteSection(rfp.id, sectionId);
        await refresh();
      },
      { success: 'Section deleted.', failure: 'Failed to delete section.' }
    );
    setDeletingSectionId(null);
  }

  async function handleMoveSection(sectionId, direction) {
    const sorted = sortSections(rfp.sections);
    const idx = sorted.findIndex((s) => s.id === sectionId);
    const target = direction === 'up' ? idx - 1 : idx + 1;
    if (idx === -1 || target < 0 || target >= sorted.length) return;
    [sorted[idx], sorted[target]] = [sorted[target], sorted[idx]];
    const updated = sorted.map((s, i) => ({ ...s, sort_order: i + 1 }));
    setRfp((prev) => ({ ...prev, sections: updated }));
    try {
      await api.reorderSections(rfp.id, updated.map((s) => s.id));
    } catch (err) {
      await refresh();
      toast.error(err.message || 'Failed to save section order.');
    }
  }

  async function patchSection(sectionId, patch, label) {
    const previous = rfp.sections;
    setRfp((prev) => ({ ...prev, sections: prev.sections.map((s) => (s.id === sectionId ? { ...s, ...patch } : s)) }));
    setUpdatingSection(sectionId, true);
    try {
      await api.updateSection(rfp.id, sectionId, patch);
    } catch (err) {
      setRfp((prev) => ({ ...prev, sections: previous }));
      toast.error(`Failed to update ${label}: ${err.message}`);
    } finally {
      unsetUpdatingSection(sectionId);
    }
  }

  // ---- Notes ----------------------------------------------------------------
  async function handleSaveBrainDump(e) {
    e.preventDefault();
    if (!brainDumpText.trim()) return;
    setIsSavingBrainDump(true);
    await run(
      async () => {
        await api.createNote(rfp.id, { raw_content: brainDumpText.trim(), section_id: null });
        setBrainDumpText('');
        await refresh();
      },
      { success: 'Note saved.', failure: 'Failed to save note.' }
    );
    setIsSavingBrainDump(false);
  }

  async function handleSaveSectionNote(sectionId) {
    const text = (noteInputs[sectionId] || '').trim();
    if (!text) return;
    setSavingNote(sectionId, true);
    await run(
      async () => {
        await api.createNote(rfp.id, { raw_content: text, section_id: sectionId });
        setNoteInput(sectionId, '');
        await refresh();
      },
      { success: 'Section note saved.', failure: 'Failed to save note.' }
    );
    unsetSavingNote(sectionId);
  }

  async function handleDeleteNote(noteId) {
    await run(
      async () => {
        await api.deleteNote(rfp.id, noteId);
        await refresh();
      },
      { success: 'Note removed.', failure: 'Failed to delete note.' }
    );
  }

  // ---- Open questions -------------------------------------------------------
  async function handleResolve(questionId, sectionId) {
    const text = (resolutionInputs[questionId] || '').trim();
    if (!text) return;
    setResolving(questionId, true);
    await run(
      async () => {
        await api.resolveOpenQuestion(rfp.id, questionId, { resolution: text, status: 'resolved' });
        await generateOne(sectionId, { quiet: true });
        await refresh();
        setResolutionInput(questionId, '');
      },
      { success: 'Question resolved and section regenerated.', failure: 'Failed to resolve question.' }
    );
    unsetResolving(questionId);
  }

  // ---- Editors --------------------------------------------------------------
  async function handleSaveFinal(sectionId) {
    setSavingEditor(sectionId, true);
    await run(
      async () => {
        await api.updateSection(rfp.id, sectionId, { final_content: editorContents[sectionId] || '', status: 'resolved' });
        await refresh();
      },
      { success: 'Final response saved and marked resolved.', failure: 'Failed to save response.' }
    );
    unsetSavingEditor(sectionId);
  }

  async function handleInlineSave(sectionId) {
    setInline((p) => ({ ...p, saving: true }));
    await run(
      async () => {
        await api.updateSection(rfp.id, sectionId, { final_content: inline.content, status: 'resolved' });
        await refresh();
        setInline({ sectionId: null, content: '', saving: false });
      },
      { success: 'Section updated.', failure: 'Failed to update section.' }
    );
    setInline((p) => ({ ...p, saving: false }));
  }

  function copyFullDocument() {
    const body = sortSections(rfp.sections)
      .map((sec, i) => `## ${i + 1}. ${sec.heading}\n\n${sec.final_content || sec.draft_content || sec.original_text || '[No draft generated]'}`)
      .join('\n\n---\n\n');
    const header = `# Proposal response: ${rfp.client_name}\n**Status**: ${rfp.status || 'Draft'} | **Budget**: ${formatGBP(rfp.value)} (${rfp.budget_type || 'fixed'})\n\n---\n\n`;
    navigator.clipboard.writeText(header + body);
    setCopiedFullDoc(true);
    setTimeout(() => setCopiedFullDoc(false), 2500);
    toast.info('Full document copied as Markdown.');
  }

  function scrollToSection(sectionId) {
    const el = sectionRefs.current[sectionId];
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.classList.add('ring-2', 'ring-accent');
    setTimeout(() => el.classList.remove('ring-2', 'ring-accent'), 2000);
  }

  // ---- Render ---------------------------------------------------------------
  if (loading) {
    return (
      <div className="max-w-7xl mx-auto py-12 px-4 text-center" role="status">
        <Loader2 className="w-8 h-8 animate-spin mx-auto text-accent mb-3" aria-hidden="true" />
        <p className="text-sm font-medium text-ink-muted">Loading RFP…</p>
      </div>
    );
  }

  if (loadError || !rfp) {
    return (
      <div className="max-w-2xl mx-auto py-12 px-4">
        <div role="alert" className="card border-danger/40">
          <div className="flex items-center gap-3 mb-3">
            <AlertCircle className="w-6 h-6 text-danger" aria-hidden="true" />
            <h2 className="text-lg font-bold text-ink">Failed to load RFP</h2>
          </div>
          <p className="text-sm text-ink-muted mb-4">{loadError || 'Not found.'}</p>
          <button type="button" onClick={onBack} className="btn-secondary">
            Back to RFP Tracker
          </button>
        </div>
      </div>
    );
  }

  const sections = rfp.sections || [];
  const notes = rfp.notes || [];
  const openQuestions = rfp.open_questions || [];
  const wholeRfpNotes = notes.filter((n) => n.section_id == null);
  const unresolved = openQuestions.filter((q) => q.status === 'open');
  const sorted = sortSections(sections);
  const filtered = sorted.filter((sec) => {
    const norm = normalizeClassification(sec.classification);
    const q = searchTerm.toLowerCase();
    return (categoryFilter === 'all' || norm === categoryFilter) && [sec.heading, sec.original_text, sec.draft_content].some((t) => (t || '').toLowerCase().includes(q));
  });
  const counts = {
    drafted: sections.filter((s) => s.status === 'drafted' || s.draft_content).length,
    resolved: sections.filter((s) => s.status === 'resolved').length,
  };

  const tabs = [
    { id: 'sections', label: `Sections (${sections.length})`, icon: List },
    { id: 'full-document', label: 'Full document', icon: FileText },
    { id: 'original-brief', label: 'Original brief', icon: BookOpen },
  ];

  const sectionActions = {
    move: handleMoveSection,
    changeStatus: (id, status) => patchSection(id, { status }, 'status'),
    changeClassification: (id, classification) => patchSection(id, { classification }, 'classification'),
    toggleNotes: (id) => setNotesExpanded(id, !notesExpanded[id]),
    generate: (id) => generateOne(id),
    remove: handleDeleteSection,
    deleteNote: handleDeleteNote,
    setNoteInput,
    saveNote: handleSaveSectionNote,
    setResolutionInput,
    resolve: handleResolve,
    setViewMode,
    startEditing: (sec) => {
      setViewMode(sec.id, 'editor');
      setEditorContent(sec.id, sec.final_content || sec.draft_content);
    },
    insertMarkdown: (id, syntax) => setEditorContent(id, appendMarkdown(editorContents[id] ?? '', syntax)),
    togglePreview: (id) => setPreviewMode(id, !previewModes[id]),
    setEditorContent,
    saveFinal: handleSaveFinal,
  };

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
      <button type="button" onClick={onBack} className="btn-ghost -ml-2 mb-6 text-xs">
        <ArrowLeft className="w-4 h-4" aria-hidden="true" />
        <span>Back to RFP Tracker</span>
      </button>

      <RFPHeader
        rfp={rfp}
        sectionCount={sections.length}
        busy={{ isExporting, isClassifying, batchGenerating }}
        batchProgress={batchProgress}
        onEditDetails={openEditDetails}
        onExport={handleExport}
        onGenerateAll={handleGenerateAll}
        onClassify={handleClassify}
      />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-border mb-6 gap-2">
        <div role="tablist" aria-label="RFP views" className="flex gap-1 overflow-x-auto">
          {tabs.map((t) => {
            const Icon = t.icon;
            const active = mainViewTab === t.id;
            return (
              <button key={t.id} type="button" role="tab" aria-selected={active} onClick={() => setMainViewTab(t.id)} className={`tab -mb-px flex items-center gap-2 ${active ? 'tab-active' : ''}`}>
                <Icon className="w-4 h-4" aria-hidden="true" />
                <span>{t.label}</span>
              </button>
            );
          })}
        </div>
        {mainViewTab === 'sections' && (
          <button type="button" onClick={() => setShowOriginalDrawer((v) => !v)} aria-pressed={showOriginalDrawer} className="btn-ghost text-xs border border-border-strong self-start sm:self-auto">
            <BookOpen className="w-3.5 h-3.5" aria-hidden="true" />
            <span>{showOriginalDrawer ? 'Hide brief panel' : 'Show brief panel'}</span>
          </button>
        )}
      </div>

      {rfp.final_doc_link && (
        <div className="card mb-6 border-l-4 border-l-accent p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-10 h-10 rounded bg-accent-soft text-accent flex items-center justify-center flex-shrink-0">
              <FileText className="w-5 h-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-ink">Exported document</h2>
                <span className={`chip ${rfp.final_doc_link.includes('mock') ? 'chip-warning' : 'chip-success'}`}>{rfp.final_doc_link.includes('mock') ? 'Mock' : 'Live'}</span>
              </div>
              <a href={rfp.final_doc_link} target="_blank" rel="noopener noreferrer" className="text-xs text-accent underline font-mono break-all mt-1 inline-block">
                {rfp.final_doc_link}
              </a>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <a href={rfp.final_doc_link} target="_blank" rel="noopener noreferrer" className="btn-primary text-xs">
              <span>Open</span>
              <ArrowUpRight className="w-3.5 h-3.5" aria-hidden="true" />
            </a>
            <button type="button" onClick={handleExport} disabled={isExporting} className="btn-secondary text-xs">
              <RefreshCw className={`w-3.5 h-3.5 ${isExporting ? 'animate-spin' : ''}`} aria-hidden="true" />
              <span>Re-export</span>
            </button>
          </div>
        </div>
      )}

      {mainViewTab === 'sections' && (
        <>
          <OutcomePanel selection={outcomeSelection} onSelect={setOutcomeSelection} feedback={outcomeFeedback} onFeedbackChange={setOutcomeFeedback} saving={isSavingOutcome} onSave={handleSaveOutcome} />

          <OpenQuestionsRibbon
            questions={unresolved}
            sections={sections}
            expanded={openQuestionsExpanded}
            onToggle={() => setOpenQuestionsExpanded((v) => !v)}
            inputs={resolutionInputs}
            onInputChange={setResolutionInput}
            resolving={resolving}
            onResolve={handleResolve}
            onJump={scrollToSection}
          />

          <BrainDumpPanel notes={wholeRfpNotes} expanded={brainDumpExpanded} onToggle={() => setBrainDumpExpanded((v) => !v)} text={brainDumpText} onTextChange={setBrainDumpText} saving={isSavingBrainDump} onSave={handleSaveBrainDump} onDeleteNote={handleDeleteNote} />

          <div className="card mb-6 p-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <label htmlFor="section-search" className="sr-only">
                  Search sections
                </label>
                <Search className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
                <input id="section-search" type="search" placeholder="Search headings, requirements or drafts…" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} className="input-field pl-9" />
              </div>
              <div>
                <label htmlFor="section-category" className="sr-only">
                  Filter by classification
                </label>
                <select id="section-category" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="input-field sm:w-56">
                  <option value="all">All categories</option>
                  <option value="strategic_decision">Strategic decisions</option>
                  <option value="gap">Information gaps</option>
                  <option value="pricing">Pricing</option>
                  <option value="boilerplate">Boilerplate</option>
                  <option value="compliance_admin">Compliance / admin</option>
                </select>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-ink">
                  Response sections ({filtered.length} of {sections.length})
                </h2>
                <p className="help-text font-mono">
                  {counts.drafted} drafted · {counts.resolved} resolved
                </p>
              </div>
              <button type="button" onClick={() => setShowAddSection(true)} className="btn-dark text-xs">
                <Plus className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Add section</span>
              </button>
            </div>

            {sections.length === 0 ? (
              <div className="card text-center py-12">
                <FileText className="w-10 h-10 mx-auto text-ink-muted mb-3" aria-hidden="true" />
                <p className="font-bold text-ink">No sections yet</p>
                <p className="help-text mt-1">Upload a document or add sections manually to begin drafting.</p>
              </div>
            ) : filtered.length === 0 ? (
              <p className="card text-center py-8 text-ink-muted text-sm">No sections match the current filter.</p>
            ) : (
              filtered.map((section, idx) => {
                const fullIndex = sorted.findIndex((s) => s.id === section.id);
                return (
                  <SectionCard
                    key={section.id}
                    innerRef={(el) => {
                      sectionRefs.current[section.id] = el;
                    }}
                    section={section}
                    index={idx}
                    isFirst={fullIndex <= 0}
                    isLast={fullIndex >= sorted.length - 1}
                    notes={notes}
                    openQuestions={openQuestions}
                    provenance={provenanceMap[section.id]}
                    engine={engineMap[section.id]}
                    busy={{
                      saving: Boolean(updatingSection[section.id]),
                      drafting: Boolean(generating[section.id]),
                      savingEditor: Boolean(savingEditor[section.id]),
                      savingNote: Boolean(savingNote[section.id]),
                      deleting: deletingSectionId === section.id,
                      resolving,
                    }}
                    ui={{
                      viewMode: viewModes[section.id],
                      editorContent: editorContents[section.id],
                      previewMode: previewModes[section.id],
                      notesExpanded: Boolean(notesExpanded[section.id]),
                      noteInput: noteInputs[section.id],
                      resolutionInputs,
                    }}
                    actions={sectionActions}
                  />
                );
              })
            )}
          </div>
        </>
      )}

      {mainViewTab === 'full-document' && (
        <FullDocumentView
          rfp={rfp}
          sections={sections}
          copied={copiedFullDoc}
          onCopy={copyFullDocument}
          onExport={handleExport}
          exporting={isExporting}
          inline={inline}
          onStartInline={(sec) => {
            setInlinePreview(false);
            setInline({ sectionId: sec.id, content: sec.final_content ?? sec.draft_content ?? '', saving: false });
          }}
          onInlineChange={(content) => setInline((p) => ({ ...p, content }))}
          onInlineInsert={(syntax) => setInline((p) => ({ ...p, content: appendMarkdown(p.content, syntax) }))}
          onInlineSave={handleInlineSave}
          onInlineCancel={() => setInline({ sectionId: null, content: '', saving: false })}
          inlinePreview={inlinePreview}
          onToggleInlinePreview={() => setInlinePreview((v) => !v)}
        />
      )}

      {mainViewTab === 'original-brief' && (
        <OriginalBriefView
          rfp={rfp}
          sections={sorted}
          onCopy={() => {
            navigator.clipboard.writeText(briefAsText(rfp, sorted));
            toast.info('Original brief copied.');
          }}
        />
      )}

      {showOriginalDrawer && mainViewTab === 'sections' && <OriginalBriefDrawer rfp={rfp} sections={sorted} onClose={() => setShowOriginalDrawer(false)} />}

      <EditDetailsModal open={showEditDetails} onClose={() => setShowEditDetails(false)} form={editForm} onChange={(patch) => setEditForm((p) => ({ ...p, ...patch }))} saving={isSavingDetails} onSubmit={handleSaveDetails} />
      <AddSectionModal open={showAddSection} onClose={() => setShowAddSection(false)} form={sectionForm} onChange={(patch) => setSectionForm((p) => ({ ...p, ...patch }))} saving={isAddingSection} onSubmit={handleAddSection} />
      <ExportSuccessModal result={exportResult} onClose={() => setExportResult(null)} />
    </div>
  );
}
