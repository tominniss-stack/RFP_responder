"""Database schema DDL, indexes, and default seed data.

Contains:
- All 10 schema tables (rfps, services, rfp_services, kb_documents,
  kb_document_services, price_items, rfp_sections, rfp_notes, open_questions, settings)
- Foreign key constraints with cascading deletes
- Settings singleton constraint CHECK(id = 1)
- Default Master System Prompt & Tone of Voice Prompt
- Pre-populated default services
"""

import sqlite3

# ---------------------------------------------------------------------------
# Default Prompts & Seed Data
# ---------------------------------------------------------------------------

# Brand name used in prompts and seed content. Fictional agency for demo purposes.
AGENCY_NAME = "Another Marketing Agency"

# Single source of truth for default model identifiers (also used by services/llm.py).
DEFAULT_CLASSIFICATION_MODEL = "gemini-2.5-flash"
DEFAULT_GENERATION_MODEL = "claude-sonnet-4-5"

DEFAULT_SYSTEM_PROMPT = f"""You are an internal drafting assistant for {AGENCY_NAME}, helping staff prepare first-draft responses to Requests for Proposal (RFPs).

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
6. Output only the drafted section content, plus any [MORE INFO REQUIRED] markers. Do not include commentary about your own process."""

DEFAULT_TONE_PROMPT = f"""Write in {AGENCY_NAME}'s house tone:
- Confident but not arrogant; direct and clear over clever or jargon-heavy
- Human and conversational, avoiding generic "corporate AI" phrasing (e.g. avoid "we are excited to leverage synergies")
- Short, punchy sentences over long compound ones where possible
- Show, don't just claim — back statements with specific evidence from case studies/testimonials rather than vague assertions of quality
- [PLACEHOLDER: paste 2-3 examples of strong past proposal writing here once available, as few-shot reference for tone]"""

DEFAULT_SERVICES = [
    "Web Development — Headless CMS",
    "Digital Marketing — PPC",
    "UX/UI Design",
    "SEO — Technical",
    "Content Strategy & Copywriting",
]

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

SCHEMA_DDL = """
-- 1. Core RFP record
CREATE TABLE IF NOT EXISTS rfps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    value NUMERIC,
    date_submitted DATE,
    deadline DATE,
    budget_type TEXT DEFAULT 'fixed',
    budget_notes TEXT,
    raw_details TEXT,
    status TEXT CHECK(status IN ('draft', 'submitted', 'won', 'lost', 'no decision')) DEFAULT 'draft',
    outcome_feedback TEXT,
    source_document TEXT,
    final_doc_link TEXT,
    hubspot_deal_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Editable services list (extensible tag set)
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

-- 3. Junction table for RFP <-> Services (many-to-many)
CREATE TABLE IF NOT EXISTS rfp_services (
    rfp_id INTEGER NOT NULL REFERENCES rfps(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    PRIMARY KEY (rfp_id, service_id)
);

-- 4. Knowledge base documents for RAG
CREATE TABLE IF NOT EXISTS kb_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('past_proposal', 'case_study', 'testimonial', 'pitch_deck', 'boilerplate')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    outcome TEXT CHECK(outcome IN ('won', 'lost', 'n/a') OR outcome IS NULL),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Junction table for KB Document <-> Services (many-to-many tag set)
CREATE TABLE IF NOT EXISTS kb_document_services (
    kb_document_id INTEGER NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    PRIMARY KEY (kb_document_id, service_id)
);

-- 6. Structured pricing data
CREATE TABLE IF NOT EXISTS price_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER REFERENCES services(id) ON DELETE SET NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL CHECK(unit IN ('day rate', 'fixed', 'monthly retainer')),
    amount NUMERIC NOT NULL
);

-- 7. Sections of an individual RFP response
CREATE TABLE IF NOT EXISTS rfp_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rfp_id INTEGER NOT NULL REFERENCES rfps(id) ON DELETE CASCADE,
    heading TEXT NOT NULL,
    original_text TEXT NOT NULL,
    classification TEXT CHECK(classification IN ('boilerplate', 'pricing', 'strategic_decision', 'strategic', 'gap', 'compliance_admin')),
    confidence TEXT CHECK(confidence IN ('high', 'medium', 'low') OR confidence IS NULL),
    clarifying_question TEXT,
    suggested_default TEXT,
    draft_content TEXT,
    final_content TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'drafted', 'resolved')) DEFAULT 'pending',
    sort_order INTEGER NOT NULL DEFAULT 0
);

-- 8. Account manager notes (hybrid model: whole-RFP or section-level)
CREATE TABLE IF NOT EXISTS rfp_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rfp_id INTEGER NOT NULL REFERENCES rfps(id) ON DELETE CASCADE,
    section_id INTEGER REFERENCES rfp_sections(id) ON DELETE CASCADE,
    raw_content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. Open questions / gap tracking
CREATE TABLE IF NOT EXISTS open_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rfp_id INTEGER NOT NULL REFERENCES rfps(id) ON DELETE CASCADE,
    section_id INTEGER REFERENCES rfp_sections(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('open', 'resolved')) DEFAULT 'open',
    resolution TEXT
);

-- 10. App-wide settings (enforced single-row configuration)
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    classification_model TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
    generation_model TEXT NOT NULL DEFAULT 'claude-sonnet-4-5',
    claude_api_key TEXT DEFAULT '',
    gemini_api_key TEXT DEFAULT '',
    mock_google_export INTEGER NOT NULL DEFAULT 1,
    google_credentials_path TEXT DEFAULT 'credentials.json',
    system_prompt TEXT NOT NULL,
    tone_of_voice_prompt TEXT NOT NULL,
    hubspot_api_key TEXT DEFAULT '',
    hubspot_portal_id TEXT DEFAULT ''
);

-- Performance & Foreign Key Indexes
CREATE INDEX IF NOT EXISTS idx_rfp_sections_rfp_id ON rfp_sections(rfp_id);
CREATE INDEX IF NOT EXISTS idx_rfp_notes_rfp_id ON rfp_notes(rfp_id);
CREATE INDEX IF NOT EXISTS idx_rfp_notes_section_id ON rfp_notes(section_id);
CREATE INDEX IF NOT EXISTS idx_open_questions_rfp_id ON open_questions(rfp_id);
CREATE INDEX IF NOT EXISTS idx_open_questions_section_id ON open_questions(section_id);
CREATE INDEX IF NOT EXISTS idx_price_items_service_id ON price_items(service_id);
CREATE INDEX IF NOT EXISTS idx_kb_documents_type ON kb_documents(type);
CREATE INDEX IF NOT EXISTS idx_kb_documents_outcome ON kb_documents(outcome);
"""


