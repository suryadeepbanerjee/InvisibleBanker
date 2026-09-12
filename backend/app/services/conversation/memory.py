"""
Conversation Memory Service
===========================
Manages persistent conversation state across all turns.

Architecture: 6-layer context model
  Layer 1: Recent messages (last 15, direct DB query)
  Layer 2: Conversation summary (JSONB, updated after each response)
  Layer 3: Structured profile (from profiles table)
  Layer 4: Relevant document facts (from documents table, filtered by intent)
  Layer 5: Workflow state (from applications table)
  Layer 6: Live research results (from knowledge table, recent relevant chunks)

Critical invariant: context is NEVER cleared due to:
  - empty frontend state
  - page refresh
  - API errors
  - missing history

A new conversation is ONLY created when explicitly requested.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.core.database import get_supabase_admin

logger = logging.getLogger(__name__)

# How many recent messages to include in the LLM context
RECENT_MESSAGE_LIMIT = 15

# How often to regenerate the conversation summary (every N assistant turns)
SUMMARY_UPDATE_FREQUENCY = 5


def _db():
    return get_supabase_admin()


# ─── Conversation CRUD ────────────────────────────────────────────────────────

def get_or_create_conversation(user_id: str, language: str = "en-IN") -> str:
    """
    Find the active conversation for this user or create a new one.
    Returns conversation_id.

    Uses the most recent active conversation. Does NOT create a new one
    every time — only when there's no active conversation at all.
    """
    db = _db()
    res = (
        db.table("conversations")
        .select("id")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["id"]

    # No active conversation — create one
    conv_id = str(uuid.uuid4())
    db.table("conversations").insert({
        "id": conv_id,
        "user_id": user_id,
        "language": language,
        "summary": {},
        "current_intent": "unknown",
        "research_status": "IDLE",
        "is_active": True,
    }).execute()
    logger.info(f"Created new conversation {conv_id} for user {user_id}")
    return conv_id


def get_conversation(conversation_id: str) -> Optional[dict]:
    """Load conversation record. Returns None if not found."""
    db = _db()
    res = db.table("conversations").select("*").eq("id", conversation_id).execute()
    return res.data[0] if res.data else None


def ensure_conversation_belongs_to_user(conversation_id: str, user_id: str) -> bool:
    """Security check: verify conversation belongs to this user."""
    db = _db()
    res = (
        db.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    return bool(res.data)


def start_new_conversation(user_id: str, language: str = "en-IN") -> str:
    """
    Explicitly close all active conversations for this user and start a new one.
    Called ONLY when the user explicitly requests a new conversation.
    """
    db = _db()
    # Mark all existing active conversations as inactive
    db.table("conversations").update({"is_active": False}).eq(
        "user_id", user_id
    ).eq("is_active", True).execute()

    # Create fresh conversation
    conv_id = str(uuid.uuid4())
    db.table("conversations").insert({
        "id": conv_id,
        "user_id": user_id,
        "language": language,
        "summary": {},
        "current_intent": "unknown",
        "research_status": "IDLE",
        "is_active": True,
    }).execute()
    logger.info(f"Started new conversation {conv_id} for user {user_id} (explicit)")
    return conv_id


# ─── Message CRUD ─────────────────────────────────────────────────────────────

def save_message(
    conversation_id: str,
    role: str,
    content: str,
    language: str = "en-IN",
    metadata: Optional[dict] = None,
) -> str:
    """
    Persist a message and update conversation's updated_at timestamp.
    Returns message_id.
    """
    db = _db()
    msg_id = str(uuid.uuid4())
    db.table("messages").insert({
        "id": msg_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "language": language,
        "metadata": metadata or {},
    }).execute()

    # Touch the conversation timestamp so ordering stays correct
    db.table("conversations").update({
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", conversation_id).execute()

    return msg_id


def get_recent_messages(conversation_id: str, limit: int = RECENT_MESSAGE_LIMIT) -> list[dict]:
    """
    Retrieve the last N messages for this conversation.
    Returns list in chronological order (oldest first) — correct for LLM context.
    """
    db = _db()
    # Fetch most recent N in DESC order, then reverse for chronological
    res = (
        db.table("messages")
        .select("role, content, language, metadata, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    if not res.data:
        return []
    # Reverse to get chronological order
    return list(reversed(res.data))


def get_messages_for_llm(conversation_id: str, limit: int = RECENT_MESSAGE_LIMIT) -> list[dict]:
    """
    Format recent messages as OpenAI-compatible message dicts for the LLM.
    Returns [{"role": "user"|"assistant", "content": "..."}, ...]
    """
    messages = get_recent_messages(conversation_id, limit)
    return [{"role": m["role"], "content": m["content"]} for m in messages]


def count_assistant_messages(conversation_id: str) -> int:
    """Count how many assistant messages are in this conversation."""
    db = _db()
    res = (
        db.table("messages")
        .select("id", count="exact")
        .eq("conversation_id", conversation_id)
        .eq("role", "assistant")
        .execute()
    )
    return res.count or 0


# ─── Conversation Summary ─────────────────────────────────────────────────────

def get_conversation_summary(conversation_id: str) -> dict:
    """
    Load the persistent summary for this conversation.

    Example summary structure:
    {
        "intent": "housing_financial_assistance",
        "user_state": "Delhi",
        "purpose": "rent",
        "requested_amount": null,
        "important_facts": ["User does not have enough for rent"],
        "open_questions": ["required_amount"],
        "documents_mentioned": ["bank_statement"],
        "decisions_made": [],
        "language": "hi-IN"
    }
    """
    db = _db()
    res = db.table("conversations").select("summary").eq("id", conversation_id).execute()
    if res.data:
        return res.data[0].get("summary") or {}
    return {}


def update_conversation_summary(conversation_id: str, updates: dict) -> None:
    """
    Merge new information into the conversation summary.
    Does NOT replace the whole summary — merges at top level.
    """
    db = _db()
    existing = get_conversation_summary(conversation_id)
    # Merge: lists are extended, scalars are overwritten
    for key, value in updates.items():
        if isinstance(value, list) and isinstance(existing.get(key), list):
            # Extend lists but deduplicate
            combined = existing[key] + [v for v in value if v not in existing[key]]
            existing[key] = combined[:50]  # Cap list size
        elif value is not None:
            existing[key] = value

    db.table("conversations").update({
        "summary": existing,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conversation_id).execute()


def update_conversation_intent(conversation_id: str, intent: str, language: str) -> None:
    """Update the current intent and language preference on the conversation."""
    db = _db()
    db.table("conversations").update({
        "current_intent": intent,
        "language": language,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conversation_id).execute()


def update_research_status(conversation_id: str, status: str, job_id: Optional[str] = None) -> None:
    """Update research status on the conversation record."""
    db = _db()
    update = {
        "research_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if job_id:
        update["latest_research_job_id"] = job_id
    db.table("conversations").update(update).eq("id", conversation_id).execute()


# ─── Full Context Assembly ────────────────────────────────────────────────────

def build_conversation_context(
    conversation_id: str,
    user_id: str,
    current_intent: str = "unknown",
) -> dict:
    """
    Assemble the full 6-layer context for the current reasoning request.

    Returns:
    {
        "recent_messages": [...],      # Layer 1: last 15 messages
        "summary": {...},              # Layer 2: conversation summary
        "profile": {...},              # Layer 3: structured profile
        "document_facts": [...],       # Layer 4: relevant doc facts
        "workflow_state": "...",       # Layer 5: application workflow
        "application_id": "...",       # For workflow continuity
        "research_status": "...",      # Research readiness
        "is_new_conversation": bool,   # True only if first message ever
    }
    """
    db = _db()
    context = {}

    # Layer 1: Recent messages
    context["recent_messages"] = get_messages_for_llm(conversation_id)
    context["is_new_conversation"] = len(context["recent_messages"]) == 0

    # Layer 2: Conversation summary
    context["summary"] = get_conversation_summary(conversation_id)

    # Layer 3: Structured profile
    profile_res = db.table("profiles").select("structured_profile").eq("user_id", user_id).execute()
    context["profile"] = {}
    if profile_res.data:
        context["profile"] = profile_res.data[0].get("structured_profile") or {}

    # Layer 4: Relevant document facts (filtered by intent)
    context["document_facts"] = _get_relevant_document_facts(user_id, current_intent)

    # Layer 5: Workflow state
    app_res = (
        db.table("applications")
        .select("id, workflow_state")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    context["workflow_state"] = "START"
    context["application_id"] = None
    if app_res.data:
        context["workflow_state"] = app_res.data[0].get("workflow_state", "START")
        context["application_id"] = app_res.data[0]["id"]

    # Research status from conversation record
    conv = get_conversation(conversation_id)
    context["research_status"] = conv.get("research_status", "IDLE") if conv else "IDLE"

    return context


def _get_relevant_document_facts(user_id: str, intent: str) -> list[dict]:
    """
    Retrieve document-extracted facts relevant to the current intent.
    Filters for high-confidence fields based on what the intent needs.
    """
    db = _db()
    doc_res = (
        db.table("documents")
        .select("id, type, extracted_json, confidence, status, metadata")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    if not doc_res.data:
        return []

    # Intent-to-relevant-fields mapping
    INTENT_FIELD_RELEVANCE = {
        "business_financing": [
            "monthly_income", "annual_turnover", "gst_number", "business_name",
            "average_monthly_balance", "statement_period_months",
        ],
        "home_loan": [
            "monthly_income", "employer_name", "average_monthly_balance",
        ],
        "personal_loan": [
            "monthly_income", "employer_name", "average_monthly_balance",
            "has_loan_default",
        ],
        "payment_issue": ["account_number", "bank_name"],
        "govt_scheme": [
            "monthly_income", "business_name", "gst_number",
        ],
        "general_query": [],  # Include all confident fields
    }
    relevant_fields = INTENT_FIELD_RELEVANCE.get(intent, [])

    facts = []
    for doc in doc_res.data:
        extracted = doc.get("extracted_json") or {}
        doc_id = doc["id"]
        doc_type = doc.get("type", "unknown")
        meta = doc.get("metadata") or {}

        for field_name, field_data in extracted.items():
            if not isinstance(field_data, dict):
                continue
            value = field_data.get("value")
            confidence = float(field_data.get("confidence", 0.0))
            if value is None or confidence < 0.6:
                continue
            # Include field if it's relevant to intent OR if intent is unknown/general
            if not relevant_fields or field_name in relevant_fields:
                facts.append({
                    "field": field_name,
                    "value": value,
                    "confidence": confidence,
                    "document_id": doc_id,
                    "document_type": doc_type,
                    "source_type": field_data.get("source_type", "llm_interpretation"),
                    "evidence": field_data.get("evidence_span", ""),
                    "filename": meta.get("filename", ""),
                })

    return facts


# ─── Summary Generation Helper ────────────────────────────────────────────────

def should_update_summary(conversation_id: str) -> bool:
    """Return True if it's time to update the conversation summary."""
    count = count_assistant_messages(conversation_id)
    return count > 0 and count % SUMMARY_UPDATE_FREQUENCY == 0


def extract_summary_updates_from_intent(intent_result: dict, profile: dict) -> dict:
    """
    Build summary update dict from a new intent result and profile snapshot.
    Non-destructive — only includes fields that have values.
    """
    updates = {}

    if intent := intent_result.get("intent"):
        if intent != "unknown":
            updates["intent"] = intent

    if state := (intent_result.get("state") or profile.get("state")):
        updates["user_state"] = state

    if purpose := (intent_result.get("loan_purpose") or profile.get("loan_purpose")):
        updates["purpose"] = purpose

    if amount := (intent_result.get("loan_amount") or profile.get("loan_amount")):
        updates["requested_amount"] = amount

    if lang := intent_result.get("detected_language"):
        updates["language"] = lang

    return updates
