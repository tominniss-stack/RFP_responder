import React, { useState, useEffect } from 'react';
import { Key, Cpu, MessageSquare, FileCheck, Save, RotateCcw, Eye, EyeOff, ArrowUpRight, Tag, Banknote, Sliders, Trash2 } from 'lucide-react';
import { api } from '../services/api';
import ServicesAdmin from './ServicesAdmin';
import PricingAdmin from './PricingAdmin';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmDialog';

export const DEFAULT_CLASSIFICATION_MODEL = 'gemini-2.5-flash';
export const DEFAULT_GENERATION_MODEL = 'claude-sonnet-4-5';

const CLASSIFICATION_MODELS = [
  { value: 'gemini-2.5-flash', label: 'Google Gemini 2.5 Flash (recommended for intake)' },
  { value: 'gemini-2.5-flash-lite', label: 'Google Gemini 2.5 Flash-Lite (fastest)' },
  { value: 'claude-haiku-4-5', label: 'Anthropic Claude Haiku 4.5' },
  { value: 'claude-sonnet-4-5', label: 'Anthropic Claude Sonnet 4.5' },
  { value: 'mock-deterministic', label: 'Mock deterministic (offline)' },
];

const GENERATION_MODELS = [
  { value: 'claude-sonnet-4-5', label: 'Anthropic Claude Sonnet 4.5 (recommended for drafting)' },
  { value: 'claude-opus-4-1', label: 'Anthropic Claude Opus 4.1 (maximum capability)' },
  { value: 'gemini-2.5-pro', label: 'Google Gemini 2.5 Pro' },
  { value: 'gemini-2.5-flash', label: 'Google Gemini 2.5 Flash' },
  { value: 'mock-deterministic', label: 'Mock deterministic (offline)' },
];

export const DEFAULT_SYSTEM_PROMPT = `You are an internal drafting assistant for Another Marketing Agency, helping staff prepare first-draft responses to Requests for Proposal (RFPs).

Your task is to generate a first draft for ONE section of an RFP response at a time.
You will be given:
- The original RFP question/requirement text for this section
- Retrieved reference material (past proposals, case studies, testimonials, pitch deck content) relevant to this section
- Structured pricing data, where relevant
- Boilerplate company information, where relevant
- Notes from the account manager (transcript excerpts, bullet points, or specific guidance for this project)

Rules:
1. Only use information present in the material provided. Never invent client names, figures, dates, credentials, past project details, or capabilities that are not explicitly present in your reference material.
2. Pricing figures must be reproduced exactly as given in the structured pricing data. Never estimate, round, or paraphrase a number.
3. If the provided material is insufficient to properly answer the section, write a brief, professional acknowledgement of the requirement (e.g. "We understand the need for..."), then insert the exact marker:
   [MORE INFO REQUIRED: brief description of what's missing]
   Do not attempt to plausibly guess the missing detail.
4. Match the structure, terminology, and level of detail implied by the original RFP question.
5. Write in the voice and style set out in the accompanying tone-of-voice instructions.
6. Output only the drafted section content, plus any [MORE INFO REQUIRED] markers. Do not include commentary about your own process.`;

export const DEFAULT_TONE_OF_VOICE = `Write in Another Marketing Agency's house tone:
- Confident but not arrogant; direct and clear over clever or jargon-heavy
- Human and conversational, avoiding generic "corporate AI" phrasing (e.g. avoid "we are excited to leverage synergies")
- Short, punchy sentences over long compound ones where possible
- Show, don't just claim — back statements with specific evidence from case studies/testimonials rather than vague assertions of quality`;

const MASK_MARKER = '••••';