def create_tables(conn: sqlite3.Connection) -> None:
    """Execute SQLite schema table and index creation with safe column migrations."""
    conn.executescript(SCHEMA_DDL)

    # Idempotent column migrations for existing SQLite databases
    migrations = [
        ("deadline", "ALTER TABLE rfps ADD COLUMN deadline DATE;"),
        ("budget_type", "ALTER TABLE rfps ADD COLUMN budget_type TEXT DEFAULT 'fixed';"),
        ("budget_notes", "ALTER TABLE rfps ADD COLUMN budget_notes TEXT;"),
        ("raw_details", "ALTER TABLE rfps ADD COLUMN raw_details TEXT;"),
    ]
    cur = conn.execute("PRAGMA table_info(rfps);")
    existing_cols = {row["name"] if hasattr(row, "keys") else row[1] for row in cur.fetchall()}
    for col_name, alter_stmt in migrations:
        if col_name not in existing_cols:
            try:
                conn.execute(alter_stmt)
            except sqlite3.OperationalError:
                pass

    settings_migrations = [
        ("weight_won", "ALTER TABLE settings ADD COLUMN weight_won REAL DEFAULT 1.25;"),
        ("weight_lost", "ALTER TABLE settings ADD COLUMN weight_lost REAL DEFAULT 0.90;"),
        ("hubspot_api_key", "ALTER TABLE settings ADD COLUMN hubspot_api_key TEXT DEFAULT '';"),
        ("hubspot_portal_id", "ALTER TABLE settings ADD COLUMN hubspot_portal_id TEXT DEFAULT '';"),
    ]
    cur_s = conn.execute("PRAGMA table_info(settings);")
    existing_s_cols = {row["name"] if hasattr(row, "keys") else row[1] for row in cur_s.fetchall()}
    for col_name, alter_stmt in settings_migrations:
        if col_name not in existing_s_cols:
            try:
                conn.execute(alter_stmt)
            except sqlite3.OperationalError:
                pass



SEED_PRICE_ITEMS = [
    (1, 1, "Senior Full-Stack Engineer", "day rate", 850.0),
    (2, 3, "Principal UX/UI Designer", "day rate", 900.0),
    (3, 4, "Comprehensive Technical SEO & Accessibility Audit", "fixed", 3500.0),
    (4, 2, "Monthly Multi-Channel PPC Management", "monthly retainer", 2200.0),
    (5, 1, "Core Headless CMS Web Application Package", "fixed", 16500.0),
    (6, 1, "Enterprise SLA Support & Maintenance Retainer", "monthly retainer", 5000.0),
    (7, 5, "Digital Discovery Sprint & Content Architecture", "fixed", 6000.0),
    (8, 1, "Senior QA & Assistive Technology Test Specialist", "day rate", 750.0),
]

