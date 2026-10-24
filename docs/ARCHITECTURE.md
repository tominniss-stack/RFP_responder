# Architecture

Technical reference for the RFP Response Assistant. Written against the code as shipped; every path below is a real file.

## 1. System overview

```
┌──────────────────────────────┐        JSON / multipart        ┌──────────────────────────────────┐
│  frontend/  (React 18, Vite) │ ─────────────────────────────▶ │  backend/  (FastAPI, uvicorn)    │
│  hash router · token theming │ ◀───────────────────────────── │  /api/*  routers                 │
└──────────────────────────────┘   X-LLM-Engine / X-LLM-Model   └───────────────┬──────────────────┘
                                                                                │
                              ┌─────────────────────────────────────────────────┼───────────────────┐
                              │ services/                                       │                   │
                              │  ingestion → llm → vector_store → pricing → export → hubspot        │
                              └─────────────────────────────────────────────────┼───────────────────┘
                                                                                │
                                  SQLite (WAL, FK on)  ·  optional ChromaDB  ·  Anthropic / Google APIs
```

Single-process backend, single SQLite file, no message queue. The frontend talks only to `/api/*`; the backend never serves the SPA in dev (Vite does) — Docker uses nginx for that.

## 2. Repository layout

```
backend/
  run.py                      uvicorn entry (PORT default 4010)
  requirements.txt            fastapi, uvicorn, pydantic, pdfplumber, python-multipart + optional extras
  app/
    main.py                   app factory, lifespan (create_tables + seed_defaults), CORS, routers
    database.py               get_db_connection / get_db / get_db_context — PRAGMAs applied per connection
    models.py                 SCHEMA_DDL, DEFAULT_* constants, seed data, create_tables(), seed_defaults()
    schemas.py                Pydantic v2 request/response models
    api/                      rfps.py · kb.py · pricing.py · services.py · settings.py
    services/
      ingestion.py            PDF/DOCX → sections
      llm.py                  provider clients, engine resolution, classification
      vector_store.py         pure-Python TF-IDF store + ChromaDB wrapper
      pricing.py              deterministic pricing injection
      export.py               Google Docs/Drive payload builder + executor
      hubspot.py              optional deal sync
      seed.py                 ensure_seeded(), sample RFP generators
    seeds/__main__.py         `python -m app.seeds`
  tests/                      unit tests (108)
frontend/
  src/
    App.jsx                   hash routing, theme, providers, skip link, ErrorBoundary
    index.css                 design tokens (:root / .dark) + component classes
    components/               Navbar, Logo, Badge (chips), Modal, Toast, ConfirmDialog, ErrorBoundary,
                              MarkdownRenderer, MockExportBanner
    components/rfp/           RFPDetail sub-components (header, section card, panels, modals, views)
    pages/                    RFPTracker, NewRFP, RFPDetail, KnowledgeBase, PricingAdmin, ServicesAdmin, Settings
    services/api.js           fetch wrapper + typed endpoint map
  scripts/
    a11y-audit.mjs            Playwright + axe sweep (all routes × both themes)
    validate-build.cjs        post-build sanity check
  tailwind.config.js          semantic colour map → CSS variables
tests/                        root integration + adversarial suites (210) and tiered runner (79)
scripts/lint-theme.sh         design-token lint gates
start.sh                      one-command launcher / CI verifier
```

## 3. Backend

### 3.1 Entry point and lifespan

[`backend/app/main.py`](../backend/app/main.py) builds the `FastAPI` app with an `asynccontextmanager` lifespan that opens a connection, runs `create_tables()` then `seed_defaults()`, and closes. CORS allows `localhost`/`127.0.0.1` on 3010, 4010, 5173 and 3000 plus anything in `CORS_ORIGINS` (comma-separated). `expose_headers` includes `X-LLM-Engine`, `X-LLM-Model`, `X-LLM-Fallback-From` so the browser can read them.

Routers are mounted under `/api`: `rfps` (also hosts sections, notes, open questions, export), `kb`, `pricing`, `services`, `settings`. `GET /api/health` returns `{status, database, version}`.

### 3.2 Database layer

[`backend/app/database.py`](../backend/app/database.py) — `sqlite3` only. Every connection sets `PRAGMA foreign_keys = ON`, `journal_mode = WAL`, `busy_timeout = 5000`, and `row_factory = sqlite3.Row`. `DATABASE_PATH` env overrides the default `backend/data/rfp_assistant.db`. Tests override the `get_db` dependency with a temp-file DB per test.