function SecretField({ id, label, value, onChange, placeholder, help, optional }) {
  const [show, setShow] = useState(false);
  const isMasked = typeof value === 'string' && value.includes(MASK_MARKER);
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label htmlFor={id} className="text-sm font-semibold text-ink">
          {label}
        </label>
        {optional && <span className="help-text font-mono">Optional</span>}
      </div>
      <div className="relative">
        <input
          id={id}
          type={show && !isMasked ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={(e) => {
            if (isMasked) e.target.select();
          }}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
          className="input-field pr-20 font-mono"
          aria-describedby={`${id}-help`}
        />
        <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
          {!isMasked && (
            <button type="button" onClick={() => setShow((s) => !s)} className="btn-icon p-1.5" aria-label={show ? `Hide ${label}` : `Show ${label}`} aria-pressed={show}>
              {show ? <EyeOff className="w-4 h-4" aria-hidden="true" /> : <Eye className="w-4 h-4" aria-hidden="true" />}
            </button>
          )}
          {value && (
            <button type="button" onClick={() => onChange('')} className="btn-icon p-1.5 hover:text-danger" aria-label={`Clear ${label}`}>
              <Trash2 className="w-4 h-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
      <p id={`${id}-help`} className="help-text mt-1">
        {isMasked ? 'A key is stored. Type a new value to replace it, or clear it to remove.' : help}
      </p>
    </div>
  );
}

export default function Settings({ onSettingsUpdated, initialTab = 'ai' }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [activeTab, setActiveTab] = useState(initialTab || 'ai');
  const [formData, setFormData] = useState({
    classification_model: DEFAULT_CLASSIFICATION_MODEL,
    generation_model: DEFAULT_GENERATION_MODEL,
    claude_api_key: '',
    gemini_api_key: '',
    mock_google_export: true,
    google_credentials_path: 'credentials.json',
    system_prompt: DEFAULT_SYSTEM_PROMPT,
    tone_of_voice_prompt: DEFAULT_TONE_OF_VOICE,
    weight_won: 1.25,
    weight_lost: 0.9,
    hubspot_api_key: '',
    hubspot_portal_id: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (initialTab) setActiveTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.getSettings();
        if (data && !cancelled) {
          setFormData({
            classification_model: data.classification_model || DEFAULT_CLASSIFICATION_MODEL,
            generation_model: data.generation_model || DEFAULT_GENERATION_MODEL,
            claude_api_key: data.claude_api_key || '',
            gemini_api_key: data.gemini_api_key || '',
            mock_google_export: data.mock_google_export !== undefined ? Boolean(data.mock_google_export) : true,
            google_credentials_path: data.google_credentials_path || 'credentials.json',
            system_prompt: data.system_prompt || DEFAULT_SYSTEM_PROMPT,
            tone_of_voice_prompt: data.tone_of_voice_prompt || DEFAULT_TONE_OF_VOICE,
            weight_won: data.weight_won != null ? Number(data.weight_won) : 1.25,
            weight_lost: data.weight_lost != null ? Number(data.weight_lost) : 0.9,
            hubspot_api_key: data.hubspot_api_key || '',
            hubspot_portal_id: data.hubspot_portal_id || '',
          });
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Unable to load settings.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function set(field, value) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...formData,
        mock_google_export: Boolean(formData.mock_google_export),
        weight_won: parseFloat(formData.weight_won) || 1.25,
        weight_lost: parseFloat(formData.weight_lost) || 0.9,
      };
      const updated = await api.updateSettings(payload);
      if (updated) {
        setFormData((prev) => ({
          ...prev,
          claude_api_key: updated.claude_api_key || '',
          gemini_api_key: updated.gemini_api_key || '',
          hubspot_api_key: updated.hubspot_api_key || '',
        }));
      }
      toast.success('Settings saved. Changes apply to the next generation task.');
      onSettingsUpdated?.(updated || payload);
    } catch (err) {
      setError(err.message || 'Failed to update settings.');
    } finally {
      setSaving(false);
    }
  }

  async function handleResetPrompts() {
    const ok = await confirm({
      title: 'Reset prompts to defaults?',
      message: 'The master system prompt and tone-of-voice prompt will be replaced with the built-in defaults. You still need to save.',
      confirmLabel: 'Reset prompts',
    });
    if (ok) {
      setFormData((prev) => ({ ...prev, system_prompt: DEFAULT_SYSTEM_PROMPT, tone_of_voice_prompt: DEFAULT_TONE_OF_VOICE }));
    }
  }

  const tabs = [
    { id: 'ai', label: 'AI models & prompts', icon: Sliders },
    { id: 'services', label: 'Services', icon: Tag },
    { id: 'pricing', label: 'Pricing rate card', icon: Banknote },
  ];

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto py-12 px-4 text-center" role="status">
        <div className="animate-spin w-8 h-8 border-4 border-accent border-t-transparent rounded-full mx-auto mb-4" aria-hidden="true" />
        <p className="text-ink-muted font-medium">Loading settings…</p>
      </div>
    );
  }

  const ratio = (formData.weight_won / (formData.weight_lost || 1)).toFixed(3);

  return (
    <div className="max-w-5xl mx-auto py-8 px-4 sm:px-6">
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-ink-muted">Models, prompts, credentials, service taxonomy and the pricing rate card.</p>
      </div>

      <div role="tablist" aria-label="Settings sections" className="flex border-b border-border mb-8 gap-1 overflow-x-auto">
        {tabs.map((t) => {
          const Icon = t.icon;
          const active = activeTab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              aria-controls={`settings-panel-${t.id}`}
              id={`settings-tab-${t.id}`}
              onClick={() => setActiveTab(t.id)}
              className={`tab -mb-px flex items-center gap-2 ${active ? 'tab-active' : ''}`}
            >
              <Icon className="w-4 h-4" aria-hidden="true" />
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>

      {activeTab === 'services' && (
        <div role="tabpanel" id="settings-panel-services" aria-labelledby="settings-tab-services">
          <ServicesAdmin />
        </div>
      )}

      {activeTab === 'pricing' && (
        <div role="tabpanel" id="settings-panel-pricing" aria-labelledby="settings-tab-pricing">
          <PricingAdmin />
        </div>
      )}

      {activeTab === 'ai' && (
        <div role="tabpanel" id="settings-panel-ai" aria-labelledby="settings-tab-ai" className="max-w-4xl">
          {error && (
            <div role="alert" className="mb-6 p-4 rounded-md bg-danger-soft border border-danger/40 text-sm font-semibold text-ink">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-8">
            <section className="card" aria-labelledby="models-heading">
              <div className="flex items-center gap-2 border-b border-border pb-3 mb-5">
                <Cpu className="w-5 h-5 text-accent" aria-hidden="true" />
                <h2 id="models-heading" className="text-lg font-bold text-ink">
                  Model selection (two-tier)
                </h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label htmlFor="classification-model" className="block text-sm font-semibold text-ink mb-1">
                    Classification & intake model
                  </label>
                  <p className="help-text mb-2">Tier 1 — fast and inexpensive for parsing, classification and gap detection.</p>
                  <select id="classification-model" value={formData.classification_model} onChange={(e) => set('classification_model', e.target.value)} className="input-field">
                    {CLASSIFICATION_MODELS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="generation-model" className="block text-sm font-semibold text-ink mb-1">
                    Draft generation model
                  </label>
                  <p className="help-text mb-2">Tier 2 — higher capability for tone, RAG synthesis and nuance.</p>
                  <select id="generation-model" value={formData.generation_model} onChange={(e) => set('generation_model', e.target.value)} className="input-field">
                    {GENERATION_MODELS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </section>

            <section className="card" aria-labelledby="bias-heading">
              <div className="flex items-center gap-2 border-b border-border pb-3 mb-5">
                <Sliders className="w-5 h-5 text-accent" aria-hidden="true" />
                <div>
                  <h2 id="bias-heading" className="text-lg font-bold text-ink">
                    Outcome-weighted retrieval
                  </h2>
                  <p className="help-text">How strongly RAG retrieval favours content from won proposals over lost ones.</p>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label htmlFor="weight-won" className="text-sm font-semibold text-ink">
                      Won multiplier
                    </label>
                    <span className="chip chip-success font-mono">{Number(formData.weight_won).toFixed(2)}×</span>
                  </div>
                  <p className="help-text mb-2">Default 1.25 (+25%). Higher values lean harder on winning bids.</p>
                  <input id="weight-won" type="number" step="0.05" min="1.00" max="2.50" value={formData.weight_won} onChange={(e) => set('weight_won', parseFloat(e.target.value) || 1.0)} className="input-field font-mono" />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label htmlFor="weight-lost" className="text-sm font-semibold text-ink">
                      Lost multiplier
                    </label>
                    <span className="chip chip-danger font-mono">{Number(formData.weight_lost).toFixed(2)}×</span>
                  </div>
                  <p className="help-text mb-2">Default 0.90 (−10%). De-prioritises language from unsuccessful bids.</p>
                  <input id="weight-lost" type="number" step="0.05" min="0.10" max="1.00" value={formData.weight_lost} onChange={(e) => set('weight_lost', parseFloat(e.target.value) || 0.9)} className="input-field font-mono" />
                </div>
              </div>
              <p className="mt-4 sub-card text-xs">
                <strong>Current ratio:</strong> <span className="font-mono font-bold">{ratio}×</span> — won content ranks {ratio}× higher than equivalent lost content.
              </p>
            </section>

            <section className="card" aria-labelledby="keys-heading">
              <div className="flex items-center gap-2 border-b border-border pb-3 mb-5">
                <Key className="w-5 h-5 text-accent" aria-hidden="true" />
                <h2 id="keys-heading" className="text-lg font-bold text-ink">
                  API credentials
                </h2>
              </div>
              <p className="help-text mb-4">
                Keys are stored in the local SQLite database and never returned to the browser in full. With no keys configured, the app runs on the deterministic
                offline mock engine and labels every result as such.
              </p>
              <div className="space-y-5">
                <SecretField id="claude-key" label="Anthropic (Claude) API key" value={formData.claude_api_key} onChange={(v) => set('claude_api_key', v)} placeholder="sk-ant-api03-…" help="Used when a Claude model is selected." />
                <SecretField id="gemini-key" label="Google (Gemini) API key" value={formData.gemini_api_key} onChange={(v) => set('gemini_api_key', v)} placeholder="AIza…" help="Used when a Gemini model is selected." />
                <div className="pt-4 border-t border-border space-y-4">
                  <SecretField
                    id="hubspot-key"
                    label="HubSpot private app token"
                    optional
                    value={formData.hubspot_api_key}
                    onChange={(v) => set('hubspot_api_key', v)}
                    placeholder="pat-na1-…"
                    help="Links RFPs to HubSpot deals and syncs lifecycle stages (draft → decision maker bought-in, won → closed won)."
                  />
                  <div>
                    <label htmlFor="hubspot-portal" className="block text-sm font-semibold text-ink mb-1">
                      HubSpot portal / account ID
                    </label>
                    <input id="hubspot-portal" type="text" value={formData.hubspot_portal_id} onChange={(e) => set('hubspot_portal_id', e.target.value)} placeholder="e.g. 14592031" className="input-field font-mono" />
                  </div>
                </div>
              </div>
            </section>

            <section className="card" aria-labelledby="prompts-heading">
              <div className="flex items-center justify-between border-b border-border pb-3 mb-5">
                <div className="flex items-center gap-2">
                  <MessageSquare className="w-5 h-5 text-accent" aria-hidden="true" />
                  <h2 id="prompts-heading" className="text-lg font-bold text-ink">
                    System & tone prompts
                  </h2>
                </div>
                <button type="button" onClick={handleResetPrompts} className="btn-ghost text-xs">
                  <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Reset to defaults</span>
                </button>
              </div>
              <div className="space-y-6">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label htmlFor="system-prompt" className="text-sm font-semibold text-ink">
                      Master system prompt
                    </label>
                    <span className="help-text">{formData.system_prompt.length} chars</span>
                  </div>
                  <p className="help-text mb-2">Core behaviour, non-hallucination rules and [MORE INFO REQUIRED] marker requirements.</p>
                  <textarea id="system-prompt" rows={10} value={formData.system_prompt} onChange={(e) => set('system_prompt', e.target.value)} className="input-field font-mono text-xs leading-relaxed" />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label htmlFor="tone-prompt" className="text-sm font-semibold text-ink">
                      Tone of voice prompt
                    </label>
                    <span className="help-text">{formData.tone_of_voice_prompt.length} chars</span>
                  </div>
                  <p className="help-text mb-2">The agency voice: confident, direct, human and evidence-backed.</p>
                  <textarea id="tone-prompt" rows={6} value={formData.tone_of_voice_prompt} onChange={(e) => set('tone_of_voice_prompt', e.target.value)} className="input-field font-mono text-xs leading-relaxed" />
                </div>
              </div>
            </section>

            <section className="card" aria-labelledby="export-heading">
              <div className="flex items-center gap-2 border-b border-border pb-3 mb-5">
                <FileCheck className="w-5 h-5 text-accent" aria-hidden="true" />
                <h2 id="export-heading" className="text-lg font-bold text-ink">
                  Google Docs export
                </h2>
              </div>
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-4 p-4 sub-card">
                  <div>
                    <p id="mock-export-label" className="text-sm font-semibold text-ink">
                      Mock / dry-run export mode
                    </p>
                    <p id="mock-export-desc" className="help-text mt-1">
                      When on, exports simulate the Google Docs API: the full payload is logged and a placeholder document URL is returned. No credentials needed.
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={formData.mock_google_export}
                    aria-labelledby="mock-export-label"
                    aria-describedby="mock-export-desc"
                    onClick={() => set('mock_google_export', !formData.mock_google_export)}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full border-2 border-transparent transition-colors ${
                      formData.mock_google_export ? 'bg-accent' : 'bg-border-strong'
                    }`}
                  >
                    <span className={`inline-block h-5 w-5 rounded-full bg-surface shadow transition-transform ${formData.mock_google_export ? 'translate-x-5' : 'translate-x-0'}`} aria-hidden="true" />
                  </button>
                </div>

                <div>
                  <label htmlFor="google-creds" className="block text-sm font-semibold text-ink mb-1">
                    Google OAuth credentials file path
                  </label>
                  <input id="google-creds" type="text" value={formData.google_credentials_path} onChange={(e) => set('google_credentials_path', e.target.value)} placeholder="credentials.json" className="input-field font-mono" aria-describedby="google-creds-help" />
                  <p id="google-creds-help" className="help-text mt-1">
                    Relative to the backend directory, or an absolute path to the OAuth client JSON.
                  </p>
                </div>

                <div className="mt-5 p-4 sub-card">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold text-ink">Enable live export</h3>
                    <a href="https://console.cloud.google.com/" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-semibold text-accent underline underline-offset-2">
                      <span>Google Cloud Console</span>
                      <ArrowUpRight className="w-3.5 h-3.5" aria-hidden="true" />
                    </a>
                  </div>
                  <ol className="list-decimal list-inside space-y-2 text-xs text-ink leading-relaxed">
                    <li>
                      <strong>Create a project</strong> in Google Cloud Console.
                    </li>
                    <li>
                      <strong>Enable APIs</strong>: <em>APIs & Services → Library</em> → enable <strong>Google Docs API</strong> and <strong>Google Drive API</strong>.
                    </li>
                    <li>
                      <strong>OAuth consent screen</strong> with scopes <code className="font-mono bg-surface px-1 rounded border border-border">…/auth/documents</code> and{' '}
                      <code className="font-mono bg-surface px-1 rounded border border-border">…/auth/drive.file</code>.
                    </li>
                    <li>
                      <strong>Create credentials</strong>: OAuth client ID → <strong>Desktop app</strong> → download JSON → save as{' '}
                      <code className="font-mono bg-surface px-1 rounded border border-border">credentials.json</code>.
                    </li>
                    <li>
                      <strong>Switch off mock mode</strong> above and save. The first export opens a browser consent flow.
                    </li>
                  </ol>
                </div>
              </div>
            </section>

            <div className="flex items-center justify-end pt-2">
              <button type="submit" disabled={saving} className="btn-primary px-6">
                <Save className="w-4 h-4" aria-hidden="true" />
                <span>{saving ? 'Saving…' : 'Save settings'}</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
