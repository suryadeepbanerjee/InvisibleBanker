"""
Document extraction service.

Pipeline:
1. Detect document type from filename / content
2. Extract text with PyMuPDF (primary) or pdfplumber (tables)
3. Extract structured fields with LLM
4. Assign confidence scores
5. Flag low-confidence fields for NEEDS_REVIEW
6. Detect conflicts between documents
"""
import io
import logging
from typing import Optional
import pdfplumber
from app.services.llm import provider as llm
from app.models.schemas import ExtractedField, DataSourceType, DocumentStatus
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

DOCUMENT_TYPES = [
    "bank_statement",
    "salary_slip",
    "gst_certificate",
    "gst_return",
    "pan_card",
    "aadhaar",
    "business_registration",
    "income_tax_return",
    "loan_statement",
    "property_document",
    "other",
]

TYPE_DETECTION_PROMPT = """You are a document type classifier for Indian financial documents.
Classify the document from its text content.

Possible types: bank_statement, salary_slip, gst_certificate, gst_return, pan_card, aadhaar, 
business_registration, income_tax_return, loan_statement, property_document, other

Return JSON: {"document_type": "...", "confidence": 0.0-1.0}
"""

FIELD_EXTRACTION_PROMPT = """Extract structured financial information from this Indian financial document.

Return JSON with any of these fields you can find (omit fields not present):
{
  "account_holder_name": {"value": "...", "confidence": 0.0-1.0, "evidence": "exact text from doc"},
  "pan_number": {"value": "...", "confidence": 0.0-1.0, "evidence": "..."},
  "monthly_income": {"value": NUMBER_IN_INR, "confidence": 0.0-1.0, "evidence": "..."},
  "average_monthly_balance": {"value": NUMBER, "confidence": 0.0-1.0, "evidence": "..."},
  "annual_turnover": {"value": NUMBER, "confidence": 0.0-1.0, "evidence": "..."},
  "gst_number": {"value": "...", "confidence": 0.0-1.0, "evidence": "..."},
  "business_name": {"value": "...", "confidence": 0.0-1.0, "evidence": "..."},
  "bank_name": {"value": "...", "confidence": 0.0-1.0, "evidence": "..."},
  "account_number": {"value": "MASKED", "confidence": 0.0-1.0, "evidence": "..."},
  "statement_period_months": {"value": NUMBER, "confidence": 0.0-1.0, "evidence": "..."},
  "has_loan_default": {"value": true/false, "confidence": 0.0-1.0, "evidence": "..."},
  "employer_name": {"value": "...", "confidence": 0.0-1.0, "evidence": "..."},
  "designation": {"value": "...", "confidence": 0.0-1.0, "evidence": "..."}
}

Rules:
- Only extract what is EXPLICITLY in the document — do NOT infer or guess
- Confidence 0.9+ = clearly stated. 0.7-0.9 = reasonably clear. <0.7 = ambiguous
- For account numbers, always set value to "MASKED" for security
- Evidence should be a short quote from the document
"""