### 3.3 Schema

Ten tables, defined as a DDL string in [`backend/app/models.py`](../backend/app/models.py):

| Table | Purpose | Notable constraints |
|---|---|---|
| `rfps` | one row per proposal | `status CHECK IN ('draft','submitted','won','lost','no decision')`, `budget_type`, `final_doc_link` |
| `services` | agency service catalogue | `name UNIQUE` |
| `rfp_services` | RFP ↔ service | cascade on RFP delete |
| `kb_documents` | past proposals, case studies, boilerplate | `type CHECK IN (...)`, `outcome` won/lost |
| `kb_document_services` | KB ↔ service | cascade |
| `price_items` | structured price list | `unit CHECK IN ('day rate','fixed','monthly retainer')`, `amount >= 0`, `service_id ON DELETE SET NULL` |
| `rfp_sections` | parsed sections | `classification CHECK IN (...)`, `status`, `draft_content`, `final_content`, `provenance` (JSON), `sort_order` |
| `rfp_notes` | account-manager notes | `section_id NULL` = whole-RFP note |
| `open_questions` | gaps awaiting evidence | `resolved`, `resolution_text`, `section_id` |
| `settings` | singleton | `CHECK(id = 1)` |

Schema evolution is additive: `create_tables()` runs `ALTER TABLE … ADD COLUMN` inside try/except for columns introduced after the initial DDL. There is no migration framework by design — the dataset is small and single-tenant.

### 3.4 Settings and secrets

[`backend/app/api/settings.py`](../backend/app/api/settings.py). `GET` masks every key in `SECRET_FIELDS` as `••••` + last four characters. `PUT` ignores any field whose value still carries the mask marker, so a UI that echoes the form back cannot overwrite a stored secret with its masked form. Keys are stored in plaintext in SQLite — acceptable for a single-operator tool on a private network, and the roadmap item for anything multi-user.

### 3.5 LLM layer

[`backend/app/services/llm.py`](../backend/app/services/llm.py). Two provider clients built on `urllib` (no SDKs): `call_claude_api` (Anthropic Messages) and `call_gemini_api` (generateContent). Both wrap HTTP/URL errors in `LLMProviderError`, which the routers map to **HTTP 502**. There is deliberately no silent fallback from a configured live provider to the mock.

`resolve_engine(model, settings)` decides what runs:

1. `MOCK_LLM=1` or `TEST_MODE=1` in the environment → `mock`.
2. Model name starts with `claude` and a Claude key is set → `claude`; starts with `gemini` and a Gemini key is set → `gemini`.
3. Otherwise → `mock`.

`call_model_with_meta()` returns `(text, {"engine", "model"})`; `classify_rfp_sections_with_meta()` does the same for classification and, if a live provider returns unparseable JSON, falls back to the deterministic keyword classifier and reports `fallback_from`. The `generate` endpoint includes `engine`/`model` in its JSON; `classify` sets the `X-LLM-*` headers. The frontend's `EngineBadge` renders them.

The mock dispatcher is deterministic and schema-faithful: it classifies by keyword tables and produces drafts that honour the same precedence rules and gap-marker format as the live prompt, which is what makes the test suites meaningful without network access.

### 3.6 Ingestion

[`backend/app/services/ingestion.py`](../backend/app/services/ingestion.py). PDF via `pdfplumber`. DOCX via `python-docx` when installed, otherwise `zipfile` + `xml.etree` reading `word/document.xml` directly; in both paths paragraphs whose style name contains "heading" become section headings and tables are flattened to text. If no heading styles are found the splitter falls back to markdown `#` headers, then numbered `1.` / `1.1` headings, then double-newline paragraphs.

### 3.7 Vector store and retrieval

[`backend/app/services/vector_store.py`](../backend/app/services/vector_store.py). `ChromaVectorStoreWrapper` uses ChromaDB if importable, otherwise `PurePythonVectorStore` (term-overlap scoring). Retrieval applies **outcome biasing**: `score = raw_similarity × weight`, with `weight_won` (default 1.25) and `weight_lost` (default 0.90) read from settings and overridable per request. Documents are chunked (500 chars, 100 overlap) at index time. `sync_vector_store_from_db()` rebuilds the index from `kb_documents`; the generate path only triggers a sync when the store is empty, so repeated draft generation does not rebuild the index.

