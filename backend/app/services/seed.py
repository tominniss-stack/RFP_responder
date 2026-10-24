"""Database seeding and sample document generation service (F25).

Implements:
1. Idempotent seeding of 5 services, 8 price items, and 5 KB entries with won-biasing.
2. In-memory vector store synchronization (sync_vector_store_from_db).
3. Sample RFP generation (.docx and .pdf) containing 7 distinct sections
   (BOILERPLATE, STRATEGIC_DECISION, PRICING, GAP, COMPLIANCE_ADMIN)
   with Section 5 deliberately ambiguous ("Accessibility Compliance & Implementation Experience").
4. Asset generation into backend/data/ and frontend/public/.
5. CLI runner and database initialization hooks.
"""

import io
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union
import xml.sax.saxutils
import zipfile

from app.database import get_db_context
from app.models import (
    DEFAULT_SERVICES,
    SEED_KB_DOCUMENTS,
    SEED_PRICE_ITEMS,
    create_tables,
    seed_defaults,
)
from app.services.vector_store import sync_vector_store_from_db

SAMPLE_SECTIONS: List[Tuple[str, str]] = [
    (
        "1. Agency Overview & Company Credentials",
        "Provide a comprehensive overview of your agency including company history, organizational structure, "
        "core technical capabilities, and verified accreditations. Specifically state your ISO 27001 Information "
        "Security status, Cyber Essentials accreditation, and level of Professional Indemnity Insurance.",
    ),
    (
        "2. Technical Architecture & CMS Platform Recommendation",
        "Outline your recommended Content Management System (CMS) and front-end delivery architecture. "
        "Compare headless CMS vs. traditional monolithic approaches, and specify your recommended platform "
        "with regard to security, decoupled architecture, and the trade-offs between candidate platforms.",
    ),
    (
        "3. Commercial Quotation & Pricing Schedule",
        "Provide a detailed commercial quotation and schedule of costs for delivery and maintenance. "
        "Outline day rates for key technical roles (Senior Developer, UX Designer) and fixed costs for "
        "core discovery packages or headless CMS website deployment, as well as recurring monthly retainer options.",
    ),
    (
        "4. Public Sector Healthcare & NHS Portal Experience",
        "Describe your agency specific past experience and case studies delivering high-volume patient-facing "
        "web portals within the NHS and public health sector. Provide verified evidence of clinical telemetry "
        "integration, patient data governance, and NHS identity verification.",
    ),
    (
        "5. Approach to Accessibility Compliance & Implementation Experience",
        "Describe your recommended technical approach to accessibility compliance, including any relevant experience. "
        "Specifically address how your design and engineering teams satisfy WCAG 2.2 Level AA requirements, "
        "perform automated axe-core scans versus manual assistive technology audits, and provide examples of "
        "previous digital interfaces built to public sector accessibility standards.",
    ),
    (
        "6. Information Governance, Data Protection & Mandatory Declarations",
        "The supplier must complete this formal declaration confirming strict compliance with the UK General Data "
        "Protection Regulation (UK GDPR) and Data Protection Act 2018. Confirm that no data will be transferred "
        "outside the UK/EEA without prior written consent, and provide an authorized officer signature agreeing to "
        "the standard tender terms and conditions.",
    ),
    (
        "7. Technical SEO, Search Marketing & SLA Governance",
        "Outline your recommended technical SEO auditing, search marketing (PPC) management, and service level "
        "agreement (SLA) governance to ensure continuous performance optimization and high search visibility.",
    ),
]


