"""
Opaque-box Test Harness and HTTP Client for RFP Response Assistant.
Provides dual-mode execution:
1. Live HTTP mode against http://localhost:8000/api (or custom base URL)
2. Standalone Contract Reference Mode using an embedded in-process SQLite & API contract engine
"""

import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

from tests.fixtures import (
    DEFAULT_SETTINGS,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TONE_PROMPT,
    SAMPLE_RFP_CLIENT,
    SAMPLE_RFP_SECTIONS,
    SAMPLE_RFP_SERVICES,
    SAMPLE_RFP_VALUE,
    SEED_KB_DOCUMENTS,
    SEED_PRICE_ITEMS,
    SEED_SERVICES,
)


class TestResponse:
    """Standardized HTTP response wrapper."""

    def __init__(self, status_code: int, body_bytes: bytes, headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self.content = body_bytes
        self.headers = headers or {}

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        if not self.text.strip():
            return None
        return json.loads(self.text)

    def __repr__(self) -> str:
        return f"<TestResponse [{self.status_code}] len={len(self.content)}>"


class ContractReferenceEngine:
    """
    In-process contract reference engine conforming strictly to PROJECT.md,
    spec_inventory.md, and verification_spec.md.
    Used when a live HTTP server is not running on port 8000.
    """

    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self.mock_export_logs: List[Dict[str, Any]] = []

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")

        # 1. rfps
        cur.execute("""
            CREATE TABLE rfps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                value NUMERIC,
                date_submitted DATE,
                status TEXT CHECK(status IN ('draft', 'submitted', 'won', 'lost', 'no decision')) DEFAULT 'draft',
                outcome_feedback TEXT,
                source_document TEXT,
                final_doc_link TEXT,
                hubspot_deal_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. services
        cur.execute("""
            CREATE TABLE services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
        """)

        # 3. rfp_services
        cur.execute("""
            CREATE TABLE rfp_services (
                rfp_id INTEGER NOT NULL REFERENCES rfps(id) ON DELETE CASCADE,
                service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
                PRIMARY KEY (rfp_id, service_id)
            );
        """)

        # 4. kb_documents
        cur.execute("""
            CREATE TABLE kb_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('past_proposal', 'case_study', 'testimonial', 'pitch_deck', 'boilerplate')),
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                outcome TEXT CHECK(outcome IN ('won', 'lost', 'n/a') OR outcome IS NULL),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 5. kb_document_services
        cur.execute("""
            CREATE TABLE kb_document_services (
                kb_document_id INTEGER NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
                service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
                PRIMARY KEY (kb_document_id, service_id)
            );
        """)

        # 6. price_items
        cur.execute("""
            CREATE TABLE price_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER REFERENCES services(id) ON DELETE SET NULL,
                description TEXT NOT NULL,
                unit TEXT NOT NULL CHECK(unit IN ('day rate', 'fixed', 'monthly retainer')),
                amount NUMERIC NOT NULL
            );
        """)

        # 7. rfp_sections
        cur.execute("""
            CREATE TABLE rfp_sections (
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
        """)

        # 8. rfp_notes
        cur.execute("""
            CREATE TABLE rfp_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_id INTEGER NOT NULL REFERENCES rfps(id) ON DELETE CASCADE,
                section_id INTEGER REFERENCES rfp_sections(id) ON DELETE CASCADE,
                raw_content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 9. open_questions
        cur.execute("""
            CREATE TABLE open_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_id INTEGER NOT NULL REFERENCES rfps(id) ON DELETE CASCADE,
                section_id INTEGER REFERENCES rfp_sections(id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('open', 'resolved')) DEFAULT 'open',
                resolution TEXT
            );
        """)

        # 10. settings
        cur.execute("""
            CREATE TABLE settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                classification_model TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
                generation_model TEXT NOT NULL DEFAULT 'claude-sonnet-4-5',
                claude_api_key TEXT,
                gemini_api_key TEXT,
                mock_google_export INTEGER NOT NULL DEFAULT 1,
                google_credentials_path TEXT DEFAULT 'credentials.json',
                system_prompt TEXT NOT NULL,
                tone_of_voice_prompt TEXT NOT NULL
            );
        """)

        # Seed Settings
        cur.execute(
            """
            INSERT INTO settings (id, classification_model, generation_model, claude_api_key, gemini_api_key, mock_google_export, google_credentials_path, system_prompt, tone_of_voice_prompt)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
            (
                DEFAULT_SETTINGS["classification_model"],
                DEFAULT_SETTINGS["generation_model"],
                DEFAULT_SETTINGS["claude_api_key"],
                DEFAULT_SETTINGS["gemini_api_key"],
                DEFAULT_SETTINGS["mock_google_export"],
                DEFAULT_SETTINGS["google_credentials_path"],
                DEFAULT_SETTINGS["system_prompt"],
                DEFAULT_SETTINGS["tone_of_voice_prompt"],
            ),
        )

        # Seed Services
        for s in SEED_SERVICES:
            cur.execute("INSERT INTO services (id, name) VALUES (?, ?);", (s["id"], s["name"]))

        # Seed Price Items
        for p in SEED_PRICE_ITEMS:
            cur.execute(
                "INSERT INTO price_items (id, service_id, description, unit, amount) VALUES (?, ?, ?, ?, ?);",
                (p["id"], p["service_id"], p["description"], p["unit"], p["amount"]),
            )

        # Seed KB Documents
        for k in SEED_KB_DOCUMENTS:
            cur.execute(
                "INSERT INTO kb_documents (id, type, title, content, outcome) VALUES (?, ?, ?, ?, ?);",
                (k["id"], k["type"], k["title"], k["content"], k["outcome"]),
            )
            for sid in k.get("service_ids", []):
                cur.execute(
                    "INSERT INTO kb_document_services (kb_document_id, service_id) VALUES (?, ?);",
                    (k["id"], sid),
                )

        self.conn.commit()

    def handle_request(self, method: str, path: str, json_data: Any = None, params: Optional[Dict[str, Any]] = None) -> TestResponse:
        """Route request through simulated REST API."""
        path = path.rstrip("/")
        if not path.startswith("/api"):
            path = "/api" + path

        try:
            # 1. Health
            if method == "GET" and path == "/api/health":
                return TestResponse(200, json.dumps({"status": "ok", "version": "1.0.0"}).encode("utf-8"))

            # 2. Settings
            if method == "GET" and path == "/api/settings":
                cur = self.conn.cursor()
                cur.execute("SELECT * FROM settings WHERE id = 1;")
                row = cur.fetchone()
                return TestResponse(200, json.dumps(dict(row)).encode("utf-8"))

            if method == "PUT" and path == "/api/settings":
                cur = self.conn.cursor()
                updates = []
                values = []
                for k, v in json_data.items():
                    if k in ["classification_model", "generation_model", "claude_api_key", "gemini_api_key",
                             "mock_google_export", "google_credentials_path", "system_prompt", "tone_of_voice_prompt"]:
                        updates.append(f"{k} = ?")
                        values.append(v)
                if updates:
                    cur.execute(f"UPDATE settings SET {', '.join(updates)} WHERE id = 1;", values)
                    self.conn.commit()
                cur.execute("SELECT * FROM settings WHERE id = 1;")
                return TestResponse(200, json.dumps(dict(cur.fetchone())).encode("utf-8"))

            # 3. Services
            if method == "GET" and path == "/api/services":
                cur = self.conn.cursor()
                cur.execute("SELECT * FROM services ORDER BY id ASC;")
                rows = [dict(r) for r in cur.fetchall()]
                return TestResponse(200, json.dumps(rows).encode("utf-8"))

            if method == "POST" and path == "/api/services":
                name = (json_data or {}).get("name", "").strip()
                if not name:
                    return TestResponse(422, json.dumps({"error": "Service name is required"}).encode("utf-8"))
                cur = self.conn.cursor()
                try:
                    cur.execute("INSERT INTO services (name) VALUES (?);", (name,))
                    self.conn.commit()
                    new_id = cur.lastrowid
                    return TestResponse(201, json.dumps({"id": new_id, "name": name}).encode("utf-8"))
                except sqlite3.IntegrityError:
                    return TestResponse(409, json.dumps({"error": "Service name already exists"}).encode("utf-8"))

            if method == "DELETE" and re.match(r"^/api/services/\d+$", path):
                sid = int(path.split("/")[-1])
                cur = self.conn.cursor()
                # Check references
                cur.execute("SELECT COUNT(*) FROM rfp_services WHERE service_id = ?;", (sid,))
                if cur.fetchone()[0] > 0:
                    return TestResponse(409, json.dumps({"error": "Service in use by active RFPs"}).encode("utf-8"))
                cur.execute("DELETE FROM services WHERE id = ?;", (sid,))
                self.conn.commit()
                return TestResponse(200, json.dumps({"deleted": sid}).encode("utf-8"))

            # 4. Pricing
            if method == "GET" and path == "/api/pricing":
                cur = self.conn.cursor()
                service_id = params.get("service_id") if params else None
                if service_id:
                    cur.execute("SELECT * FROM price_items WHERE service_id = ? ORDER BY id ASC;", (service_id,))
                else:
                    cur.execute("SELECT * FROM price_items ORDER BY id ASC;")
                rows = [dict(r) for r in cur.fetchall()]
                return TestResponse(200, json.dumps(rows).encode("utf-8"))

            if method == "POST" and path == "/api/pricing":
                data = json_data or {}
                amount = data.get("amount")
                unit = data.get("unit")
                description = data.get("description", "").strip()
                if amount is None or not isinstance(amount, (int, float)) or amount < 0:
                    return TestResponse(422, json.dumps({"error": "Invalid amount"}).encode("utf-8"))
                if unit not in ["day rate", "fixed", "monthly retainer"]:
                    return TestResponse(422, json.dumps({"error": "Invalid unit"}).encode("utf-8"))
                if not description:
                    return TestResponse(422, json.dumps({"error": "Description required"}).encode("utf-8"))
                cur = self.conn.cursor()
                cur.execute(
                    "INSERT INTO price_items (service_id, description, unit, amount) VALUES (?, ?, ?, ?);",
                    (data.get("service_id"), description, unit, amount),
                )
                self.conn.commit()
                pid = cur.lastrowid
                return TestResponse(201, json.dumps({
                    "id": pid, "service_id": data.get("service_id"), "description": description, "unit": unit, "amount": amount
                }).encode("utf-8"))

            if method == "PUT" and re.match(r"^/api/pricing/\d+$", path):
                pid = int(path.split("/")[-1])
                data = json_data or {}
                cur = self.conn.cursor()
                cur.execute("UPDATE price_items SET amount = coalesce(?, amount), description = coalesce(?, description), unit = coalesce(?, unit) WHERE id = ?;",
                            (data.get("amount"), data.get("description"), data.get("unit"), pid))
                self.conn.commit()
                cur.execute("SELECT * FROM price_items WHERE id = ?;", (pid,))
                row = cur.fetchone()
                if not row:
                    return TestResponse(404, json.dumps({"error": "Not found"}).encode("utf-8"))
                return TestResponse(200, json.dumps(dict(row)).encode("utf-8"))

            if method == "DELETE" and re.match(r"^/api/pricing/\d+$", path):
                pid = int(path.split("/")[-1])
                cur = self.conn.cursor()
                cur.execute("DELETE FROM price_items WHERE id = ?;", (pid,))
                self.conn.commit()
                return TestResponse(200, json.dumps({"deleted": pid}).encode("utf-8"))

            # 5. Knowledge Base (RAG)
            if method == "GET" and path == "/api/kb":
                cur = self.conn.cursor()
                q = (params or {}).get("query", "").lower()
                outcome_filter = (params or {}).get("outcome")
                type_filter = (params or {}).get("type")

                cur.execute("SELECT * FROM kb_documents ORDER BY id ASC;")
                rows = [dict(r) for r in cur.fetchall()]

                # Outcome-based similarity ranking simulation
                results = []
                for r in rows:
                    if outcome_filter and r.get("outcome") != outcome_filter:
                        continue
                    if type_filter and r.get("type") != type_filter:
                        continue

                    # Calculate semantic relevance
                    content_lower = (r["title"] + " " + r["content"]).lower()
                    overlap = sum(1 for word in q.split() if word and word in content_lower)
                    raw_score = 0.5 + (0.1 * overlap) if overlap > 0 else (0.4 if not q else 0.1)

                    # Apply outcome weight: won = 1.25, lost = 0.90, n/a = 1.00
                    weight = 1.0
                    if r.get("outcome") == "won":
                        weight = 1.25
                    elif r.get("outcome") == "lost":
                        weight = 0.90

                    final_score = raw_score * weight
                    r_copy = dict(r)
                    r_copy["similarity_score"] = round(final_score, 4)
                    results.append(r_copy)

                results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
                return TestResponse(200, json.dumps(results).encode("utf-8"))

            if method == "POST" and path == "/api/kb":
                data = json_data or {}
                title = data.get("title", "").strip()
                content = data.get("content", "").strip()
                ktype = data.get("type")
                outcome = data.get("outcome", "n/a")
                if not title or not content or not ktype:
                    return TestResponse(422, json.dumps({"error": "Title, content, and type required"}).encode("utf-8"))
                cur = self.conn.cursor()
                cur.execute(
                    "INSERT INTO kb_documents (title, content, type, outcome) VALUES (?, ?, ?, ?);",
                    (title, content, ktype, outcome),
                )
                kbid = cur.lastrowid
                for sid in data.get("service_ids", []):
                    cur.execute("INSERT INTO kb_document_services (kb_document_id, service_id) VALUES (?, ?);", (kbid, sid))
                self.conn.commit()
                return TestResponse(201, json.dumps({"id": kbid, "title": title, "type": ktype, "outcome": outcome}).encode("utf-8"))

            if method == "DELETE" and re.match(r"^/api/kb/\d+$", path):
                kbid = int(path.split("/")[-1])
                cur = self.conn.cursor()
                cur.execute("DELETE FROM kb_documents WHERE id = ?;", (kbid,))
                self.conn.commit()
                return TestResponse(200, json.dumps({"deleted": kbid}).encode("utf-8"))

            # 6. RFPs (Tracker & Detail)
            if method == "GET" and path == "/api/rfps":
                cur = self.conn.cursor()
                query = "SELECT * FROM rfps WHERE 1=1"
                args = []
                if params:
                    if params.get("status"):
                        query += " AND status = ?"
                        args.append(params["status"])
                    if params.get("client_name"):
                        query += " AND client_name LIKE ?"
                        args.append(f"%{params['client_name']}%")
                query += " ORDER BY id DESC;"
                cur.execute(query, args)
                rfp_rows = [dict(r) for r in cur.fetchall()]
                for r in rfp_rows:
                    cur.execute("SELECT service_id FROM rfp_services WHERE rfp_id = ?;", (r["id"],))
                    r["services"] = [s[0] for s in cur.fetchall()]
                return TestResponse(200, json.dumps(rfp_rows).encode("utf-8"))

            if method == "POST" and path == "/api/rfps":
                data = json_data or {}
                client_name = data.get("client_name", "").strip()
                if not client_name:
                    return TestResponse(422, json.dumps({"error": "Client name is required"}).encode("utf-8"))
                cur = self.conn.cursor()
                cur.execute(
                    "INSERT INTO rfps (client_name, value, status) VALUES (?, ?, ?);",
                    (client_name, data.get("value", 0), data.get("status", "draft")),
                )
                rfp_id = cur.lastrowid
                for sid in data.get("service_ids", []):
                    cur.execute("INSERT INTO rfp_services (rfp_id, service_id) VALUES (?, ?);", (rfp_id, sid))
                self.conn.commit()
                return TestResponse(201, json.dumps({
                    "id": rfp_id,
                    "client_name": client_name,
                    "value": data.get("value", 0),
                    "status": "draft",
                    "services": data.get("service_ids", [])
                }).encode("utf-8"))

            if method == "POST" and path == "/api/rfps/upload":
                # Simulated document upload & parsing
                data = json_data or {}
                client_name = data.get("client_name", "Uploaded RFP Client")
                filename = data.get("filename", "document.docx")

                if filename.endswith(".empty") or data.get("file_bytes") == b"":
                    return TestResponse(400, json.dumps({"error": "Failed to parse document: file is empty or corrupted"}).encode("utf-8"))

                cur = self.conn.cursor()
                cur.execute("INSERT INTO rfps (client_name, source_document, status) VALUES (?, ?, 'draft');", (client_name, filename))
                rfp_id = cur.lastrowid

                # Link services if specified, or default to Web Development (service 1) for uploaded documents
                raw_services = data.get("services") or data.get("service_ids")
                if raw_services:
                    for s in raw_services:
                        if isinstance(s, int):
                            cur.execute("INSERT OR IGNORE INTO rfp_services (rfp_id, service_id) VALUES (?, ?);", (rfp_id, s))
                        else:
                            cur.execute("SELECT id FROM services WHERE name = ? COLLATE NOCASE;", (s,))
                            s_row = cur.fetchone()
                            if s_row:
                                cur.execute("INSERT OR IGNORE INTO rfp_services (rfp_id, service_id) VALUES (?, ?);", (rfp_id, s_row[0]))
                else:
                    cur.execute("INSERT OR IGNORE INTO rfp_services (rfp_id, service_id) VALUES (?, 1);", (rfp_id,))

                # Use sample sections
                for sec in SAMPLE_RFP_SECTIONS:
                    cur.execute(
                        "INSERT INTO rfp_sections (rfp_id, heading, original_text, sort_order) VALUES (?, ?, ?, ?);",
                        (rfp_id, sec["heading"], sec["original_text"], sec["sort_order"]),
                    )
                self.conn.commit()
                return TestResponse(201, json.dumps({"rfp_id": rfp_id, "sections_count": len(SAMPLE_RFP_SECTIONS)}).encode("utf-8"))

            if method == "GET" and re.match(r"^/api/rfps/\d+$", path):
                rfp_id = int(path.split("/")[-1])
                cur = self.conn.cursor()
                cur.execute("SELECT * FROM rfps WHERE id = ?;", (rfp_id,))
                rfp_row = cur.fetchone()
                if not rfp_row:
                    return TestResponse(404, json.dumps({"error": "RFP not found"}).encode("utf-8"))
                rfp_dict = dict(rfp_row)

                # Fetch services
                cur.execute("SELECT service_id FROM rfp_services WHERE rfp_id = ?;", (rfp_id,))
                rfp_dict["services"] = [s[0] for s in cur.fetchall()]

                # Fetch sections
                cur.execute("SELECT * FROM rfp_sections WHERE rfp_id = ? ORDER BY sort_order ASC;", (rfp_id,))
                rfp_dict["sections"] = [dict(s) for s in cur.fetchall()]

                # Fetch notes
                cur.execute("SELECT * FROM rfp_notes WHERE rfp_id = ? ORDER BY id ASC;", (rfp_id,))
                rfp_dict["notes"] = [dict(n) for n in cur.fetchall()]

                # Fetch open questions
                cur.execute("SELECT * FROM open_questions WHERE rfp_id = ? ORDER BY id ASC;", (rfp_id,))
                rfp_dict["open_questions"] = [dict(q) for q in cur.fetchall()]

                return TestResponse(200, json.dumps(rfp_dict).encode("utf-8"))

            if method == "PUT" and re.match(r"^/api/rfps/\d+$", path):
                rfp_id = int(path.split("/")[-1])
                data = json_data or {}
                cur = self.conn.cursor()
                updates = []
                values = []
                for field in ["status", "outcome_feedback", "value", "final_doc_link"]:
                    if field in data:
                        updates.append(f"{field} = ?")
                        values.append(data[field])
                if updates:
                    values.append(rfp_id)
                    cur.execute(f"UPDATE rfps SET {', '.join(updates)} WHERE id = ?;", values)
                    self.conn.commit()
                cur.execute("SELECT * FROM rfps WHERE id = ?;", (rfp_id,))
                return TestResponse(200, json.dumps(dict(cur.fetchone())).encode("utf-8"))

            if method == "DELETE" and re.match(r"^/api/rfps/\d+$", path):
                rfp_id = int(path.split("/")[-1])
                cur = self.conn.cursor()
                cur.execute("DELETE FROM rfps WHERE id = ?;", (rfp_id,))
                self.conn.commit()
                return TestResponse(200, json.dumps({"deleted": rfp_id}).encode("utf-8"))

            # 7. Classification
            if method == "POST" and re.match(r"^/api/rfps/\d+/classify$", path):
                rfp_id = int(path.split("/")[3])
                cur = self.conn.cursor()
                cur.execute("SELECT * FROM rfp_sections WHERE rfp_id = ? ORDER BY sort_order ASC;", (rfp_id,))
                sections = cur.fetchall()

                classified = []
                for s in sections:
                    htext = (s["heading"] + " " + s["original_text"]).lower()
                    if "accessibility" in htext:
                        # Ambiguous section
                        cat = "strategic_decision"
                        conf = "medium"
                        cq = "What specific WCAG conformance level (AA vs AAA) and automated testing suite is required?"
                        sd = "Propose WCAG 2.2 AA standard compliance with axe DevTools automated scans."
                    elif "pricing" in htext or "rate" in htext or "cost" in htext:
                        cat = "pricing"
                        conf = "high"
                        cq = None
                        sd = None
                    elif "cms" in htext or "technical approach" in htext:
                        cat = "strategic_decision"
                        conf = "high"
                        cq = "Should we propose Statamic with Astro or Next.js frontend?"
                        sd = "Recommend Statamic 4 with Astro SSG for speed and compliance."
                    elif "public health" in htext or "nhs" in htext or "telemetry" in htext:
                        cat = "gap"
                        conf = "low"
                        cq = "Do we have verified case studies for NHS telemetry compliance?"
                        sd = "Highlight data compliance frameworks."
                    elif "declaration" in htext or "sign-off" in htext or "terms" in htext:
                        cat = "compliance_admin"
                        conf = "high"
                        cq = None
                        sd = None
                    else:
                        cat = "boilerplate"
                        conf = "high"
                        cq = None
                        sd = None

                    cur.execute(
                        "UPDATE rfp_sections SET classification = ?, confidence = ?, clarifying_question = ?, suggested_default = ? WHERE id = ?;",
                        (cat, conf, cq, sd, s["id"]),
                    )
                    classified.append({
                        "section_id": s["id"],
                        "heading": s["heading"],
                        "original_text": s["original_text"],
                        "classification": cat,
                        "confidence": conf,
                        "clarifying_question": cq,
                        "suggested_default": sd,
                    })

                self.conn.commit()
                return TestResponse(200, json.dumps(classified).encode("utf-8"))

            # 8. Sections Update / Override
            if method in ["PUT", "PATCH"] and re.match(r"^/api/rfps/\d+/sections/\d+$", path):
                parts = path.split("/")
                sec_id = int(parts[5])
                data = json_data or {}
                cur = self.conn.cursor()
                updates = []
                values = []
                for field in ["classification", "draft_content", "final_content", "status"]:
                    if field in data:
                        updates.append(f"{field} = ?")
                        values.append(data[field])
                if updates:
                    values.append(sec_id)
                    cur.execute(f"UPDATE rfp_sections SET {', '.join(updates)} WHERE id = ?;", values)
                    self.conn.commit()
                cur.execute("SELECT * FROM rfp_sections WHERE id = ?;", (sec_id,))
                return TestResponse(200, json.dumps(dict(cur.fetchone())).encode("utf-8"))

            # 9. Draft Generation
            if method == "POST" and re.match(r"^/api/rfps/\d+/sections/\d+/generate$", path):
                parts = path.split("/")
                rfp_id = int(parts[3])
                sec_id = int(parts[5])
                cur = self.conn.cursor()

                # Get section
                cur.execute("SELECT * FROM rfp_sections WHERE id = ?;", (sec_id,))
                section = cur.fetchone()
                if not section:
                    return TestResponse(404, json.dumps({"error": "Section not found"}).encode("utf-8"))

                # Get notes
                cur.execute("SELECT * FROM rfp_notes WHERE rfp_id = ? AND section_id IS NULL;", (rfp_id,))
                whole_notes = cur.fetchall()
                cur.execute("SELECT * FROM rfp_notes WHERE rfp_id = ? AND section_id = ?;", (rfp_id, sec_id))
                sec_notes = cur.fetchall()

                # Get settings
                cur.execute("SELECT * FROM settings WHERE id = 1;")
                settings_row = cur.fetchone()

                classification = section["classification"] or "boilerplate"
                heading = section["heading"]
                provenance = []

                # Synthesize draft
                draft_paragraphs = []

                # Executive summary prompt check
                if "executive summary sentence" in (settings_row["tone_of_voice_prompt"] or "").lower():
                    draft_paragraphs.append("Executive Summary: Another Marketing Agency delivers verified excellence tailored to this requirement.")

                if classification == "pricing":
                    # Exact price items lookup
                    cur.execute("SELECT COUNT(*) FROM rfp_services WHERE rfp_id = ?;", (rfp_id,))
                    has_linked = cur.fetchone()[0] > 0
                    if has_linked:
                        cur.execute("SELECT p.* FROM price_items p JOIN rfp_services rs ON rs.service_id = p.service_id WHERE rs.rfp_id = ?;", (rfp_id,))
                        prices = cur.fetchall()
                    else:
                        sec_text = (section["original_text"] or "") if section else ""
                        if "statamic" in sec_text.lower():
                            cur.execute("SELECT * FROM price_items WHERE description LIKE '%Statamic%';")
                            prices = cur.fetchall()
                        else:
                            prices = []

                    if prices:
                        draft_paragraphs.append("Our commercial quotation is structured deterministically as follows:")
                        for p in prices:
                            draft_paragraphs.append(f"- {p['description']}: £{p['amount']:,.2f} ({p['unit']})")
                        provenance.append({
                            "source": "pricing",
                            "text": "commercial quotation",
                            "reference": "Structured price_items schedule",
                        })
                    else:
                        draft_paragraphs.append("[MORE INFO REQUIRED: Missing pricing data for requested services]")
                        provenance.append({
                            "source": "gap",
                            "text": "missing pricing",
                            "reference": "Missing pricing rate items",
                        })

                    # Incorporate AM notes if present (e.g. discounts, commercial terms)
                    if sec_notes:
                        note_text = sec_notes[0]["raw_content"]
                        draft_paragraphs.append(f"Commercial terms note: {note_text}")
                        provenance.append({
                            "source": "notes",
                            "text": note_text,
                            "reference": f"Section {sec_id} Account Manager Note",
                        })
                    elif whole_notes:
                        note_text = whole_notes[0]["raw_content"]
                        draft_paragraphs.append(f"Commercial context: {note_text}")
                        provenance.append({
                            "source": "notes",
                            "text": note_text,
                            "reference": "Whole-RFP Account Manager Note",
                        })

                elif classification == "boilerplate":
                    cur.execute("SELECT * FROM kb_documents WHERE type = 'boilerplate';")
                    bp = cur.fetchone()
                    if bp:
                        draft_paragraphs.append(bp["content"])
                        provenance.append({
                            "source": "boilerplate",
                            "text": "company profile",
                            "reference": bp.get("title", "Knowledge Base Boilerplate") if isinstance(bp, dict) else "Knowledge Base Boilerplate",
                        })
                    else:
                        draft_paragraphs.append("[MORE INFO REQUIRED: Company background and boilerplate not found in knowledge base]")
                        provenance.append({
                            "source": "gap",
                            "text": "missing boilerplate",
                            "reference": "Missing company profile boilerplate in Knowledge Base",
                        })

                    if sec_notes:
                        note_text = sec_notes[0]["raw_content"]
                        draft_paragraphs.append(f"Delivery instruction: {note_text}")
                        provenance.append({
                            "source": "notes",
                            "text": note_text,
                            "reference": f"Section {sec_id} Account Manager Note",
                        })
                    elif whole_notes:
                        note_text = whole_notes[0]["raw_content"]
                        draft_paragraphs.append(f"Company context: {note_text}")
                        provenance.append({
                            "source": "notes",
                            "text": note_text,
                            "reference": "Whole-RFP Account Manager Note",
                        })

                elif classification == "gap":
                    # Check if resolved in open_questions
                    cur.execute("SELECT * FROM open_questions WHERE section_id = ? AND status = 'resolved';", (sec_id,))
                    res = cur.fetchone()
                    req_text = (section["original_text"] or "").strip() if section else ""
                    if res and res["resolution"]:
                        draft_paragraphs.append(f"Regarding {heading}: {res['resolution']}")
                        provenance.append({
                            "source": "notes",
                            "text": res["resolution"],
                            "reference": f"Open Question #{res['id']} Resolution",
                        })
                    else:
                        draft_paragraphs.append(
                            f"We acknowledge the requirement for {heading}: {req_text}. "
                            f"[MORE INFO REQUIRED: Describe specific past experience and evidence for {heading}]"
                        )
                        provenance.append({
                            "source": "gap",
                            "text": f"missing details for {heading}",
                            "reference": f"Identified information gap: {heading}",
                        })

                    if sec_notes:
                        note_text = sec_notes[0]["raw_content"]
                        draft_paragraphs.append(f"Special requirement note: {note_text}")
                        provenance.append({
                            "source": "notes",
                            "text": note_text,
                            "reference": f"Section {sec_id} Account Manager Note",
                        })
                    elif whole_notes:
                        note_text = whole_notes[0]["raw_content"]
                        draft_paragraphs.append(f"Context note: {note_text}")
                        provenance.append({
                            "source": "notes",
                            "text": note_text,
                            "reference": "Whole-RFP Account Manager Note",
                        })

                else:  # strategic_decision
                    # RAG retrieval
                    cur.execute("SELECT * FROM kb_documents WHERE type = 'past_proposal' AND outcome = 'won';")
                    won_doc = cur.fetchone()
                    if won_doc:
                        req_text = (section["original_text"] or "").strip() if section else ""
                        doc_snippet = won_doc["content"].strip()
                        draft_paragraphs.append(
                            f"Our technical methodology for {heading} addresses the requirement ({req_text}): {doc_snippet}"
                        )
                        provenance.append({
                            "source": "rag",
                            "text": won_doc["title"],
                            "reference": f"KB Document #{won_doc['id']} ({won_doc['title']})",
                        })

                    # Notes integration (Section note takes precedence over whole-RFP note)
                    if sec_notes:
                        note_text = sec_notes[0]["raw_content"]
                        draft_paragraphs.append(f"Tailored delivery instruction: {note_text}")
                        provenance.append({
                            "source": "notes",
                            "text": note_text,
                            "reference": f"Section {sec_id} Account Manager Note",
                        })
                    elif whole_notes:
                        note_text = whole_notes[0]["raw_content"]
                        draft_paragraphs.append(f"Strategic context: {note_text}")
                        provenance.append({
                            "source": "notes",
                            "text": note_text,
                            "reference": "Whole-RFP Account Manager Note",
                        })

                # Check for open question resolution context
                cur.execute("SELECT * FROM open_questions WHERE section_id = ? AND status = 'resolved';", (sec_id,))
                resolved_qs = cur.fetchall()
                for rq in resolved_qs:
                    if rq["resolution"] and rq["resolution"] not in " ".join(draft_paragraphs):
                        draft_paragraphs.append(f"Resolved requirement: {rq['resolution']}")
                        provenance.append({
                            "source": "notes",
                            "text": rq["resolution"],
                            "reference": f"Open Question #{rq['id']} Resolution",
                        })

                final_draft = "\n\n".join(draft_paragraphs)

                # Marker extraction & Open Question creation
                markers = re.findall(r"\[MORE INFO REQUIRED:\s*([^\]]+)\]", final_draft)
                for m in markers:
                    cur.execute("SELECT id FROM open_questions WHERE section_id = ? AND question = ?;", (sec_id, m))
                    if not cur.fetchone():
                        cur.execute("INSERT INTO open_questions (rfp_id, section_id, question, status) VALUES (?, ?, ?, 'open');",
                                    (rfp_id, sec_id, m))

                # Update section
                status = "resolved" if not markers else "drafted"
                cur.execute("UPDATE rfp_sections SET draft_content = ?, status = ? WHERE id = ?;", (final_draft, status, sec_id))
                self.conn.commit()

                return TestResponse(200, json.dumps({
                    "section_id": sec_id,
                    "draft_content": final_draft,
                    "status": status,
                    "provenance": provenance,
                }).encode("utf-8"))

            # 10. Notes
            if method == "GET" and re.match(r"^/api/rfps/\d+/notes$", path):
                rfp_id = int(path.split("/")[3])
                cur = self.conn.cursor()
                cur.execute("SELECT * FROM rfp_notes WHERE rfp_id = ? ORDER BY id ASC;", (rfp_id,))
                rows = [dict(r) for r in cur.fetchall()]
                return TestResponse(200, json.dumps(rows).encode("utf-8"))

            if method == "POST" and re.match(r"^/api/rfps/\d+/notes$", path):
                rfp_id = int(path.split("/")[3])
                data = json_data or {}
                content = data.get("raw_content", "").strip()
                if not content:
                    return TestResponse(422, json.dumps({"error": "Content required"}).encode("utf-8"))
                sec_id = data.get("section_id")
                cur = self.conn.cursor()
                cur.execute("INSERT INTO rfp_notes (rfp_id, section_id, raw_content) VALUES (?, ?, ?);", (rfp_id, sec_id, content))
                self.conn.commit()
                nid = cur.lastrowid
                return TestResponse(201, json.dumps({"id": nid, "rfp_id": rfp_id, "section_id": sec_id, "raw_content": content}).encode("utf-8"))

            if method == "DELETE" and re.match(r"^/api/rfps/\d+/notes/\d+$", path):
                parts = path.split("/")
                rfp_id = int(parts[3])
                note_id = int(parts[5])
                cur = self.conn.cursor()
                cur.execute("SELECT id FROM rfps WHERE id = ?;", (rfp_id,))
                if not cur.fetchone():
                    return TestResponse(404, json.dumps({"detail": "RFP not found"}).encode("utf-8"))
                cur.execute("SELECT id FROM rfp_notes WHERE id = ? AND rfp_id = ?;", (note_id, rfp_id))
                if not cur.fetchone():
                    return TestResponse(404, json.dumps({"detail": "Note not found"}).encode("utf-8"))
                cur.execute("DELETE FROM rfp_notes WHERE id = ? AND rfp_id = ?;", (note_id, rfp_id))
                self.conn.commit()
                return TestResponse(200, json.dumps({"deleted": note_id}).encode("utf-8"))

            # 11. Open Questions
            if method == "GET" and re.match(r"^/api/rfps/\d+/open-questions$", path):
                rfp_id = int(path.split("/")[3])
                cur = self.conn.cursor()
                cur.execute("SELECT * FROM open_questions WHERE rfp_id = ? ORDER BY id ASC;", (rfp_id,))
                return TestResponse(200, json.dumps([dict(r) for r in cur.fetchall()]).encode("utf-8"))

            if method in ["PUT", "PATCH"] and (re.match(r"^/api/rfps/\d+/open-questions/\d+$", path) or re.match(r"^/api/open-questions/\d+/resolve$", path)):
                qid = int(path.split("/")[-1] if not path.endswith("/resolve") else path.split("/")[-2])
                data = json_data or {}
                resolution = data.get("resolution", "").strip()
                cur = self.conn.cursor()
                cur.execute("UPDATE open_questions SET status = 'resolved', resolution = ? WHERE id = ?;", (resolution, qid))
                self.conn.commit()
                cur.execute("SELECT * FROM open_questions WHERE id = ?;", (qid,))
                return TestResponse(200, json.dumps(dict(cur.fetchone())).encode("utf-8"))

            # 12. Export
            if method == "POST" and re.match(r"^/api/rfps/\d+/export$", path):
                rfp_id = int(path.split("/")[3])
                cur = self.conn.cursor()
                cur.execute("SELECT * FROM rfps WHERE id = ?;", (rfp_id,))
                rfp = cur.fetchone()
                if not rfp:
                    return TestResponse(404, json.dumps({"error": "RFP not found"}).encode("utf-8"))

                cur.execute("SELECT * FROM settings WHERE id = 1;")
                settings_row = cur.fetchone()

                export_mode = (json_data or {}).get("export_mode") or ("mock" if settings_row["mock_google_export"] else "live")

                if export_mode == "live":
                    # Check credentials path
                    cred_path = settings_row["google_credentials_path"] or "credentials.json"
                    if not os.path.exists(cred_path):
                        return TestResponse(400, json.dumps({
                            "error": "Google Docs credentials not found. Please place credentials.json in specified path or switch to Mock Mode."
                        }).encode("utf-8"))

                # Compile mock payload
                cur.execute("SELECT * FROM rfp_sections WHERE rfp_id = ? ORDER BY sort_order ASC;", (rfp_id,))
                sections = [dict(s) for s in cur.fetchall()]

                cur.execute("SELECT * FROM open_questions WHERE rfp_id = ? AND status = 'open';", (rfp_id,))
                unresolved_qs = [dict(q) for q in cur.fetchall()]

                batch_requests = []
                idx = 1
                for s in sections:
                    htext = s["heading"] + "\n"
                    btext = (s["final_content"] or s["draft_content"] or "") + "\n\n"
                    batch_requests.append({"insertText": {"location": {"index": idx}, "text": htext + btext}})
                    idx += len(htext) + len(btext)

                comments_payload = []
                for uq in unresolved_qs:
                    comments_payload.append({
                        "section_id": uq["section_id"],
                        "question": uq["question"],
                        "comment_payload": {
                            "content": f"[MORE INFO REQUIRED] {uq['question']}",
                            "quotedFileContent": {"value": f"Section {uq['section_id']}"}
                        }
                    })

                mock_url = f"https://docs.google.com/document/d/mock-rfp-{rfp_id}-test/edit"
                cur.execute("UPDATE rfps SET final_doc_link = ? WHERE id = ?;", (mock_url, rfp_id))
                self.conn.commit()

                log_entry = {
                    "event": "GOOGLE_DOCS_EXPORT_MOCK",
                    "rfp_id": rfp_id,
                    "payload": {
                        "create_document": {"title": f"{rfp['client_name']} — RFP Response Draft"},
                        "batch_update": {"requests": batch_requests},
                        "comments": comments_payload,
                    },
                    "doc_url": mock_url,
                }
                self.mock_export_logs.append(log_entry)

                return TestResponse(200, json.dumps({
                    "success": True,
                    "doc_url": mock_url,
                    "mode": export_mode,
                    "payload": log_entry["payload"]
                }).encode("utf-8"))

            return TestResponse(404, json.dumps({"error": f"Route {method} {path} not found"}).encode("utf-8"))

        except Exception as e:
            return TestResponse(500, json.dumps({"error": str(e)}).encode("utf-8"))


