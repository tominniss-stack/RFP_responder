# Testing

Three Python suites plus two frontend gates. Everything runs offline — the LLM layer is forced to the deterministic mock (`MOCK_LLM=1` / `TEST_MODE=1`) so results are reproducible and no API keys are needed.

| Suite | Command | Count | Scope |
|---|---|---|---|
| Backend unit | `npm run test:backend` | 108 | per-module tests under `backend/tests/` using FastAPI `TestClient` and a temp SQLite file per test |
| Root integration + adversarial | `npm run test:e2e` | 210 | `tests/test_*.py` — pipeline, pricing, RAG, generation, export, stress and adversarial hardening |
| Tiered E2E | `npm run test:tiers` | 79 | `tests/runner.py` over `tier1_features` → `tier4_realworld` |
| Theme lint | `npm run lint:theme` | 4 gates | grep rules over `frontend/src` |
| Accessibility | `npm run audit:a11y` | 24 scans | Playwright + axe-core, all routes and modals × light/dark |

`./start.sh --ci` runs setup, health-check and the tiered runner non-interactively and exits non-zero on failure. The GitHub Actions workflow runs the first four rows on every push.

## Backend unit tests (`backend/tests/`)

| File | Covers |
|---|---|
| `test_foundations.py` | PRAGMAs, DDL, cascade/set-null behaviour, settings singleton, services CRUD, **secret masking** (`GET` masks, `PUT` with masked echo does not overwrite) |
| `test_ingestion_classification.py` | PDF/DOCX extraction, heading/markdown/numbered/paragraph fallbacks, mock classifier, mocked Claude/Gemini HTTP dispatch, RFP endpoints, `X-LLM-Engine` header |
| `test_response_generation.py` | notes CRUD and precedence, exact pricing in drafts, gap marker → open question, resolve + regenerate, section status validation |
| `test_kb_pricing.py` | KB CRUD and search biasing, price item validation (negative amounts, bad units, blank descriptions, unknown service) |
| `test_export.py` | payload builder (headings, inline runs, index accumulation), comment anchoring and fallback, mock vs live mode, missing credentials → 400, missing libraries → 500, mocked live execution |
| `test_seed_data.py` | seed counts and shapes, won/lost biasing on seed corpus, sample RFP generation and parsing, idempotent `ensure_seeded()` |
| `test_adversarial_generation.py` | injection-style notes, huge payloads, unicode, cross-RFP isolation |

## Root suites (`tests/`)

Named by the behaviour they exercise:

- `test_ingestion_pipeline.py`, `test_ingestion_stress.py` — parser edge cases, large documents, malformed archives.
- `test_knowledge_base_rag.py` — chunking, retrieval ordering, outcome weighting, empty-store fallback.
- `test_pricing_engine.py` — floating-point fidelity, zero-approximation patterns, **unlinked RFP never receives pricing**, 422/400/409 validation and referential integrity.
- `test_draft_generation.py`, `test_provenance_and_notes.py`, `test_open_questions_lifecycle.py` — precedence matrix across all classifications, provenance schema, tripartite synthesis, dedup on regeneration, resolution lifecycle, cascade deletion.
- `test_api_stress.py` — concurrency and repeated-call stability.
- `test_adversarial_hardening.py` — six dimensions: parser, pricing injection, retrieval biasing, gap markers, export pipeline, and a **static design-token audit** (only the accent pairing may be hard-coded hex in markup; focus ring and reduced-motion rules must exist; Inter font configured).
- `test_end_to_end_walkthrough.py` — the user-facing acceptance walkthrough (upload → classify → generate → notes → resolve → export) plus acceptance criteria: every route exists, **design tokens are complete and every ink/surface and accent/accent-ink pairing is ≥ 4.5:1 in both themes** (computed from `index.css`), components use semantic tokens only, independent model selection, mock-export banner, won-proposal biasing.

Tiered tests (`tier1_features` … `tier4_realworld`) share `tests/harness.py` (app factory + temp DB) and `tests/fixtures.py` (document generators) and are reported by `tests/runner.py` with per-tier timing.

## Policies the tests enforce

- **No silent fallback.** A configured live provider that fails yields HTTP 502, never a mock draft.
- **No guessed pricing.** Pricing comes only from price items linked through the RFP's services; otherwise a gap marker and open question.
- **Explicit engine reporting.** Every generate response and classify response states which engine/model produced it.
- **Secrets never round-trip.** API keys are masked on read and a masked value is ignored on write.
- **Theme by class swap only.** No `dark:` colour variants, no raw palette colours, contrast proven from token values.

## Accessibility audit

`frontend/scripts/a11y-audit.mjs` drives Chromium through Playwright with `@axe-core/playwright` (axe-core 4.14, WCAG 2.0/2.1/2.2 A+AA tag set). It creates a fixture RFP via the API, classifies it, then for **each theme** visits `#/`, `#/new-rfp`, `#/kb`, `#/settings`, `#/services`, `#/pricing`, `#/rfp/:id` and opens the KB add-document modal, services delete confirm, pricing add-item modal, RFP edit-details modal and add-section modal. Full-page screenshots go to `plans/screenshots/`, the JSON report to `plans/a11y-report.json` (both git-ignored). Exit code is non-zero if any serious/critical violation is found.

Current result: **0 violations at any impact level across all 24 scans.** The first sweep after the design-system refactor reported 25 serious/critical findings from five root causes, all fixed before release:

| axe rule | Cause | Fix |
|---|---|---|
| `dlitem` / `definition-list` | metric cards wrapped `<dt>/<dd>` in a `<div>` inside `<dl>` | `<ul aria-label>` of `<li>` cards with `<p>` label/value |
| `target-size` | section move buttons rendered 22 × 22 px | `min-w/min-h 28px`, 16 px icon |
| `color-contrast` | light accent on `accent-soft` = 4.15:1; 12 px link on `surface-raised` = 4.21:1 | light `accent` darkened to `#0B6670` (≥ 5.6:1 on every light surface) |
| `region` | export-mode banner content outside any landmark | `<aside aria-label="Export mode notice">` |
| `heading-order` | `<h3>` directly after the page `<h1>` | promoted to `<h2>` |

Run it locally with both servers up:

```bash
./start.sh &                      # or MOCK_LLM=1 python backend/run.py + npm run dev --prefix frontend
BASE_URL=http://127.0.0.1:3010 npm run audit:a11y
```

## Adding tests

- Backend unit: add to `backend/tests/`, use the `override_get_db` pattern from `test_foundations.py` to get an isolated DB.
- Integration: add `tests/test_<behaviour>.py`; pytest discovers it. If it belongs to a tier, place it under the tier directory and `runner.py` picks it up automatically.
- Any new colour must be a token in `index.css` (both `:root` and `.dark`) and mapped in `tailwind.config.js`; `test_08_ac_design_tokens_complete_and_wcag_aa_in_both_themes` will fail if a token is missing from either block or fails contrast.
