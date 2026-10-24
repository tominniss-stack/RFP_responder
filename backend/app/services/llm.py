"""Multi-provider LLM client and RFP section classification engine.

Supports:
1. Anthropic Claude (/v1/messages)
2. Google Gemini (/v1beta/models/{model}:generateContent)
3. A deterministic keyword-matching mock engine for offline use and tests.

Engine selection is explicit and never silent: when a live provider is configured
and fails, the error is raised as `LLMProviderError` so callers can surface it
rather than quietly substituting mock output. The engine actually used is always
reported alongside the result via `call_model_with_meta()`.
"""

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Literal, Optional, Tuple
import urllib.error
import urllib.request

from app.database import get_db_connection
from app.models import AGENCY_NAME, DEFAULT_CLASSIFICATION_MODEL, DEFAULT_GENERATION_MODEL


class LLMProviderError(RuntimeError):
    """Raised when a configured live provider call fails."""

    def __init__(self, provider: str, model: str, detail: str):
        self.provider = provider
        self.model = model
        self.detail = detail
        super().__init__(f"{provider} ({model}) request failed: {detail}")


MOCK_MODEL_NAME = "mock-deterministic"

CLASSIFICATION_SYSTEM_PROMPT = """You are analysing a Request for Proposal (RFP) document that has been split into
its constituent sections/questions. For each section, classify it into exactly
one of the following categories:

- BOILERPLATE: Can be answered using standard company information (who we are,
  team bios, certifications, insurance, past case studies, general methodology).
- PRICING: Requires cost/rate/budget figures.
- STRATEGIC_DECISION: Requires a judgment call about approach, technology, or
  methodology that isn't a fixed company fact — e.g. choice of platform,
  build vs. buy, staffing model, timeline trade-offs. This is NOT something
  that can be answered from past documents alone, because the "right" answer
  depends on this specific project.
- GAP: Requires specific factual/experience information that may not exist in
  our knowledge base (e.g. "describe your experience in [niche sector]").
- COMPLIANCE_ADMIN: Formalities — signatures, declarations, submission checklists.

For each section, also:
1. Extract the exact question/requirement text as written.
2. If STRATEGIC_DECISION, draft ONE short, specific question we should ask our
   internal team to resolve it, and suggest a default answer if a similar
   decision appears in past proposals provided in context.
3. Rate confidence (high/medium/low) in your classification.

Output valid JSON only, in this schema:
[
  {
    "section_id": "",
    "heading": "",
    "original_text": "",
    "classification": "",
    "confidence": "",
    "clarifying_question": "",
    "suggested_default": ""
  }
]"""


