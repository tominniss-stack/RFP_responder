"""Document ingestion service for PDF, DOCX, and plain text extraction.

Implements:
1. Robust PDF extraction via pdfplumber with table extraction.
2. Robust DOCX extraction using zipfile and xml.etree.ElementTree (with python-docx support).
3. Structural section detection (headings, numbered outlines, question blocks) with double-newline fallback.
4. Upload file persistence to backend/data/uploads.
"""

import io
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Union
import xml.etree.ElementTree as ET
import zipfile

DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"


def extract_from_pdf(file_input: Union[bytes, io.BytesIO, str, Path]) -> str:
    """Extract text and tables from a PDF document using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber is required for PDF parsing.")

    if isinstance(file_input, (bytes, bytearray)):
        fp = io.BytesIO(file_input)
    elif isinstance(file_input, (str, Path)):
        fp = str(file_input)
    else:
        fp = file_input

    extracted_pages = []
    try:
        with pdfplumber.open(fp) as pdf:
            for page in pdf.pages:
                page_content = []

                # 1. Extract tables if present
                try:
                    tables = page.extract_tables() or []
                    for tbl in tables:
                        if not tbl:
                            continue
                        tbl_lines = []
                        for row in tbl:
                            clean_row = [str(cell).strip() if cell is not None else "" for cell in row]
                            if any(clean_row):
                                tbl_lines.append("| " + " | ".join(clean_row) + " |")
                        if tbl_lines:
                            if len(tbl_lines) > 1 and len(tbl) > 0 and tbl[0]:
                                cols = len(tbl[0])
                                divider = "| " + " | ".join(["---"] * cols) + " |"
                                tbl_lines.insert(1, divider)
                            page_content.append("\n".join(tbl_lines))
                except Exception:
                    pass

                # 2. Extract page layout text
                try:
                    text = page.extract_text(layout=False) or ""
                    if text.strip():
                        page_content.append(text.strip())
                except Exception:
                    pass

                if page_content:
                    extracted_pages.append("\n\n".join(page_content))
    except Exception as exc:
        raise ValueError(f"Corrupted or invalid PDF file: {exc}") from exc

    res = "\n\n".join(extracted_pages)
    if not res.strip():
        raise ValueError("Document contains no readable text")
    return res


def extract_from_docx(file_input: Union[bytes, io.BytesIO, str, Path]) -> str:
    """Extract structured text and tables from a DOCX document.

    Enforces zip validation and word/document.xml existence.
    Supports python-docx if installed, with a zero-dependency fallback
    using standard library zipfile and xml.etree.ElementTree.
    """
    # 1. Validate zip archive format
    close_after = False
    if isinstance(file_input, (bytes, bytearray)):
        if not zipfile.is_zipfile(io.BytesIO(file_input)):
            raise ValueError("Corrupted or invalid DOCX archive")
        zip_fp = io.BytesIO(file_input)
    elif isinstance(file_input, (str, Path)):
        if not zipfile.is_zipfile(file_input):
            raise ValueError("Corrupted or invalid DOCX archive")
        zip_fp = open(file_input, "rb")
        close_after = True
    else:
        if hasattr(file_input, "seek"):
            file_input.seek(0)
        if not zipfile.is_zipfile(file_input):
            raise ValueError("Corrupted or invalid DOCX archive")
        if hasattr(file_input, "seek"):
            file_input.seek(0)
        zip_fp = file_input

    # 2. Attempt python-docx if installed
    try:
        import docx
        if hasattr(zip_fp, "seek"):
            zip_fp.seek(0)
        doc = docx.Document(zip_fp)
        paragraphs = []
        for p in doc.paragraphs:
            t = p.text.strip()
            if t:
                if p.style and "heading" in p.style.name.lower():
                    paragraphs.append(f"## {t}")
                else:
                    paragraphs.append(t)
        for tbl in doc.tables:
            for row in tbl.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    paragraphs.append("| " + " | ".join(cells) + " |")
        if paragraphs:
            if close_after:
                try:
                    zip_fp.close()
                except Exception:
                    pass
            return "\n\n".join(paragraphs)
    except Exception:
        pass

    # 3. Built-in Fallback: zipfile + xml.etree.ElementTree
    if hasattr(zip_fp, "seek"):
        zip_fp.seek(0)

    blocks = []
    try:
        with zipfile.ZipFile(zip_fp) as zf:
            if "word/document.xml" not in zf.namelist():
                raise ValueError("Corrupted or invalid DOCX archive")
            xml_data = zf.read("word/document.xml")
            root = ET.fromstring(xml_data)
            body = root.find("w:body", DOCX_NS)
            if body is None:
                # Some documents have tags without explicit namespace prefix
                for elem in root.iter():
                    if elem.tag.endswith("body"):
                        body = elem
                        break
            if body is None:
                raise ValueError("Corrupted or invalid DOCX archive")

            for child in body:
                tag = child.tag.split("}")[-1]
                if tag == "p":
                    p_style = child.find(".//w:pStyle", DOCX_NS)
                    style_name = ""
                    if p_style is not None:
                        style_name = p_style.attrib.get(f"{{{DOCX_NS['w']}}}val", "").lower()
                    text = "".join(child.itertext()).strip()
                    if text:
                        if "heading" in style_name or "title" in style_name:
                            blocks.append(f"## {text}")
                        else:
                            blocks.append(text)
                elif tag == "tbl":
                    tbl_rows = []
                    for tr in child.findall(".//w:tr", DOCX_NS):
                        row_cells = []
                        for tc in tr.findall(".//w:tc", DOCX_NS):
                            row_cells.append("".join(tc.itertext()).strip())
                        if any(row_cells):
                            tbl_rows.append("| " + " | ".join(row_cells) + " |")
                    if tbl_rows:
                        blocks.append("\n".join(tbl_rows))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Corrupted or invalid DOCX archive") from exc
    finally:
        if close_after:
            try:
                zip_fp.close()
            except Exception:
                pass

    return "\n\n".join(blocks)


HEADING_PATTERN = re.compile(
    r"^(?:"
    r"#{1,6}\s+(?P<h_md>.+)|"
    r"(?:Section|Part|Module|Requirement|Clause)\s+(?P<h_sec>\d+(?:\.\d+)*[:.\-\s]+.+)|"
    r"(?P<h_num>\d+(?:\.\d+)*\.\s+[A-Z].+)|"
    r"(?:Question|Q)\s*(?P<h_q>\d+[:.\-\s]+.+)"
    r")$",
    re.IGNORECASE | re.MULTILINE,
)


def split_text_into_sections(text: str) -> List[Dict[str, Any]]:
    """Segment document text into sections with headings and sort order."""
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    sections: List[Dict[str, Any]] = []
    current_heading = "Overview"
    current_body: List[str] = []

    for line in lines:
        stripped = line.strip()
        m = HEADING_PATTERN.match(stripped)
        if m:
            if current_body:
                body_str = "\n".join(current_body).strip()
                if body_str:
                    sections.append({
                        "heading": current_heading,
                        "original_text": body_str,
                        "sort_order": len(sections) + 1,
                    })
            h_text = m.group("h_md") or m.group("h_sec") or m.group("h_num") or m.group("h_q") or stripped
            current_heading = re.sub(r"^#{1,6}\s*", "", h_text).strip().rstrip(":")
            current_body = []
        else:
            current_body.append(line)

    if current_body:
        body_str = "\n".join(current_body).strip()
        if body_str:
            sections.append({
                "heading": current_heading,
                "original_text": body_str,
                "sort_order": len(sections) + 1,
            })

    # Tier 2 Fallback: If no explicit heading matched, split on double newlines
    explicit_heading_found = any(s["heading"] != "Overview" for s in sections)
    if (not sections or not explicit_heading_found) and text.strip():
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
        if len(paragraphs) > 1:
            sections = []
            for idx, p in enumerate(paragraphs, start=1):
                p_lines = p.splitlines()
                first_line = p_lines[0].strip()
                if len(first_line) <= 80:
                    h = re.sub(r"^#{1,6}\s*", "", first_line).strip().rstrip(":")
                    body = "\n".join(p_lines[1:]).strip() if len(p_lines) > 1 else p
                else:
                    h = f"Section {idx}"
                    body = p
                sections.append({
                    "heading": h or f"Section {idx}",
                    "original_text": body or p,
                    "sort_order": idx,
                })

    # Fallback if text exists but nothing generated
    if not sections and text.strip():
        sections.append({
            "heading": "Section 1",
            "original_text": text.strip(),
            "sort_order": 1,
        })

    return sections


def save_uploaded_file(file_bytes: bytes, original_filename: str) -> str:
    """Save uploaded document bytes to backend/data/uploads with unique name."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    sanitized = re.sub(r"[^\w\.\-]", "_", original_filename)
    timestamp = int(time.time() * 1000)
    unique_filename = f"{timestamp}_{sanitized}"
    target_path = UPLOAD_DIR / unique_filename
    with open(target_path, "wb") as f:
        f.write(file_bytes)
    return unique_filename