def generate_sample_docx(dest_path: Optional[Union[str, Path]] = None) -> bytes:
    """Generate a valid DOCX archive in memory with heading styles containing the 7 sample sections."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        p_xmls = []
        for heading, text in SAMPLE_SECTIONS:
            h_esc = xml.sax.saxutils.escape(heading)
            t_esc = xml.sax.saxutils.escape(text)
            p_xmls.append(f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{h_esc}</w:t></w:r></w:p>')
            p_xmls.append(f'<w:p><w:r><w:t>{t_esc}</w:t></w:r></w:p>')

        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{" ".join(p_xmls)}</w:body>'
            '</w:document>'
        )
        zf.writestr("word/document.xml", doc_xml)
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>',
        )

    data = buf.getvalue()
    if dest_path is not None:
        p = Path(dest_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return data


def generate_sample_pdf(dest_path: Optional[Union[str, Path]] = None) -> bytes:
    """Generate a valid PDF-1.4 stream containing the 7 sample sections extractable via pdfplumber."""
    lines = ["BT /F1 10 Tf 50 750 Td"]
    for h, b in SAMPLE_SECTIONS:
        h_clean = h.replace("(", "").replace(")", "")
        lines.append(f"({h_clean}) Tj 0 -15 Td")
        words = b.replace("(", "").replace(")", "").split(" ")
        chunk = []
        for w in words:
            chunk.append(w)
            if len(" ".join(chunk)) > 70:
                s = " ".join(chunk)
                lines.append(f"({s}) Tj 0 -12 Td")
                chunk = []
        if chunk:
            s = " ".join(chunk)
            lines.append(f"({s}) Tj 0 -18 Td")
    lines.append("ET")

    stream_content = "\n".join(lines).encode("latin1")
    length = len(stream_content)
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 1500] "
        b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
        b"/Contents 4 0 R >> endobj\n"
        b"4 0 obj << /Length " + str(length).encode("ascii") + b" >>\nstream\n"
        + stream_content
        + b"\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"0000000280 00000 n \n"
        b"trailer << /Size 5 /Root 1 0 R >>\nstartxref\n400\n%%EOF\n"
    )

    if dest_path is not None:
        p = Path(dest_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(pdf)
    return pdf


def generate_sample_rfp_assets(base_dir: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    """Ensure sample_rfp.docx and sample_rfp.pdf are created in backend/data and copied to frontend/public."""
    if base_dir is None:
        backend_dir = Path(__file__).resolve().parent.parent.parent
    else:
        backend_dir = Path(base_dir)

    data_dir = backend_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    docx_path = data_dir / "sample_rfp.docx"
    pdf_path = data_dir / "sample_rfp.pdf"

    generate_sample_docx(docx_path)
    generate_sample_pdf(pdf_path)

    # Attempt to copy to frontend/public if frontend directory exists
    project_root = backend_dir.parent if backend_dir.name == "backend" else backend_dir
    frontend_public = project_root / "frontend" / "public"
    try:
        frontend_public.mkdir(parents=True, exist_ok=True)
        shutil.copy2(docx_path, frontend_public / "sample_rfp.docx")
        shutil.copy2(pdf_path, frontend_public / "sample_rfp.pdf")
    except Exception:
        pass

    return {
        "docx": str(docx_path),
        "pdf": str(pdf_path),
    }


def seed_database(conn: sqlite3.Connection) -> None:
    """Seed default records into SQLite and sync the vector store."""
    seed_defaults(conn)
    sync_vector_store_from_db(conn)


def ensure_seeded(
    db_path: Optional[str] = None,
    reset: bool = False,
    generate_files: bool = True,
) -> None:
    """Ensure SQLite tables exist, default records are seeded, and sample assets exist.
    
    Args:
        db_path: Optional SQLite database path override.
        reset: If True, drop existing tables and re-seed from scratch.
        generate_files: If True, generate sample DOCX/PDF assets.
    """
    with get_db_context(db_path) as conn:
        if reset:
            tables = [
                "kb_document_services",
                "rfp_services",
                "open_questions",
                "rfp_notes",
                "rfp_sections",
                "price_items",
                "kb_documents",
                "services",
                "rfps",
                "settings",
            ]
            for tbl in tables:
                conn.execute(f"DROP TABLE IF EXISTS {tbl};")
            conn.commit()

        create_tables(conn)
        seed_database(conn)

    if generate_files:
        generate_sample_rfp_assets()


if __name__ == "__main__":
    ensure_seeded()
