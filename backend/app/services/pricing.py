"""Deterministic Pricing Injection Engine (F14, F15).

Guarantees exact mathematical reproduction of structured pricing figures in drafts
without estimation, rounding, or LLM paraphrasing.
"""

import re
import sqlite3
from typing import Any, Dict, List, Optional


def get_pricing_for_rfp(
    conn: sqlite3.Connection,
    rfp_id: int,
    section_text: str = "",
) -> List[Dict[str, Any]]:
    """Retrieve structured price items associated with an RFP's services.

    Deterministic by design — pricing is never guessed:
    1. If the RFP has linked services, return the price items for those services.
    2. If linked services exist but have no price items, return [] (the draft gets a gap marker).
    3. If the RFP has NO linked services, return [] — the account manager must tag the
       RFP with services before pricing can be injected. `section_text` is accepted for
       API compatibility but intentionally not used for fuzzy matching.
    """
    cur_count = conn.execute(
        "SELECT COUNT(*) FROM rfp_services WHERE rfp_id = ?;",
        (rfp_id,),
    )
    has_linked = cur_count.fetchone()[0] > 0

    if has_linked:
        cursor = conn.execute(
            """
            SELECT p.id, p.service_id, s.name AS service_name, p.description, p.unit, p.amount
            FROM price_items p
            JOIN rfp_services rs ON rs.service_id = p.service_id
            LEFT JOIN services s ON s.id = p.service_id
            WHERE rs.rfp_id = ?
            ORDER BY p.id ASC;
            """,
            (rfp_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    return []


def format_pricing_schedule(prices: List[Dict[str, Any]]) -> str:
    """Format price items into exact deterministic Markdown schedule.
    
    Ensures exact numeric reproduction: e.g. £850.00 (day rate), £16,500.00 (fixed).
    """
    lines = ["Our commercial quotation is structured deterministically as follows:"]
    for p in prices:
        amount = float(p["amount"])
        formatted_amount = f"£{amount:,.2f}"
        lines.append(f"- {p['description']}: {formatted_amount} ({p['unit']})")
    return "\n".join(lines)


def generate_pricing_draft(
    conn: sqlite3.Connection,
    rfp_id: int,
    section_id: int,
) -> Dict[str, Any]:
    """Deterministically assemble section draft for pricing classification."""
    cur = conn.execute("SELECT * FROM rfp_sections WHERE id = ?;", (section_id,))
    section = cur.fetchone()
    if not section:
        raise ValueError(f"Section {section_id} not found")

    draft_paragraphs = []
    provenance = []

    # Pricing lookup
    prices = get_pricing_for_rfp(conn, rfp_id, section["original_text"])
    if prices:
        draft_paragraphs.append(format_pricing_schedule(prices))
        provenance.append({"source": "pricing", "text": "commercial quotation"})
    else:
        # Strict zero-hallucination gap marker
        draft_paragraphs.append("[MORE INFO REQUIRED: Missing pricing data for requested services]")
        provenance.append({"source": "gap", "text": "missing pricing"})

    # Incorporate Account Manager commercial notes
    cur_sec_notes = conn.execute(
        "SELECT raw_content FROM rfp_notes WHERE rfp_id = ? AND section_id = ? ORDER BY id ASC;",
        (rfp_id, section_id),
    )
    sec_notes = cur_sec_notes.fetchall()

    cur_whole_notes = conn.execute(
        "SELECT raw_content FROM rfp_notes WHERE rfp_id = ? AND section_id IS NULL ORDER BY id ASC;",
        (rfp_id,),
    )
    whole_notes = cur_whole_notes.fetchall()

    # Incorporate RFP commercial terms & discount instructions
    cur_rfp = conn.execute(
        "SELECT client_name, value, budget_type, budget_notes FROM rfps WHERE id = ?;",
        (rfp_id,),
    )
    rfp_row = cur_rfp.fetchone()
    if rfp_row and rfp_row["budget_notes"]:
        draft_paragraphs.append(f"Commercial discount / terms: {rfp_row['budget_notes']}")
        provenance.append({"source": "notes", "text": rfp_row["budget_notes"]})

    if sec_notes:
        note_text = sec_notes[0]["raw_content"]
        draft_paragraphs.append(f"Commercial terms note: {note_text}")
        provenance.append({"source": "notes", "text": note_text})
    elif whole_notes:
        note_text = whole_notes[0]["raw_content"]
        draft_paragraphs.append(f"Commercial context: {note_text}")
        provenance.append({"source": "notes", "text": note_text})

    final_draft = "\n\n".join(draft_paragraphs)

    # Gap marker auto-registration for open questions
    markers = re.findall(r"\[MORE INFO REQUIRED:\s*([^\]]+)\]", final_draft)
    for m in markers:
        cur_q = conn.execute(
            "SELECT id FROM open_questions WHERE section_id = ? AND question = ?;",
            (section_id, m),
        )
        if not cur_q.fetchone():
            conn.execute(
                "INSERT INTO open_questions (rfp_id, section_id, question, status) VALUES (?, ?, ?, 'open');",
                (rfp_id, section_id, m),
            )

    status = "resolved" if not markers else "drafted"
    conn.execute(
        "UPDATE rfp_sections SET draft_content = ?, status = ? WHERE id = ?;",
        (final_draft, status, section_id),
    )
    conn.commit()

    return {
        "section_id": section_id,
        "draft_content": final_draft,
        "status": status,
        "provenance": provenance,
    }
