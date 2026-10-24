"""Pydantic v2 schemas for data validation and API serialization."""

from typing import List, Optional, Any, Union, Literal, Dict
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Health Schemas
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Application health status")
    version: str = Field(default="1.0.0", description="Application version")
    database: str = Field(default="connected", description="Database connection status")


# ---------------------------------------------------------------------------
# Settings Schemas
# ---------------------------------------------------------------------------

class SettingsBase(BaseModel):
    classification_model: str = Field(
        default="gemini-1.5-flash",
        description="Cheaper/faster model for classification and gap detection"
    )
    generation_model: str = Field(
        default="claude-3-5-sonnet",
        description="Higher-capability model for narrative draft generation"
    )
    claude_api_key: Optional[str] = Field(
        default="",
        description="Anthropic API key"
    )
    gemini_api_key: Optional[str] = Field(
        default="",
        description="Google Gemini API key"
    )
    mock_google_export: bool = Field(
        default=True,
        description="Flag to stub Google Docs export (True = mock mode, False = live mode)"
    )
    google_credentials_path: Optional[str] = Field(
        default="credentials.json",
        description="Path to Google Cloud OAuth credentials JSON file"
    )
    system_prompt: str = Field(
        ...,
        description="Master system prompt for drafting assistant"
    )
    tone_of_voice_prompt: str = Field(
        ...,
        description="Agency house tone-of-voice prompt"
    )
    weight_won: Optional[float] = Field(
        default=1.25,
        description="Retrieval biasing multiplier for won proposals (e.g. 1.25 for +25%)"
    )
    weight_lost: Optional[float] = Field(
        default=0.90,
        description="Retrieval biasing multiplier for lost proposals (e.g. 0.90 for -10%)"
    )
    hubspot_api_key: Optional[str] = Field(
        default="",
        description="HubSpot Private App Access Token or API Key"
    )
    hubspot_portal_id: Optional[str] = Field(
        default="",
        description="HubSpot Portal / Account ID"
    )


class SettingsResponse(SettingsBase):
    id: int = Field(default=1, description="Singleton settings row ID (always 1)")

    model_config = ConfigDict(from_attributes=True)


class SettingsUpdate(BaseModel):
    classification_model: Optional[str] = Field(None, min_length=1)
    generation_model: Optional[str] = Field(None, min_length=1)
    claude_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    mock_google_export: Optional[bool] = None
    google_credentials_path: Optional[str] = None
    system_prompt: Optional[str] = Field(None, min_length=10)
    tone_of_voice_prompt: Optional[str] = Field(None, min_length=10)
    weight_won: Optional[float] = None
    weight_lost: Optional[float] = None
    hubspot_api_key: Optional[str] = None
    hubspot_portal_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Services Schemas
# ---------------------------------------------------------------------------

class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Unique service discipline name")


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(ServiceBase):
    pass


class ServiceResponse(ServiceBase):
    id: int = Field(..., description="Unique service identifier")

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Section Schemas (F06, F09, F10)
# ---------------------------------------------------------------------------

class SectionBase(BaseModel):
    heading: str = Field(..., description="Section heading")
    original_text: str = Field(..., description="Original requirement or prompt text")
    sort_order: int = Field(default=0, description="1-indexed sequence order")


class SectionCreate(SectionBase):
    pass


class SectionUpdate(BaseModel):
    heading: Optional[str] = None
    original_text: Optional[str] = None
    classification: Optional[str] = None
    confidence: Optional[str] = None
    clarifying_question: Optional[str] = None
    suggested_default: Optional[str] = None
    draft_content: Optional[str] = None
    final_content: Optional[str] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None


class SectionResponse(SectionBase):
    id: int
    rfp_id: int
    classification: Optional[str] = None
    confidence: Optional[str] = None
    clarifying_question: Optional[str] = None
    suggested_default: Optional[str] = None
    draft_content: Optional[str] = None
    final_content: Optional[str] = None
    status: str = Field(default="pending")

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Note & Open Question Schemas (F17, F20)
# ---------------------------------------------------------------------------

class NoteCreate(BaseModel):
    raw_content: str = Field(..., min_length=1, description="Note raw text content")
    section_id: Optional[int] = Field(default=None, description="Nullable section ID (None = whole RFP)")

    @field_validator("raw_content")
    @classmethod
    def validate_raw_content_not_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Note content cannot be empty or whitespace")
        return cleaned