### 3.8 Pricing

[`backend/app/services/pricing.py`](../backend/app/services/pricing.py). `get_pricing_for_rfp()` returns price items **only** for services explicitly linked to the RFP. No linked services → empty list → the draft gets a `[MORE INFO REQUIRED: pricing …]` marker and an open question. Amounts are formatted from the stored decimal without rounding or approximation. This strictness is tested adversarially (keyword-looking RFP text must never pull in pricing).

### 3.9 Draft generation pipeline

`POST /api/rfps/{id}/sections/{section_id}/generate` in [`backend/app/api/rfps.py`](../backend/app/api/rfps.py):

1. Load section, RFP, settings.
2. Collect **account-manager notes** — a section-specific note takes precedence; otherwise all whole-RFP notes.
3. If classification is `pricing`: inject exact price items (§3.8).
4. If `boilerplate`: retrieve the boilerplate KB document; if `strategic`: outcome-biased RAG over past proposals.
5. Build the prompt from the system prompt + tone-of-voice prompt + gathered context; call `call_model_with_meta()`.
6. Scan the draft for `[MORE INFO REQUIRED` markers; create an open question per unique marker (idempotent across regenerations).
7. Persist `draft_content`, `provenance` (list of `{source, label}` — `am_note`, `pricing`, `rag`, `boilerplate`, `resolved_question`), set status `drafted`.
8. Return the draft plus `engine`/`model`.

`POST /api/rfps/{id}/generate-all` iterates every section without a draft (or all with `{"force": true}`) and returns a per-section result list; one section's provider error does not abort the batch.

### 3.10 Export

[`backend/app/services/export.py`](../backend/app/services/export.py). `build_export_payload()` converts each section's final (or draft) content from markdown into a Google Docs `batchUpdate` request list — `HEADING_1` for section headings, inline bold/italic runs, bullet lists — and builds one Drive comment per unresolved open question, anchored to the marker text where present (falling back to the section heading, then the document title). In mock mode the payload is logged to `backend/logs/` and a `mock-rfp-{id}` URL is returned; live mode requires `google-api-python-client` and a service-account JSON at the configured path, and fails with 400/500 otherwise.

## 4. Frontend

### 4.1 Routing and shell

[`frontend/src/App.jsx`](../frontend/src/App.jsx) parses `location.hash` into a route (`#/`, `#/new-rfp`, `#/rfp/:id`, `#/kb`, `#/pricing`, `#/services`, `#/settings[?tab=]`). The shell renders a skip link, `Navbar`, optional `MockExportBanner`, `<main id="main-content">` wrapped in `ErrorBoundary`, and a footer. `ToastProvider` and `ConfirmProvider` sit at the root so any page can call `useToast()` / `useConfirm()`.

Theme: `applyTheme(isDark)` toggles only the `dark` class on `<html>` and persists to `localStorage`; the initial value respects `prefers-color-scheme`. An inline script in [`index.html`](../frontend/index.html) applies the class before first paint to avoid a flash.

### 4.2 Design tokens

[`frontend/src/index.css`](../frontend/src/index.css) defines every colour as an RGB triplet custom property on `:root` (light) and `.dark`:

```
canvas · surface · surface-raised · overlay
ink · ink-muted · ink-inverse
border · border-strong
accent · accent-hover · accent-ink · accent-soft
success/-soft · warning/-soft · danger/-soft · info/-soft
```

[`tailwind.config.js`](../frontend/tailwind.config.js) maps each to `rgb(var(--color-X) / <alpha-value>)`, so `bg-accent/20` works and the whole theme swaps by class. Component classes (`.btn-primary`, `.card`, `.chip-warning`, `.input-field`, …) are composed from those tokens with `@apply`. Rules enforced by [`scripts/lint-theme.sh`](../scripts/lint-theme.sh): no `dark:` colour prefixes, no raw Tailwind palette colours, no sub-12 px type, no legacy brand tokens. A unit test computes WCAG contrast from the token values for every ink/surface pairing in both themes.

### 4.3 Components of note

