"""Google Docs Export Service (F23, F24).

Implements:
1. Dual Google API specification:
   - Google Docs API v1 (documents.batchUpdate) for Document Title, Subtitle,
     HEADING_1 for sections, and NORMAL_TEXT for draft body with forward character index tracking.
   - Google Drive API v3 (files.comments.create) for anchoring comments on
     unresolved open questions ([MORE INFO REQUIRED]).
2. Markdown-to-Google-Docs converter:
   - Parses Markdown headings (##, ###), bold (**), italic (*/_), bullet lists (- / *)
   - Generates proper batchUpdate requests with updateTextStyle and updateParagraphStyle
3. Mock / Dry-run Mode (Default):
   - Logs structured export payload to backend/logs/google_export.log.
   - Generates simulated URL: https://docs.google.com/document/d/mock-rfp-{id}-{timestamp}/edit.
   - Persists final_doc_link but does NOT auto-advance rfps.status.
4. Live Mode Error Contract:
   - Returns 400 with both 'detail' and 'error' keys if credentials.json is missing.
"""

import json
import os
import re as _re
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Markdown → Google Docs batchUpdate converter
# ---------------------------------------------------------------------------

def _parse_markdown_body(
    raw_md: str,
    start_index: int,
) -> Tuple[str, List[Dict[str, Any]], int]:
    """Convert a Markdown string into plain text + Google Docs formatting requests.

    Returns:
        (plain_text, formatting_requests, end_index)
        - plain_text: the flattened text to insertText at *start_index*
        - formatting_requests: list of updateParagraphStyle / updateTextStyle requests
        - end_index: the character index immediately after the inserted text
    """
    lines = raw_md.split("\n")
    plain_parts: List[str] = []
    para_styles: List[Dict[str, Any]] = []  # paragraph-level (headings, bullets)
    char_styles: List[Dict[str, Any]] = []  # character-level (bold, italic)

    cursor = start_index  # tracks position within the final plain text

    for line in lines:
        stripped = line.rstrip()

        # --- Heading detection (## / ###) ---
        heading_style: Optional[str] = None
        if stripped.startswith("### "):
            heading_style = "HEADING_3"
            stripped = stripped[4:]
        elif stripped.startswith("## "):
            heading_style = "HEADING_2"
            stripped = stripped[3:]

        # --- Bullet detection (- item / * item but not **bold**) ---
        is_bullet = False
        if _re.match(r"^[-*]\s+", stripped) and not stripped.startswith("**"):
            is_bullet = True
            stripped = _re.sub(r"^[-*]\s+", "", stripped)

        # --- Inline formatting: extract bold/italic spans ---
        # We process the line character by character tracking formatting
        inline_text, inline_styles = _extract_inline_formatting(stripped, cursor)
        char_styles.extend(inline_styles)

        line_text = inline_text + "\n"
        line_start = cursor
        line_end = cursor + len(line_text)

        plain_parts.append(line_text)

        if heading_style:
            para_styles.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": line_start, "endIndex": line_end},
                    "paragraphStyle": {"namedStyleType": heading_style},
                    "fields": "namedStyleType",
                }
            })

        if is_bullet:
            para_styles.append({
                "createParagraphBullets": {
                    "range": {"startIndex": line_start, "endIndex": line_end},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            })

        cursor = line_end

    plain_text = "".join(plain_parts)
    # Ensure trailing newline for paragraph separation
    if not plain_text.endswith("\n\n"):
        plain_text += "\n"
        cursor += 1

    formatting_requests = para_styles + char_styles
    return plain_text, formatting_requests, cursor


def _extract_inline_formatting(
    text: str,
    global_offset: int,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Strip Markdown bold/italic markers and return (clean_text, style_requests).

    Handles **bold**, *italic*, and _italic_ patterns.
    Does NOT handle nested bold-italic (***text***) to keep complexity bounded.
    """
    styles: List[Dict[str, Any]] = []
    clean = ""
    i = 0
    n = len(text)

    while i < n:
        # Bold: **...**
        if text[i:i+2] == "**":
            end = text.find("**", i + 2)
            if end != -1:
                inner = text[i+2:end]
                span_start = global_offset + len(clean)
                clean += inner
                span_end = global_offset + len(clean)
                styles.append({
                    "updateTextStyle": {
                        "range": {"startIndex": span_start, "endIndex": span_end},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                })
                i = end + 2
                continue

        # Italic: *...* (single asterisk, not preceded by another *)
        if text[i] == "*" and (i == 0 or text[i-1] != "*") and (i+1 < n and text[i+1] != "*"):
            end = text.find("*", i + 1)
            if end != -1 and (end + 1 >= n or text[end+1] != "*"):
                inner = text[i+1:end]
                span_start = global_offset + len(clean)
                clean += inner
                span_end = global_offset + len(clean)
                styles.append({
                    "updateTextStyle": {
                        "range": {"startIndex": span_start, "endIndex": span_end},
                        "textStyle": {"italic": True},
                        "fields": "italic",
                    }
                })
                i = end + 1
                continue

        # Italic: _..._ (underscore variant)
        if text[i] == "_" and (i + 1 < n) and text[i+1] != "_":
            end = text.find("_", i + 1)
            if end != -1:
                inner = text[i+1:end]
                span_start = global_offset + len(clean)
                clean += inner
                span_end = global_offset + len(clean)
                styles.append({
                    "updateTextStyle": {
                        "range": {"startIndex": span_start, "endIndex": span_end},
                        "textStyle": {"italic": True},
                        "fields": "italic",
                    }
                })
                i = end + 1
                continue

        clean += text[i]
        i += 1

    return clean, styles


def build_export_payload(
    rfp_row: sqlite3.Row,
    sections: List[sqlite3.Row],
    open_questions: List[sqlite3.Row],
    services_names: List[str],
) -> Tuple[Dict[str, Any], str, str]:
    """Build complete Google Docs v1 batchUpdate and Drive v3 comments payload.

    Returns:
        (payload_dict, doc_id, doc_url)
    """
    rfp_id = rfp_row["id"]
    client_name = rfp_row["client_name"]
    doc_id = f"mock-rfp-{rfp_id}-{int(time.time())}"
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

    requests: List[Dict[str, Any]] = []
    current_idx = 1
    section_bounds: Dict[int, Dict[str, Any]] = {}

    # 1. Document Title
    title_text = f"RFP Response — {client_name}\n"
    requests.append({
        "insertText": {
            "location": {"index": current_idx},
            "text": title_text,
        }
    })
    requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": current_idx, "endIndex": current_idx + len(title_text)},
            "paragraphStyle": {"namedStyleType": "TITLE"},
            "fields": "namedStyleType",
        }
    })
    current_idx += len(title_text)

    # 2. Metadata / Subtitle Block
    val_raw = rfp_row["value"]
    val_str = f"£{float(val_raw):,.2f}" if val_raw is not None else "N/A"
    date_str = rfp_row["date_submitted"] or "Draft"
    svc_str = ", ".join(services_names) if services_names else "General"
    meta_text = f"Client: {client_name} | Est. Value: {val_str} | Date: {date_str} | Services: {svc_str}\n\n"
    requests.append({
        "insertText": {
            "location": {"index": current_idx},
            "text": meta_text,
        }
    })
    requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": current_idx, "endIndex": current_idx + len(meta_text)},
            "paragraphStyle": {"namedStyleType": "SUBTITLE"},
            "fields": "namedStyleType",
        }
    })
    current_idx += len(meta_text)

    # 3. Sections
    for s in sections:
        sec_id = s["id"]
        h_start = current_idx
        heading_text = f"{s['heading']}\n"
        requests.append({
            "insertText": {
                "location": {"index": current_idx},
                "text": heading_text,
            }
        })
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": current_idx, "endIndex": current_idx + len(heading_text)},
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                "fields": "namedStyleType",
            }
        })
        current_idx += len(heading_text)

        b_start = current_idx
        body_content = s["final_content"] or s["draft_content"] or "[Draft Pending]"

        # Convert Markdown → plain text + formatting requests
        body_plain, body_fmt_reqs, current_idx = _parse_markdown_body(body_content, current_idx)

        requests.append({
            "insertText": {
                "location": {"index": b_start},
                "text": body_plain,
            }
        })
        # Apply formatting requests generated by the Markdown parser
        requests.extend(body_fmt_reqs)

        section_bounds[sec_id] = {
            "heading_start": h_start,
            "heading_len": len(s["heading"]),
            "heading_text": s["heading"],
            "body_start": b_start,
            "body_text": body_plain,  # use converted plain text for anchor offsets
        }

    # 4. Open Questions Anchored Comments (Google Drive API v3)
    comments: List[Dict[str, Any]] = []
    for q in open_questions:
        if q["status"] != "open":
            continue

        sec_id = q["section_id"]
        q_text = q["question"]
        bounds = section_bounds.get(sec_id)

        if bounds:
            body_txt = bounds["body_text"]
            # Look for specific gap marker or general gap marker in body
            marker_str = f"[MORE INFO REQUIRED: {q_text}]"
            m_idx = body_txt.find(marker_str)
            if m_idx == -1:
                marker_str = "[MORE INFO REQUIRED"
                m_idx = body_txt.find(marker_str)

            if m_idx != -1:
                m_end = body_txt.find("]", m_idx)
                gap_marker = body_txt[m_idx : m_end + 1] if m_end != -1 else body_txt[m_idx : m_idx + 40]
                anchor_start = bounds["body_start"] + m_idx
                anchor_len = len(gap_marker)
                quoted_value = gap_marker
            else:
                anchor_start = bounds["heading_start"]
                anchor_len = bounds["heading_len"]
                quoted_value = bounds.get("heading_text", "")
        else:
            anchor_start = 1
            anchor_len = len(title_text.strip())
            quoted_value = title_text.strip()

        comment_payload = {
            "content": f"[MORE INFO REQUIRED] {q_text}",
            "quotedFileContent": {
                "mimeType": "text/plain",
                "value": quoted_value,
            },
            "anchor": json.dumps({
                "r": "head",
                "a": [{
                    "txt": {
                        "o": anchor_start,
                        "l": anchor_len,
                    }
                }],
            }),
        }

        comments.append({
            "section_id": sec_id,
            "question": q_text,
            "comment_payload": comment_payload,
        })

    payload = {
        "create_document": {"title": f"RFP Response — {client_name}"},
        "batch_update": {"requests": requests},
        "comments": comments,
    }

    return payload, doc_id, doc_url


def log_export_payload(rfp_id: int, mode: str, doc_url: str, payload: Dict[str, Any]) -> None:
    """Write export audit log entry to backend/logs/google_export.log."""
    logs_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "google_export.log"

    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rfp_id": rfp_id,
        "mode": mode,
        "doc_url": doc_url,
        "requests_count": len(payload.get("batch_update", {}).get("requests", [])),
        "comments_count": len(payload.get("comments", [])),
        "payload": payload,
    }

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")


def execute_export(
    conn: sqlite3.Connection,
    rfp_id: int,
    override_mode: Optional[str] = None,
) -> Any:
    """Coordinate Google Docs export execution in mock or live mode."""
    # 1. Fetch RFP record
    cur = conn.execute("SELECT * FROM rfps WHERE id = ?;", (rfp_id,))
    rfp = cur.fetchone()
    if not rfp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFP not found")

    # 2. Fetch Settings
    cur_set = conn.execute("SELECT * FROM settings WHERE id = 1;")
    settings_row = cur_set.fetchone()
    if not settings_row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Settings not configured")

    mode = override_mode or ("mock" if settings_row["mock_google_export"] else "live")

    # 3. Handle Live Mode Validation
    if mode == "live":
        cred_path = settings_row["google_credentials_path"] or "credentials.json"
        resolved_cred = cred_path
        if not os.path.isabs(resolved_cred):
            base_dir = Path(__file__).resolve().parent.parent.parent
            resolved_cred = str(base_dir / cred_path)

        target_file = cred_path if os.path.exists(cred_path) else (resolved_cred if os.path.exists(resolved_cred) else None)
        is_placeholder = False
        if target_file:
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "YOUR_CLIENT_ID" in content or "YOUR_CLIENT_SECRET" in content:
                        is_placeholder = True
            except Exception:
                pass

        if not target_file or is_placeholder:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": f"Google Docs credentials not found or placeholder credentials.json detected at '{cred_path}'. Ensure valid credentials exist or switch to Mock Mode in Settings.",
                    "detail": f"Google Docs credentials not found at '{cred_path}'. Ensure valid credentials.json exists or switch to Mock Mode in Settings.",
                },
            )

    # 4. Fetch Sections, Services, and Open Questions
    cur_sec = conn.execute(
        "SELECT * FROM rfp_sections WHERE rfp_id = ? ORDER BY sort_order ASC, id ASC;",
        (rfp_id,),
    )
    sections = cur_sec.fetchall()

    cur_svc = conn.execute(
        """
        SELECT s.name FROM services s
        JOIN rfp_services rs ON rs.service_id = s.id
        WHERE rs.rfp_id = ?
        ORDER BY s.name ASC;
        """,
        (rfp_id,),
    )
    services_names = [r["name"] for r in cur_svc.fetchall()]

    cur_oq = conn.execute(
        "SELECT * FROM open_questions WHERE rfp_id = ? AND status = 'open' ORDER BY id ASC;",
        (rfp_id,),
    )
    open_questions = cur_oq.fetchall()

    # 5. Build Payload
    payload, doc_id, doc_url = build_export_payload(
        rfp_row=rfp,
        sections=sections,
        open_questions=open_questions,
        services_names=services_names,
    )

    # 6. Mock vs Live Execution
    if mode == "mock":
        log_export_payload(rfp_id=rfp_id, mode="mock", doc_url=doc_url, payload=payload)

        # Persist final_doc_link only — mock export should NOT mutate RFP status
        conn.execute(
            "UPDATE rfps SET final_doc_link = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
            (doc_url, rfp_id),
        )
        conn.commit()

        return {
            "success": True,
            "mode": "mock",
            "doc_id": doc_id,
            "doc_url": doc_url,
            "payload": payload,
        }

    # Live Mode Execution (when credentials exist)
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Google API client libraries (google-api-python-client, google-auth) are not installed in the environment.",
                "detail": "Google API client libraries not installed. Run: pip install google-api-python-client google-auth-oauthlib",
            },
        )

    try:
        SCOPES = [
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive",
        ]
        resolved_cred = target_file
        creds = None
        # Attempt loading authorized user file if valid tokens are present
        try:
            creds = Credentials.from_authorized_user_file(resolved_cred, SCOPES)
        except Exception:
            # Fall back to client secrets OAuth flow
            flow = InstalledAppFlow.from_client_secrets_file(resolved_cred, SCOPES)
            creds = flow.run_local_server(port=0)

        docs_service = build("docs", "v1", credentials=creds)
        drive_service = build("drive", "v3", credentials=creds)

        # 1. Create Document via Google Docs API v1
        doc = docs_service.documents().create(body=payload["create_document"]).execute()
        real_doc_id = doc.get("documentId")
        real_doc_url = f"https://docs.google.com/document/d/{real_doc_id}/edit"

        # 2. Populate Structure & Headings via batchUpdate
        docs_service.documents().batchUpdate(
            documentId=real_doc_id,
            body=payload["batch_update"],
        ).execute()

        # 3. Insert Anchored Comments via Google Drive API v3
        for comment_item in payload.get("comments", []):
            drive_service.comments().create(
                fileId=real_doc_id,
                body=comment_item["comment_payload"],
                fields="id,content,anchor",
            ).execute()

        log_export_payload(rfp_id=rfp_id, mode="live", doc_url=real_doc_url, payload=payload)

        # 4. Persist in Database and advance status
        conn.execute(
            "UPDATE rfps SET final_doc_link = ?, status = 'submitted', updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
            (real_doc_url, rfp_id),
        )
        conn.commit()

        return {
            "success": True,
            "mode": "live",
            "doc_id": real_doc_id,
            "doc_url": real_doc_url,
            "payload": payload,
        }
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": f"Live Google export failed: {str(exc)}",
                "detail": f"Live Google export failed: {str(exc)}",
            },
        )
