from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum
from datetime import datetime
import uuid


# ─── Research / Source Types ──────────────────────────────────────────────────

class ResearchStatus(str, Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    RESEARCHING = "RESEARCHING"
    READY = "READY"
    FAILED = "FAILED"


# ─── Enums ───────────────────────────────────────────────────────────────────

class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class WorkflowState(str, Enum):
    START = "START"
    INTENT_CAPTURED = "INTENT_CAPTURED"
    PROFILE_INCOMPLETE = "PROFILE_INCOMPLETE"
    PROFILE_READY = "PROFILE_READY"
    DOCUMENT_COLLECTION = "DOCUMENT_COLLECTION"
    DOCUMENT_ANALYSIS = "DOCUMENT_ANALYSIS"
    ELIGIBILITY_CHECK = "ELIGIBILITY_CHECK"
    OPTIONS_FOUND = "OPTIONS_FOUND"
    USER_SELECTED_OPTION = "USER_SELECTED_OPTION"
    APPLICATION_READY = "APPLICATION_READY"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    COMPLETED = "COMPLETED"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"


class DataSourceType(str, Enum):
    """Distinguishes the origin of data for traceability."""
    LLM_INTERPRETATION = "llm_interpretation"
    SOURCE_FACT = "source_fact"
    DETERMINISTIC_COMPUTATION = "deterministic_computation"
    HUMAN_CONFIRMED = "human_confirmed"


# ─── Extracted Field (with evidence) ─────────────────────────────────────────

class ExtractedField(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: DataSourceType = DataSourceType.LLM_INTERPRETATION
    document_id: Optional[str] = None
    page: Optional[int] = None
    evidence_span: Optional[str] = None


# ─── Intent ──────────────────────────────────────────────────────────────────

class IntentResult(BaseModel):
    domain: str = "general"
    topic: str = "unknown"
    task: str = "information"
    intent: str = "unknown"  # Legacy compatibility
    raw_input: str
    detected_language: str = "en-IN"
    loan_amount: Optional[float] = None
    loan_purpose: Optional[str] = None
    state: Optional[str] = None
    confidence: float = 1.0
    missing_fields: list[str] = []


# ─── User Profile ────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    age: Optional[int] = None
    language: str = "en-IN"
    state: Optional[str] = None
    district: Optional[str] = None
    occupation: Optional[str] = None
    business_type: Optional[str] = None
    business_vintage_years: Optional[int] = None
    monthly_income: Optional[ExtractedField] = None
    annual_income: Optional[ExtractedField] = None
    loan_amount: Optional[float] = None
    loan_purpose: Optional[str] = None
    has_existing_loan: Optional[bool] = None
    is_npa: Optional[bool] = None
    gender: Optional[str] = None
    category: Optional[str] = None  # SC/ST/OBC/General


# ─── Eligibility Rule ─────────────────────────────────────────────────────────

class EligibilityRule(BaseModel):
    field: str
    operator: str  # >=, <=, >, <, ==, !=, IN, NOT_IN
    value: Any
    source_url: Optional[str] = None
    authority: Optional[str] = None
    document_title: Optional[str] = None
    page: Optional[int] = None
    version: Optional[int] = None
    last_verified: Optional[str] = None
    knowledge_chunk_id: Optional[str] = None


# ─── Eligibility Result ───────────────────────────────────────────────────────

class RuleResult(BaseModel):
    rule: EligibilityRule
    passed: Optional[bool] = None  # None means NEEDS_REVIEW
    actual_value: Any = None
    reason: str = ""


class ProductEligibility(BaseModel):
    product_id: str
    product_name: str
    status: EligibilityStatus
    rule_results: list[RuleResult]
    needs_review_reasons: list[str] = []
    evidence_chunks: list[dict] = []


# ─── Document Readiness ───────────────────────────────────────────────────────

class DocumentCheckItem(BaseModel):
    document_type: str
    label: str
    present: bool
    document_id: Optional[str] = None


class DocumentReadiness(BaseModel):
    product_id: str
    product_name: str
    required: list[DocumentCheckItem]
    total: int
    present: int

    @property
    def completeness_pct(self) -> float:
        return (self.present / self.total * 100) if self.total > 0 else 0.0


# ─── Recommendation ───────────────────────────────────────────────────────────

class ProductRecommendation(BaseModel):
    product_id: str
    product_name: str
    product_type: str
    eligibility: ProductEligibility
    document_readiness: DocumentReadiness
    rank: int
    rank_reason: str
    explanation: str = ""  # LLM-generated, clearly labeled
    source_metadata: dict = {}


# ─── Audit Event ─────────────────────────────────────────────────────────────

class AuditEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    type: str
    data: dict = {}


# ─── Document Fact (with provenance) ─────────────────────────────────────────

class DocumentFact(BaseModel):
    field: str
    value: Any
    confidence: float
    document_id: Optional[str] = None
    document_type: Optional[str] = None
    source_type: str = "llm_interpretation"
    evidence: Optional[str] = None
    filename: Optional[str] = None


# ─── Conversation Summary ─────────────────────────────────────────────────────

class ConversationSummary(BaseModel):
    domain: Optional[str] = None
    topic: Optional[str] = None
    task: Optional[str] = None
    intent: Optional[str] = None
    user_state: Optional[str] = None
    purpose: Optional[str] = None
    requested_amount: Optional[float] = None
    important_facts: list[str] = []
    open_questions: list[str] = []
    documents_mentioned: list[str] = []
    decisions_made: list[str] = []
    language: Optional[str] = None


# ─── Chat / Conversation ─────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    language: str = "en-IN"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_type: Optional[DataSourceType] = None


# ─── Request/Response Models ──────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None  # Stable identifier, persisted in localStorage
    application_id: Optional[str] = None
    language: str = "en-IN"


class ChatResponse(BaseModel):
    reply: str
    detected_language: str
    intent: Optional[IntentResult] = None
    profile: Optional[UserProfile] = None
    workflow_state: WorkflowState = WorkflowState.START
    follow_up_questions: list[str] = []
    requires_confirmation: list[dict] = []  # Critical values to confirm
    application_id: Optional[str] = None
    user_id: Optional[str] = None  # Returned so frontend can persist session
    conversation_id: Optional[str] = None  # Stable conversation identifier
    research_status: ResearchStatus = ResearchStatus.IDLE  # Live research state
    is_new_conversation: bool = False  # True only on first message ever


class EligibilityRequest(BaseModel):
    user_id: str
    application_id: str


class EligibilityResponse(BaseModel):
    application_id: str
    recommendations: list[ProductRecommendation]
    workflow_state: WorkflowState
    evidence_summary: list[dict] = []