def mock_classify_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic keyword-matching classifier mirroring the LLM output schema."""
    results = []

    for idx, s in enumerate(sections, start=1):
        sec_id = s.get("id") or s.get("section_id") or idx
        heading = s.get("heading", f"Section {idx}")
        orig_text = s.get("original_text", "")
        htext = f"{heading} {orig_text}".lower()

        # 1. Ambiguous Section Edge Case (blending strategy approach + experience gap)
        if "accessibility" in htext or ("wcag" in htext and "experience" in htext):
            cat = "strategic_decision"
            conf = "medium"
            cq = "What specific WCAG conformance level (AA vs AAA) and automated testing suite is required?"
            sd = "Propose WCAG 2.2 AA standard compliance with axe DevTools automated scans."

        # 2. Pricing
        elif any(
            bool(re.search(r"\brates?\b", htext)) if k == "rate" else (k in htext)
            for k in ["price", "pricing", "day rate", "hourly rate", "rate", "cost", "budget", "fee", "commercial", "quote", "financial"]
        ):
            cat = "pricing"
            conf = "high"
            cq = ""
            sd = ""

        # 3. Strategic Decision
        elif any(k in htext for k in ["cms", "platform", "build vs buy", "build vs. buy", "technical approach", "architecture", "stack", "recommendation", "strategy", "trade-off", "decoupled", "headless"]):
            cat = "strategic_decision"
            conf = "high"
            cq = f"Which CMS and front-end rendering approach should we propose for {heading}?"
            sd = "Recommend a headless CMS with a statically rendered front end for speed and compliance."

        # 4. Information Gap
        elif any(k in htext for k in ["public health", "nhs", "telemetry", "experience in", "case study in", "case studies in", "past experience with", "track record in", "niche", "specialist"]):
            cat = "gap"
            conf = "low" if ("public health" in htext or "nhs" in htext) else "medium"
            cq = f"Do we have verified case studies or credentials for: {heading}?"
            sd = "Highlight data compliance frameworks and consult relevant team lead for past sector work."

        # 5. Compliance / Admin
        elif any(k in htext for k in ["declaration", "sign-off", "signature", "compliance", "sign", "terms and conditions", "terms", "nda", "checklist", "gdpr", "data protection"]):
            cat = "compliance_admin"
            conf = "high"
            cq = ""
            sd = ""

        # 6. Boilerplate (Default)
        else:
            cat = "boilerplate"
            conf = "high"
            cq = ""
            sd = ""

        results.append({
            "section_id": sec_id,
            "heading": heading,
            "original_text": orig_text,
            "classification": cat,
            "confidence": conf,
            "clarifying_question": cq,
            "suggested_default": sd,
        })

    return results


def call_claude_api(api_key: str, model: str, prompt: str, system_prompt: Optional[str] = None) -> str:
    """Dispatches prompt to Anthropic Claude Messages API."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        payload["system"] = system_prompt

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500] if hasattr(exc, "read") else str(exc)
        raise LLMProviderError("Claude", model, f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMProviderError("Claude", model, str(exc)) from exc
    except ValueError as exc:
        raise LLMProviderError("Claude", model, f"invalid JSON response: {exc}") from exc

    content = body.get("content", [])
    if content and isinstance(content, list) and "text" in content[0]:
        return content[0]["text"]
    raise LLMProviderError("Claude", model, "response contained no text content")


def call_gemini_api(api_key: str, model: str, prompt: str, system_prompt: Optional[str] = None) -> str:
    """Dispatches prompt to Google Gemini generateContent API."""
    clean_model = model.replace("models/", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    contents = [{"parts": [{"text": prompt}]}]
    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": 0.2},
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500] if hasattr(exc, "read") else str(exc)
        raise LLMProviderError("Gemini", model, f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMProviderError("Gemini", model, str(exc)) from exc
    except ValueError as exc:
        raise LLMProviderError("Gemini", model, f"invalid JSON response: {exc}") from exc

    candidates = body.get("candidates", [])
    if candidates and "content" in candidates[0]:
        parts = candidates[0]["content"].get("parts", [])
        if parts and "text" in parts[0]:
            return parts[0]["text"]
    raise LLMProviderError("Gemini", model, "response contained no text content")


def get_current_settings(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Retrieve settings record from database."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.execute("SELECT * FROM settings WHERE id = 1;")
        row = cur.fetchone()
        if row:
            return dict(row)
        return {}
    finally:
        if close_after:
            conn.close()


def resolve_engine(
    task_type: Literal["classification", "generation"],
    conn: Optional[sqlite3.Connection] = None,
) -> Tuple[str, str, str]:
    """Decide which engine will serve a task.

    Returns (engine, model, api_key) where engine is one of 'mock' | 'claude' | 'gemini'.
    The mock engine is chosen when:
      - MOCK_LLM=1 or TEST_MODE=1 is set in the environment, or
      - the configured model is the explicit mock model, or
      - no API key is configured for the provider implied by the model name.
    """
    if os.environ.get("MOCK_LLM") == "1" or os.environ.get("TEST_MODE") == "1":
        return "mock", MOCK_MODEL_NAME, ""

    settings = get_current_settings(conn)
    default_model = DEFAULT_CLASSIFICATION_MODEL if task_type == "classification" else DEFAULT_GENERATION_MODEL
    key_name = "classification_model" if task_type == "classification" else "generation_model"
    model = (settings.get(key_name) or default_model).strip()
    lowered = model.lower()

    if lowered == MOCK_MODEL_NAME or lowered.startswith("mock"):
        return "mock", MOCK_MODEL_NAME, ""

    claude_key = (settings.get("claude_api_key") or "").strip()
    gemini_key = (settings.get("gemini_api_key") or "").strip()

    if "claude" in lowered and claude_key:
        return "claude", model, claude_key
    if ("gemini" in lowered or "google" in lowered) and gemini_key:
        return "gemini", model, gemini_key
    return "mock", MOCK_MODEL_NAME, ""


def call_model_with_meta(
    task_type: Literal["classification", "generation"],
    prompt: str,
    system_prompt: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Tuple[str, Dict[str, str]]:
    """Dispatch a prompt and return (text, {"engine": ..., "model": ...}).

    Raises LLMProviderError when a live provider is configured but the call fails.
    There is deliberately no silent fallback to mock output in that case.
    """
    engine, model, api_key = resolve_engine(task_type, conn)
    meta = {"engine": engine, "model": model}

    if engine == "claude":
        return call_claude_api(api_key, model, prompt, system_prompt), meta
    if engine == "gemini":
        return call_gemini_api(api_key, model, prompt, system_prompt), meta
    return _mock_dispatch(task_type, prompt, system_prompt=system_prompt), meta


def call_model(
    task_type: Literal["classification", "generation"],
    prompt: str,
    system_prompt: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> str:
    """Single entry point for all LLM calls (text only). See call_model_with_meta()."""
    text, _ = call_model_with_meta(task_type, prompt, system_prompt=system_prompt, conn=conn)
    return text


def _mock_dispatch(
    task_type: str,
    prompt: str,
    system_prompt: Optional[str] = None,
) -> str:
    """Deterministic fallback dispatcher returning compliant strings adhering to Master System Prompt."""
    if task_type == "classification":
        try:
            parsed_sections = json.loads(prompt)
            if isinstance(parsed_sections, list):
                classified = mock_classify_sections(parsed_sections)
                return json.dumps(classified, indent=2)
        except Exception:
            pass
        return json.dumps(mock_classify_sections([{"heading": "Section 1", "original_text": prompt}]))

    # Generation task adhering to the master system prompt rules
    draft_paragraphs: List[str] = []

    # Tone of voice check (e.g. tone prompt instructions propagated dynamically from settings)
    if system_prompt and "executive summary" in system_prompt.lower():
        draft_paragraphs.append(f"Executive Summary: {AGENCY_NAME} delivers verified excellence tailored to this requirement.")

    def _extract_section(header: str) -> Optional[str]:
        pattern = rf"(?:^|\n){re.escape(header)}\n(.*?)(?=\n[A-Z0-9 _-]+:|\Z)"
        m = re.search(pattern, prompt, re.DOTALL)
        return m.group(1).strip() if m else None

    sec_block = _extract_section("RFP SECTION TO DRAFT:")
    heading = "this requirement"
    req_text = ""
    classification = "boilerplate"
    if sec_block:
        hm = re.search(r"Heading:\s*(.+)", sec_block)
        if hm:
            heading = hm.group(1).strip()
        rm = re.search(r"Requirement:\s*(.+)", sec_block)
        if rm:
            req_text = rm.group(1).strip()
        cm = re.search(r"Classification:\s*([A-Z_]+)", sec_block)
        if cm:
            classification = cm.group(1).strip().lower()

    rag_block = _extract_section("RETRIEVED REFERENCE MATERIAL (RAG):")
    pricing_block = _extract_section("STRUCTURED PRICING DATA:")
    boilerplate_block = _extract_section("BOILERPLATE COMPANY INFORMATION:")
    notes_block = _extract_section("ACCOUNT MANAGER NOTES & RESOLUTIONS:")

    # 1. Pricing block handling (Rule 2: exact numbers, zero hallucination)
    if pricing_block:
        if "[MORE INFO REQUIRED:" in pricing_block:
            draft_paragraphs.append("[MORE INFO REQUIRED: Missing pricing data for requested services]")
        else:
            draft_paragraphs.append(pricing_block)

    # 2. Boilerplate block handling (Rule 1 & Rule 3)
    if boilerplate_block:
        if "[MORE INFO REQUIRED:" in boilerplate_block:
            draft_paragraphs.append("[MORE INFO REQUIRED: Company background and boilerplate not found in knowledge base]")
        else:
            draft_paragraphs.append(boilerplate_block)

    # 3. RAG reference material handling (Rule 1 & Rule 3)
    if rag_block:
        has_resolution = notes_block and ("Resolved Open Question" in notes_block or "resolution" in notes_block.lower())
        if "[MORE INFO REQUIRED:" in rag_block and not has_resolution:
            draft_paragraphs.append(
                f"We acknowledge the requirement for {heading}: {req_text}. "
                f"[MORE INFO REQUIRED: Describe specific past experience and evidence for {heading}]"
            )
        elif "[MORE INFO REQUIRED:" not in rag_block:
            draft_paragraphs.append(
                f"Our technical methodology for {heading} addresses the requirement ({req_text}): {rag_block}"
            )

    # 4. Account Manager Notes and Open Question Resolutions handling (Rule 1 & Rule 3)
    if notes_block:
        for line in notes_block.splitlines():
            line = line.strip()
            if not line:
                continue
            if "Resolved Open Question" in line:
                m_res = re.match(r"Resolved Open Question\s*#?\d*:\s*(.+)", line, re.IGNORECASE)
                res_val = m_res.group(1).strip() if m_res else line
                draft_paragraphs.append(f"Regarding {heading}: {res_val}")
            elif "Section Note:" in line:
                m_sn = re.match(r"Section Note:\s*(.+)", line, re.IGNORECASE)
                val = m_sn.group(1).strip() if m_sn else line
                if classification == "pricing":
                    draft_paragraphs.append(f"Commercial terms note: {val}")
                elif classification == "boilerplate":
                    draft_paragraphs.append(f"Delivery instruction: {val}")
                elif classification == "gap":
                    draft_paragraphs.append(f"Special requirement note: {val}")
                else:
                    draft_paragraphs.append(f"Tailored delivery instruction: {val}")
            elif "Whole-RFP Note:" in line:
                m_wn = re.match(r"(?:Account Manager )?Whole-RFP Note:\s*(.+)", line, re.IGNORECASE)
                val = m_wn.group(1).strip() if m_wn else line
                if classification == "pricing":
                    draft_paragraphs.append(f"Commercial context: {val}")
                elif classification == "boilerplate":
                    draft_paragraphs.append(f"Company context: {val}")
                elif classification == "gap":
                    draft_paragraphs.append(f"Context note: {val}")
                else:
                    draft_paragraphs.append(f"Strategic context: {val}")
            else:
                draft_paragraphs.append(line)

    # 5. Fallback if no specific blocks were extracted (e.g. arbitrary prompt)
    if not draft_paragraphs or (len(draft_paragraphs) == 1 and draft_paragraphs[0].startswith("Executive Summary:")):
        if "[MORE INFO REQUIRED:" in prompt:
            m_gap = re.search(r"\[MORE INFO REQUIRED:[^\]]+\]", prompt)
            gap_marker = m_gap.group(0) if m_gap else "[MORE INFO REQUIRED: Additional project information required]"
            draft_paragraphs.append(f"We understand the requirement for this section. {gap_marker}")
        else:
            draft_paragraphs.append("Draft response generated based on reference material and agency guidelines.")

    return "\n\n".join(draft_paragraphs)


def clean_json_response(raw_response: str) -> List[Dict[str, Any]]:
    """Extract and parse JSON array from model output, stripping Markdown code fences."""
    cleaned = raw_response.strip()
    # Strip ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    # Locate array brackets if surrounding text exists
    first_bracket = cleaned.find("[")
    last_bracket = cleaned.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        cleaned = cleaned[first_bracket:last_bracket + 1]

    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        raise ValueError("Classification response must be a JSON array")
    return parsed


def classify_rfp_sections_with_meta(
    sections: List[Dict[str, Any]],
    conn: Optional[sqlite3.Connection] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Classify RFP sections and report which engine produced the result.

    Live provider failures propagate as LLMProviderError. A malformed-but-successful
    provider response (unparseable JSON) falls back to the deterministic classifier
    and is reported as engine='mock' with the attempted model recorded under 'fallback_from'.
    """
    if not sections:
        return [], {"engine": "mock", "model": MOCK_MODEL_NAME}

    # Prepare minimal representation for LLM prompt
    minimal_sections = [
        {
            "section_id": s.get("id") or s.get("section_id") or idx + 1,
            "heading": s.get("heading", f"Section {idx + 1}"),
            "original_text": s.get("original_text", ""),
        }
        for idx, s in enumerate(sections)
    ]

    prompt_json = json.dumps(minimal_sections, indent=2)

    raw_output, meta = call_model_with_meta(
        task_type="classification",
        prompt=prompt_json,
        system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
        conn=conn,
    )

    try:
        parsed_results = clean_json_response(raw_output)

        # Normalize outputs to conform to SQLite constraints
        normalized = []
        for item in parsed_results:
            raw_cat = str(item.get("classification", "boilerplate")).lower().strip().replace(" ", "_")
            if raw_cat not in ["boilerplate", "pricing", "strategic_decision", "strategic", "gap", "compliance_admin"]:
                raw_cat = "boilerplate"
            raw_conf = str(item.get("confidence", "high")).lower().strip()
            if raw_conf not in ["high", "medium", "low"]:
                raw_conf = "high"

            normalized.append({
                "section_id": item.get("section_id"),
                "heading": item.get("heading", ""),
                "original_text": item.get("original_text", ""),
                "classification": raw_cat,
                "confidence": raw_conf,
                "clarifying_question": item.get("clarifying_question") or None,
                "suggested_default": item.get("suggested_default") or None,
            })
        return normalized, meta

    except (ValueError, json.JSONDecodeError, AttributeError, TypeError):
        # Provider answered but not with the required JSON schema — degrade visibly.
        fallback_meta = {"engine": "mock", "model": MOCK_MODEL_NAME, "fallback_from": meta.get("model", "")}
        return mock_classify_sections(minimal_sections), fallback_meta


def classify_rfp_sections(
    sections: List[Dict[str, Any]],
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Classify RFP sections (results only). See classify_rfp_sections_with_meta()."""
    results, _ = classify_rfp_sections_with_meta(sections, conn=conn)
    return results
