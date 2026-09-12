"""
Intent and NLU service.

Responsibilities:
- Detect language
- Extract financial intent
- Extract structured entities (amount, state, purpose)
- Identify missing required fields
- Generate follow-up questions

The LLM extracts; the backend validates.
"""
import logging
from typing import Optional
from app.services.llm import provider as llm
from app.models.schemas import IntentResult, UserProfile

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = """You are a financial intent extraction system for Indian users.
Your job is to extract structured information from the user's message.

Extract the following as JSON:
{
  "domain": one of ["government_scheme", "financing", "payment", "insurance", "general", "unknown"],
  "topic": brief string describing the exact topic (e.g. "Pradhan Mantri Awas Yojana", "business_loan", "UPI failed transaction"),
  "task": one of ["information", "eligibility", "documents", "application", "recommendation", "grievance", "unknown"],
  "intent": mapping to legacy intent (use "business_financing", "home_loan", "personal_loan", "crop_insurance", "govt_scheme", "payment_issue", "grievance", "document_help", "general_query", or "unknown" based on domain/topic),
  "detected_language": language code like "hi-IN", "en-IN", "ta-IN" etc.,
  "loan_amount": number in INR or null,
  "loan_purpose": brief string or null,
  "state": Indian state name or null,
  "district": district name or null,
  "occupation": occupation string or null,
  "business_type": type of business or null,
  "confidence": 0.0 to 1.0,
  "missing_required_fields": list of field names that are needed but not provided
}

Rules:
- Extract ONLY what the user explicitly said — do NOT guess or invent
- If an amount is mentioned in lakhs (lakh), convert to full number (5 lakh = 500000)
- If state is not mentioned, set to null
- missing_required_fields should list what's needed but absent. DO NOT list profile fields if task is just "information" or "grievance".
- For financing domain + recommendation task, required fields are: loan_amount, loan_purpose, state
"""


def extract_intent(user_message: str, conversation_history: list[dict] | None = None) -> IntentResult:
    """Extract structured intent from user's natural language message."""
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
    ]

    if conversation_history:
        messages.extend(conversation_history[-6:])  # Last 3 turns for context

    messages.append({"role": "user", "content": user_message})

    result = llm.extract_json(
        messages,
        fallback={
            "domain": "unknown",
            "topic": "unknown",
            "task": "unknown",
            "intent": "unknown",
            "detected_language": "en-IN",
            "loan_amount": None,
            "loan_purpose": None,
            "state": None,
            "district": None,
            "occupation": None,
            "business_type": None,
            "confidence": 0.0,
            "missing_required_fields": [],
        }
    )

    return IntentResult(
        domain=result.get("domain", "unknown"),
        topic=result.get("topic", "unknown"),
        task=result.get("task", "unknown"),
        intent=result.get("intent", "unknown"),
        raw_input=user_message,
        detected_language=result.get("detected_language", "en-IN"),
        loan_amount=result.get("loan_amount"),
        loan_purpose=result.get("loan_purpose"),
        state=result.get("state"),
        confidence=result.get("confidence", 0.5),
        missing_fields=result.get("missing_required_fields", []),
    )


PROFILE_UPDATE_SYSTEM_PROMPT = """You are updating a user's financial profile from their message.
Given the current profile and new message, extract any new or updated fields.

Return ONLY changed fields as JSON. Unknown/not mentioned fields should NOT appear in the output.
Preserve existing values — only override if the user clearly stated something new.

Extractable fields:
name, age, state, district, occupation, business_type, business_vintage_years,
monthly_income (number), annual_income (number), loan_amount (number), loan_purpose,
has_existing_loan (boolean), is_npa (boolean), gender, category (SC/ST/OBC/General)

Rules:
- Extract ONLY what was explicitly stated
- Convert lakh amounts: 5 lakh = 500000
- Do NOT guess or invent field values
"""


def update_profile_from_message(
    user_message: str,
    current_profile: UserProfile,
) -> tuple[UserProfile, list[str]]:
    """
    Update profile with any new information from the user's message.
    
    Returns (updated_profile, list_of_newly_filled_fields)
    """
    current_dict = current_profile.model_dump(exclude_none=True)

    messages = [
        {"role": "system", "content": PROFILE_UPDATE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Current profile:\n{current_dict}\n\nUser message:\n{user_message}"
        }
    ]

    updates = llm.extract_json(messages, fallback={})
    newly_filled = []

    if not updates:
        return current_profile, []

    profile_dict = current_profile.model_dump()
    for key, value in updates.items():
        if hasattr(current_profile, key) and value is not None:
            # Wrap income fields in ExtractedField format
            if key in ("monthly_income", "annual_income") and isinstance(value, (int, float)):
                profile_dict[key] = {
                    "value": value,
                    "confidence": 0.85,  # LLM-extracted, medium confidence
                    "source_type": "llm_interpretation",
                }
            else:
                profile_dict[key] = value
            newly_filled.append(key)

    return UserProfile(**profile_dict), newly_filled


def generate_follow_up_question(
    intent: IntentResult,
    profile: UserProfile,
    language: str = "en-IN",
) -> Optional[str]:
    """
    Generate the SINGLE most important follow-up question needed.
    
    Returns None if profile is sufficient for intent.
    """
    if intent.task in ("information", "grievance", "documents") or intent.domain == "payment":
        return None  # Do not ask profile questions for pure information requests
        
    missing = intent.missing_fields

    # Add missing profile fields
    required_for_eligibility = []
    if not profile.state:
        required_for_eligibility.append("state (which state are you located in?)")
    if not profile.loan_amount:
        required_for_eligibility.append("loan_amount (how much loan do you need?)")
    if not profile.loan_purpose:
        required_for_eligibility.append("loan_purpose (what is the loan for?)")
    if profile.age is None:
        required_for_eligibility.append("age (how old are you?)")
    if not profile.occupation:
        required_for_eligibility.append("occupation (what is your occupation?)")

    if not required_for_eligibility:
        return None

    # Ask for just ONE field at a time — most important first
    priority_field = required_for_eligibility[0]

    prompt = f"""Generate a single, natural, friendly question to ask the user.
The question should ask about: {priority_field}

Language: {language}
If Hindi (hi-IN), ask in simple Hindi/Hinglish.
If English (en-IN), ask in simple English.

Return ONLY the question text, no JSON.
"""
    return llm.generate(
        [{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=100,
    ).strip()