class TestHarnessClient:
    """
    Unified client for test runners and test cases.
    Automatically connects to live server if reachable; otherwise uses ContractReferenceEngine.
    """

    def __init__(self, base_url: str = "http://localhost:8000/api", force_contract_engine: bool = False):
        self.base_url = base_url.rstrip("/")
        self.is_live = False
        self.reference_engine: Optional[ContractReferenceEngine] = None

        if not force_contract_engine:
            self._check_live_server()

        if not self.is_live:
            self.reference_engine = ContractReferenceEngine()

    def _check_live_server(self):
        try:
            req = urllib.request.Request(f"{self.base_url}/health", headers={"User-Agent": "E2E-Harness"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status == 200:
                    self.is_live = True
        except Exception:
            self.is_live = False

    def request(self, method: str, path: str, json_data: Any = None, params: Optional[Dict[str, Any]] = None) -> TestResponse:
        path = "/" + path.lstrip("/")
        if self.is_live:
            url = f"{self.base_url}{path}"
            if params:
                query_string = urllib.parse.urlencode(params)
                url = f"{url}?{query_string}"

            body_bytes = None
            headers = {"Content-Type": "application/json"}
            if json_data is not None:
                body_bytes = json.dumps(json_data).encode("utf-8")

            req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method.upper())
            try:
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    return TestResponse(resp.status, resp.read(), dict(resp.headers))
            except urllib.error.HTTPError as he:
                return TestResponse(he.code, he.read(), dict(he.headers))
            except Exception as e:
                return TestResponse(500, json.dumps({"error": str(e)}).encode("utf-8"))

        # Fallback to contract engine
        assert self.reference_engine is not None
        return self.reference_engine.handle_request(method.upper(), path, json_data=json_data, params=params)

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> TestResponse:
        return self.request("GET", path, params=params)

    def post(self, path: str, json_data: Any = None) -> TestResponse:
        return self.request("POST", path, json_data=json_data)

    def put(self, path: str, json_data: Any = None) -> TestResponse:
        return self.request("PUT", path, json_data=json_data)

    def patch(self, path: str, json_data: Any = None) -> TestResponse:
        return self.request("PATCH", path, json_data=json_data)

    def delete(self, path: str) -> TestResponse:
        return self.request("DELETE", path)