- `Modal` — `role="dialog"`, `aria-modal`, labelled by its title, focus trapped, Escape closes, focus returns to the opener, body scroll locked.
- `ConfirmDialog` — promise-based `confirm({title, body, confirmLabel, danger})` replacing `window.confirm`.
- `Toast` — `aria-live="polite"` region; success/error/info variants.
- `Badge` — single `Chip` primitive with a variant map; domain badges (status, outcome, classification, provenance, engine, deadline) are thin wrappers.
- `components/rfp/*` — `RFPDetail` is an orchestrator holding state and handlers; rendering is delegated to `RFPHeader`, `OutcomePanel`, `OpenQuestionsRibbon`, `BrainDumpPanel`, `SectionCard`, `FullDocumentView`, `OriginalBriefView`, and the modals in `RFPModals`.

### 4.4 API client

[`frontend/src/services/api.js`](../frontend/src/services/api.js) — one `request()` wrapper that sets JSON headers (unless the body is `FormData`), surfaces the response headers to callers that need `X-LLM-*`, and throws on non-2xx with the server's `detail`. Requests go to the relative path `/api`; in dev [`vite.config.js`](../frontend/vite.config.js) proxies that to `http://127.0.0.1:${VITE_BACKEND_PORT:-4010}`, and in Docker nginx does the same, so the bundle contains no hard-coded backend host.

## 5. API contract

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | |
| GET / PUT | `/api/settings` | secrets masked on read; masked echo ignored on write |
| GET / POST | `/api/services` | |
| DELETE | `/api/services/{id}` | 409 if linked to an active RFP |
| POST | `/api/rfps/upload` | multipart: `file`, `client_name`, `services[]`, `value`, `deadline`, … |
| POST | `/api/rfps` | manual creation with optional `brief` |
| GET | `/api/rfps` | filters: `service_id`, `status`, `outcome` (`pending` = not won/lost/no decision), `min_value`, `max_value` |
| GET / PUT / DELETE | `/api/rfps/{id}` | |
| POST | `/api/rfps/{id}/classify` | sets `X-LLM-Engine`, `X-LLM-Model`, optional `X-LLM-Fallback-From` |
| PUT | `/api/rfps/{id}/sections/reorder` | body `{section_ids: [...]}` |
| POST | `/api/rfps/{id}/sections` | |
| PUT / DELETE | `/api/rfps/{id}/sections/{sid}` | manual classification / draft / final edits |
| POST | `/api/rfps/{id}/sections/{sid}/generate` | returns `draft`, `provenance`, `engine`, `model` |
| POST | `/api/rfps/{id}/generate-all` | body `{force?: bool}` |
| GET / POST | `/api/rfps/{id}/notes` | `section_id` null = whole-RFP note |
| DELETE | `/api/rfps/{id}/notes/{nid}` | |
| GET | `/api/rfps/{id}/open-questions` | |
| PUT | `/api/rfps/{id}/open-questions/{qid}` | `{resolution_text}` clears the marker |
| POST | `/api/rfps/{id}/export` | `{export_mode?: 'mock' \| 'live'}` |
| GET / POST | `/api/kb` | `?q=` performs a biased search; `?outcome=` filter |
| POST | `/api/kb/seed` | reload fictional seed documents |
| GET / PUT / DELETE | `/api/kb/{id}` | |
| GET / POST | `/api/pricing` | `?service_id=` |
| POST | `/api/pricing/seed` | |
| PUT / DELETE | `/api/pricing/{id}` | |

Interactive docs at `/docs` (Swagger) and `/redoc` when the backend is running.

## 6. Configuration

| Variable | Default | Effect |
|---|---|---|
| `PORT` / `HOST` / `RELOAD` | `4010` / `0.0.0.0` / off | uvicorn |
| `DATABASE_PATH` | `backend/data/rfp_assistant.db` | SQLite file |
| `MOCK_LLM` / `TEST_MODE` | unset | `1` forces the mock engine |
| `CORS_ORIGINS` | empty | extra allowed origins, comma-separated |
| `VITE_PORT` / `VITE_BACKEND_PORT` | `3010` / `4010` | Vite dev server port and `/api` proxy target |

Runtime settings (models, keys, prompts, export mode, retrieval weights, HubSpot) live in the `settings` table and are edited through the UI.

## 7. Known limitations

- **Single operator, no auth.** Anyone who can reach the port can read settings (masked) and all proposals.
- **Plaintext secrets at rest** in SQLite (see §3.4).
- **No streaming.** Draft generation is request/response; long sections block until the provider returns.
- **Export is one-shot.** Re-exporting creates a new document; there is no diff/update of an existing one.
- **ChromaDB is optional and unpinned.** The pure-Python store is the tested default; ChromaDB is a drop-in for larger corpora.