# All organisations, people and identifiers below are fictional.
SEED_KB_DOCUMENTS = [
    {
        "id": 1,
        "type": "past_proposal",
        "title": "Enterprise Web Platform & Multi-Channel Digital Marketing for Retail Group",
        "content": (
            "Delivered an enterprise-grade headless CMS web platform and integrated PPC digital marketing "
            "campaign for a national UK retail brand. Architecture used a headless CMS with a statically "
            "rendered front end, microservices integration, technical SEO foundations, and sub-second page loads. "
            "Achieved 40% organic traffic growth and £85k contract value. Outcome: Won proposal."
        ),
        "outcome": "won",
        "service_ids": [1, 2, 3],
    },
    {
        "id": 2,
        "type": "past_proposal",
        "title": "Web Development & Digital Marketing Portal for Regional Travel Association",
        "content": (
            "Proposed a generic monolithic CMS web portal and digital marketing campaign for regional tourism bookings "
            "with standard booking engine integration, basic PPC management, and a shared relational database. "
            "Total contract value £45k. Outcome: Lost proposal."
        ),
        "outcome": "lost",
        "service_ids": [1, 2],
    },
    {
        "id": 3,
        "type": "case_study",
        "title": "Northwind Renewables Digital Replatforming & Performance Optimisation",
        "content": (
            f"{AGENCY_NAME} re-architected Northwind Renewables' digital platform from legacy infrastructure to a "
            "high-speed headless CMS. Verified post-launch results: +45% organic conversion rate, 3.2s faster core "
            "page loads (average LCP from 4.1s to 0.9s), +140% mobile engagement, and 99.99% uptime during peak "
            "winter traffic. Infrastructure deployed on carbon-neutral UK cloud hosting."
        ),
        "outcome": "n/a",
        "service_ids": [1, 3, 4],
    },
    {
        "id": 4,
        "type": "boilerplate",
        "title": f"{AGENCY_NAME} Corporate Overview & Credentials",
        "content": (
            f"{AGENCY_NAME} is a UK digital agency specialising in high-performance web development, digital "
            "marketing, and user experience design. Founded in 2016, our multidisciplinary team of 28 specialists "
            "has delivered over 120 digital solutions across public and private sectors. We maintain ISO 27001 "
            "certified information security management, Cyber Essentials Plus accreditation, and £5,000,000 "
            "professional indemnity insurance (with £10,000,000 public liability insurance). Company registration "
            "number: 00000000; VAT number: GB 000 0000 00. Registered office: 1 Example Street, Exampletown, EX1 1AA, UK."
        ),
        "outcome": "n/a",
        "service_ids": [1, 2, 3, 4, 5],
    },
    {
        "id": 5,
        "type": "testimonial",
        "title": "Northwind Renewables CTO Commendation",
        "content": (
            f"{AGENCY_NAME} delivered our digital transformation ahead of schedule and with flawless code quality. "
            "Their command of headless architecture solved our performance bottlenecks in record time, while their "
            "transparent pricing and proactive project management made them an invaluable partner throughout our "
            "replatforming. — Alex Example, Chief Technology Officer, Northwind Renewables (fictional)"
        ),
        "outcome": "n/a",
        "service_ids": [1, 3],
    },
]


def seed_defaults(conn: sqlite3.Connection) -> None:
    """Idempotently insert default singleton settings, services, price items, and KB documents."""
    # Seed settings singleton if not already existing
    conn.execute(
        """
        INSERT OR IGNORE INTO settings (
            id, classification_model, generation_model, claude_api_key, gemini_api_key,
            mock_google_export, google_credentials_path, system_prompt, tone_of_voice_prompt
        ) VALUES (1, ?, ?, '', '', 1, 'credentials.json', ?, ?);
        """,
        (DEFAULT_CLASSIFICATION_MODEL, DEFAULT_GENERATION_MODEL, DEFAULT_SYSTEM_PROMPT, DEFAULT_TONE_PROMPT)
    )

    # Seed default services
    for service_name in DEFAULT_SERVICES:
        conn.execute(
            "INSERT OR IGNORE INTO services (name) VALUES (?);",
            (service_name,)
        )

    # Seed default price items
    for item in SEED_PRICE_ITEMS:
        conn.execute(
            """
            INSERT OR IGNORE INTO price_items (id, service_id, description, unit, amount)
            VALUES (?, ?, ?, ?, ?);
            """,
            item,
        )

    # Seed default KB documents and service links
    for doc in SEED_KB_DOCUMENTS:
        conn.execute(
            """
            INSERT OR IGNORE INTO kb_documents (id, type, title, content, outcome)
            VALUES (?, ?, ?, ?, ?);
            """,
            (doc["id"], doc["type"], doc["title"], doc["content"], doc["outcome"]),
        )
        for sid in doc.get("service_ids", []):
            conn.execute(
                """
                INSERT OR IGNORE INTO kb_document_services (kb_document_id, service_id)
                VALUES (?, ?);
                """,
                (doc["id"], sid),
            )