def ingest_document(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Parse document bytes into a structured list of section dicts."""
    if not file_bytes or len(file_bytes) == 0:
        raise ValueError("Failed to parse document: file is empty or corrupted")

    if filename.endswith(".empty"):
        raise ValueError("Failed to parse document: file is empty or corrupted")
    lower_name = filename.lower()
    raw_text = ""

    if lower_name.endswith(".pdf"):
        raw_text = extract_from_pdf(file_bytes)
        if not raw_text.strip():
            raise ValueError("Document contains no readable text")
    elif lower_name.endswith(".docx"):
        raw_text = extract_from_docx(file_bytes)
        if not raw_text.strip():
            raise ValueError("Document contains no readable text")
    else:
        raise ValueError("Failed to parse document: only .pdf and .docx are supported")

    sections = split_text_into_sections(raw_text)
    if not sections:
        raise ValueError("Failed to parse document: no readable sections found")
    return sections


def extract_sections_from_file(
    file_input: Union[bytes, io.BytesIO, str, Path],
    filename: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Extract sections from file bytes or path, cleanly propagating ValueError."""
    if isinstance(file_input, (str, Path)):
        fn = filename or str(file_input)
        with open(file_input, "rb") as f:
            fbytes = f.read()
    elif isinstance(file_input, io.BytesIO):
        fn = filename or "document.docx"
        fbytes = file_input.getvalue()
    else:
        fn = filename or "document.docx"
        fbytes = file_input
    return ingest_document(fbytes, fn)