class NoteResponse(BaseModel):
    id: int
    rfp_id: int
    section_id: Optional[int] = None
    raw_content: str
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OpenQuestionUpdate(BaseModel):
    resolution: str = Field(..., description="Resolution text resolving the open question")
    status: Optional[Literal["open", "resolved"]] = Field(default="resolved")


class OpenQuestionResponse(BaseModel):
    id: int
    rfp_id: int
    section_id: Optional[int] = None
    question: str
    status: str = Field(default="open")
    resolution: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Provenance & Draft Generation Schemas (F18, F21)
# ---------------------------------------------------------------------------

ProvenanceSource = Literal["notes", "rag", "boilerplate", "pricing", "gap"]


class ProvenanceItem(BaseModel):
    source: ProvenanceSource = Field(..., description="Origin source category")
    text: str = Field(..., description="Excerpt or descriptive snippet from this source")
    reference: str = Field(default="", description="Human-readable citation or reference")


class DraftGenerateResponse(BaseModel):
    section_id: int
    draft_content: str
    status: str
    provenance: List[ProvenanceItem] = Field(default_factory=list)
    engine: Literal["mock", "claude", "gemini"] = Field(
        default="mock", description="Which engine produced the draft — never hidden from the user"
    )
    model: str = Field(default="", description="Model identifier used (or 'mock-deterministic')")


# ---------------------------------------------------------------------------
# RFP Schemas (F01, F06, F07, F26)
# ---------------------------------------------------------------------------

class RFPCreate(BaseModel):
    client_name: str = Field(..., min_length=1, description="Client name")
    value: Optional[float] = Field(default=None, description="Estimated deal value")
    date_submitted: Optional[str] = Field(default=None, description="Submission deadline / date")
    deadline: Optional[str] = Field(default=None, description="Submission deadline date (YYYY-MM-DD)")
    budget_type: Optional[str] = Field(default="fixed", description="Budget type (e.g. fixed, under_budget, unknown, retainer, time_and_materials)")
    budget_notes: Optional[str] = Field(default=None, description="Contextual budget notes")
    raw_details: Optional[str] = Field(default=None, description="Pasted RFP brief, specification, or full requirements text")
    status: Optional[str] = Field(default="draft", description="RFP status")
    services: Optional[List[Union[int, str]]] = Field(default_factory=list, description="List of service IDs")
    service_ids: Optional[List[int]] = Field(default=None, description="Alternative key for service IDs")


class RFPUpdate(BaseModel):
    client_name: Optional[str] = None
    value: Optional[float] = None
    date_submitted: Optional[str] = None
    deadline: Optional[str] = None
    budget_type: Optional[str] = None
    budget_notes: Optional[str] = None
    raw_details: Optional[str] = None
    status: Optional[str] = None
    outcome_feedback: Optional[str] = None
    source_document: Optional[str] = None
    final_doc_link: Optional[str] = None
    hubspot_deal_id: Optional[str] = None
    services: Optional[List[Union[int, str]]] = None
    service_ids: Optional[List[int]] = None