def extract_text_pdfplumber(pdf_bytes: bytes) -> tuple[str, int]:
    """Extract text using pdfplumber (better for tables on free tiers without C++ dependencies). Returns (text, page_count)."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texts = []
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text() or ""
            # Also extract tables
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row:
                        texts.append(" | ".join(str(cell or "") for cell in row))
            texts.append(text)
        return "\n".join(texts), page_count


def detect_document_type(text: str) -> tuple[str, float]:
    """Detect document type from extracted text."""
    # Quick heuristic checks first (cheaper than LLM)
    text_lower = text.lower()
    if "gst" in text_lower and "certificate" in text_lower:
        return "gst_certificate", 0.95
    if "salary" in text_lower and ("slip" in text_lower or "payslip" in text_lower):
        return "salary_slip", 0.95
    if "statement of account" in text_lower or "account statement" in text_lower:
        return "bank_statement", 0.90
    if "permanent account number" in text_lower or "income tax" in text_lower and len(text) < 500:
        return "pan_card", 0.85
    if "aadhaar" in text_lower or "uidai" in text_lower:
        return "aadhaar", 0.90
    if "gst" in text_lower and "return" in text_lower:
        return "gst_return", 0.85

    # Fall back to LLM for ambiguous cases
    try:
        result = llm.extract_json(
            [
                {"role": "system", "content": TYPE_DETECTION_PROMPT},
                {"role": "user", "content": text[:2000]},  # Limit for cost control
            ],
            fallback={"document_type": "other", "confidence": 0.3},
        )
        return result.get("document_type", "other"), result.get("confidence", 0.3)
    except Exception as e:
        logger.warning(f"Document type detection failed: {e}")
        return "other", 0.3


def extract_structured_fields(
    text: str,
    document_type: str,
    document_id: str,
) -> dict[str, ExtractedField]:
    """
    Extract structured fields with confidence scores.
    
    Returns dict of field_name → ExtractedField.
    """
    try:
        context = f"Document type: {document_type}\n\nDocument text:\n{text[:4000]}"  # Limit for cost control
        result = llm.extract_json(
            [
                {"role": "system", "content": FIELD_EXTRACTION_PROMPT},
                {"role": "user", "content": context},
            ],
            fallback={},
        )
    except Exception as e:
        logger.error(f"Field extraction LLM failed: {e}")
        return {}

    fields = {}
    for field_name, field_data in result.items():
        if not isinstance(field_data, dict) or "value" not in field_data:
            continue
        if field_data["value"] is None:
            continue

        fields[field_name] = ExtractedField(
            value=field_data["value"],
            confidence=float(field_data.get("confidence", 0.5)),
            source_type=DataSourceType.LLM_INTERPRETATION,
            document_id=document_id,
            evidence_span=field_data.get("evidence", ""),
        )

    return fields


def check_field_conflicts(
    existing_fields: dict,
    new_fields: dict[str, ExtractedField],
    document_id: str,
) -> list[dict]:
    """
    Check for conflicting values between existing profile data and new document.
    
    Returns list of conflict records.
    """
    conflicts = []
    conflict_fields = ["monthly_income", "annual_turnover", "pan_number", "gst_number"]

    for field in conflict_fields:
        if field not in new_fields:
            continue
        if field not in existing_fields:
            continue

        existing = existing_fields[field]
        new = new_fields[field]

        existing_val = existing.get("value") if isinstance(existing, dict) else getattr(existing, "value", None)
        new_val = new.value

        if existing_val is None or new_val is None:
            continue

        # For numeric fields, allow 5% variance
        if isinstance(existing_val, (int, float)) and isinstance(new_val, (int, float)):
            if abs(existing_val - new_val) / max(abs(existing_val), 1) > 0.05:
                conflicts.append({
                    "field": field,
                    "existing_value": existing_val,
                    "existing_document_id": existing.get("document_id") if isinstance(existing, dict) else getattr(existing, "document_id", None),
                    "new_value": new_val,
                    "new_document_id": document_id,
                    "resolution": "NEEDS_REVIEW",
                })
        elif existing_val != new_val:
            conflicts.append({
                "field": field,
                "existing_value": existing_val,
                "new_value": new_val,
                "new_document_id": document_id,
                "resolution": "NEEDS_REVIEW",
            })

    return conflicts


def process_document(
    pdf_bytes: bytes,
    filename: str,
    document_id: str,
    existing_profile_fields: dict | None = None,
) -> dict:
    """
    Full document processing pipeline.
    
    Returns:
    {
        "document_type": str,
        "type_confidence": float,
        "extracted_text": str,
        "page_count": int,
        "extracted_fields": dict,  # field → ExtractedField
        "conflicts": list,
        "overall_confidence": float,
        "status": DocumentStatus,
        "low_confidence_fields": list[str],
    }
    """
    # Step 1: Extract text
    try:
        text, page_count = extract_text_pdfplumber(pdf_bytes)
    except Exception as e:
        logger.error(f"Text extraction failed for {filename}: {e}")
        return {
            "document_type": "other",
            "type_confidence": 0.0,
            "extracted_text": "",
            "page_count": 0,
            "extracted_fields": {},
            "conflicts": [],
            "overall_confidence": 0.0,
            "status": DocumentStatus.NEEDS_REVIEW,
            "low_confidence_fields": [],
        }

    # Step 2: Extract structured fields FIRST (do not let classification block)
    fields = extract_structured_fields(text, "Unknown/Detecting", document_id)

    # Step 3: Detect type (can optionally use extracted fields context, but for now just text)
    doc_type, type_confidence = detect_document_type(text)

    # Step 4: Check confidence
    threshold = settings.confidence_threshold
    low_confidence_fields = [
        field for field, ef in fields.items()
        if ef.confidence < threshold
    ]

    # Step 5: Check conflicts
    conflicts = []
    if existing_profile_fields:
        conflicts = check_field_conflicts(
            existing_profile_fields,
            fields,
            document_id,
        )

    # Step 6: Determine overall status
    if low_confidence_fields or conflicts:
        status = DocumentStatus.NEEDS_REVIEW
    else:
        status = DocumentStatus.EXTRACTED

    # Overall confidence = average of field confidences
    field_confidences = [ef.confidence for ef in fields.values()]
    overall_confidence = sum(field_confidences) / len(field_confidences) if field_confidences else 0.0

    return {
        "document_type": doc_type,
        "type_confidence": type_confidence,
        "extracted_text": text,
        "page_count": page_count,
        "extracted_fields": {k: v.model_dump() for k, v in fields.items()},
        "conflicts": conflicts,
        "overall_confidence": overall_confidence,
        "status": status,
        "low_confidence_fields": low_confidence_fields,
    }