class RFPListItem(BaseModel):
    id: int
    client_name: str
    value: Optional[float] = None
    date_submitted: Optional[str] = None
    deadline: Optional[str] = None
    budget_type: Optional[str] = None
    budget_notes: Optional[str] = None
    status: str = "draft"
    outcome_feedback: Optional[str] = None
    source_document: Optional[str] = None
    final_doc_link: Optional[str] = None
    hubspot_deal_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    services: List[Any] = Field(default_factory=list)
    sections_count: Optional[int] = 0
    open_questions_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class RFPDetailResponse(BaseModel):
    id: int
    client_name: str
    value: Optional[float] = None
    date_submitted: Optional[str] = None
    deadline: Optional[str] = None
    budget_type: Optional[str] = None
    budget_notes: Optional[str] = None
    raw_details: Optional[str] = None
    status: str = "draft"
    outcome_feedback: Optional[str] = None
    source_document: Optional[str] = None
    final_doc_link: Optional[str] = None
    hubspot_deal_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    services: List[Any] = Field(default_factory=list)
    sections: List[SectionResponse] = Field(default_factory=list)
    notes: List[NoteResponse] = Field(default_factory=list)
    open_questions: List[OpenQuestionResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RFPUploadResponse(BaseModel):
    rfp_id: int
    sections_count: int
    client_name: Optional[str] = None
    message: Optional[str] = None
    sections: Optional[List[SectionResponse]] = None


# ---------------------------------------------------------------------------
# Classification Schemas (F08, F09)
# ---------------------------------------------------------------------------

class ClassificationResult(BaseModel):
    section_id: Optional[Union[int, str]] = None
    heading: str
    original_text: Optional[str] = None
    classification: str
    confidence: Optional[str] = "high"
    clarifying_question: Optional[str] = None
    suggested_default: Optional[str] = None


class ClassifyResponse(BaseModel):
    status: str = "ok"
    classified_count: int
    sections: List[ClassificationResult]


# ---------------------------------------------------------------------------
# Knowledge Base Schemas (F11, F12, F13, F16)
# ---------------------------------------------------------------------------

KBType = Literal["past_proposal", "case_study", "testimonial", "pitch_deck", "boilerplate"]
KBOutcome = Literal["won", "lost", "n/a"]


class KBDocumentBase(BaseModel):
    title: str = Field(..., min_length=1, description="Document title")
    content: str = Field(..., min_length=1, description="Document text content")
    type: str = Field(..., description="'past_proposal'|'case_study'|'testimonial'|'pitch_deck'|'boilerplate'")
    outcome: Optional[str] = Field(default="n/a", description="'won'|'lost'|'n/a'")
    service_ids: Optional[List[int]] = Field(default_factory=list, description="Associated service IDs")


class KBDocumentCreate(KBDocumentBase):
    pass


class KBDocumentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    content: Optional[str] = Field(default=None, min_length=1)
    type: Optional[str] = None
    outcome: Optional[str] = None
    service_ids: Optional[List[int]] = None


class KBDocumentResponse(BaseModel):
    id: int
    title: str
    content: str
    type: str
    outcome: Optional[str] = "n/a"
    services: List[int] = Field(default_factory=list)
    service_ids: List[int] = Field(default_factory=list)
    similarity_score: Optional[float] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Structured Pricing Schemas (F14, F15)
# ---------------------------------------------------------------------------

PricingUnit = Literal["day rate", "fixed", "monthly retainer"]


class PriceItemBase(BaseModel):
    service_id: Optional[int] = Field(default=None, description="Foreign key to services table")
    description: str = Field(..., min_length=1, description="Description of the role, deliverable, or retainer")
    unit: PricingUnit = Field(..., description="Pricing unit ('day rate', 'fixed', 'monthly retainer')")
    amount: float = Field(..., ge=0.0, description="Monetary amount in GBP, must be non-negative")

    @field_validator("description")
    @classmethod
    def validate_description_not_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Description cannot be empty or whitespace")
        return cleaned


class PriceItemCreate(PriceItemBase):
    pass


class PriceItemUpdate(BaseModel):
    service_id: Optional[int] = None
    description: Optional[str] = None
    unit: Optional[PricingUnit] = None
    amount: Optional[float] = Field(default=None, ge=0.0)

    @field_validator("description")
    @classmethod
    def validate_description_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Description cannot be empty or whitespace")
            return cleaned
        return v


class PriceItemResponse(BaseModel):
    id: int
    service_id: Optional[int] = None
    service_name: Optional[str] = None
    description: str
    unit: str
    amount: float

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Export Schemas (F23, F24)
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    export_mode: Optional[Literal["mock", "live"]] = Field(
        default=None,
        description="Override export mode. If None, uses settings.mock_google_export."
    )


class GoogleCommentPayload(BaseModel):
    content: str
    quotedFileContent: Dict[str, Any]
    anchor: str


class GoogleCommentItem(BaseModel):
    section_id: Optional[int] = None
    question: str
    comment_payload: GoogleCommentPayload


class GoogleBatchUpdatePayload(BaseModel):
    requests: List[Dict[str, Any]] = Field(default_factory=list)


class GoogleExportPayload(BaseModel):
    create_document: Dict[str, Any]
    batch_update: GoogleBatchUpdatePayload
    comments: List[GoogleCommentItem] = Field(default_factory=list)


class ExportResponse(BaseModel):
    success: bool = True
    mode: str
    doc_id: str
    doc_url: str
    payload: GoogleExportPayload


