"""
Chat/Conversation API routes — REWRITTEN for persistent context.

Key changes from original:
  1. Every request carries/creates a stable conversation_id
  2. Messages are PERSISTED before and after processing
  3. All 6 context layers are assembled before calling the LLM
  4. Generic greeting ONLY fires on is_new_conversation == True
  5. Live research is triggered for relevant intents (non-blocking)
  6. Document facts are included in LLM context
  7. Context failure ≠ new conversation

The main invariant:
  If the user has said anything before, the assistant knows about it.
  "हान" / "yes" / "iske liye kya karna hai?" will always resolve
  against conversation context — never trigger a generic greeting.
"""
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    ChatRequest, ChatResponse, UserProfile, WorkflowState,
    IntentResult, AuditEvent, ResearchStatus,
)
from app.services.llm import intent as intent_service
from app.services.llm import provider as llm_provider
from app.services.knowledge.rag import search_knowledge, format_evidence_for_llm
from app.services.conversation import memory as conv_memory
from app.services.research.research_service import (
    start_research_job, needs_live_research, get_job_status
)
from app.core.database import get_supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])
db = get_supabase_admin()


# ─── User/Profile helpers (unchanged from original) ──────────────────────────

def _upsert_user(user_id: str | None, language: str) -> str:
    if user_id:
        res = db.table("users").select("id").eq("id", user_id).execute()
        if res.data:
            return user_id
    new_id = str(uuid.uuid4())
    db.table("users").insert({"id": new_id, "language": language}).execute()
    return new_id


def _get_or_create_profile(user_id: str) -> UserProfile:
    res = db.table("profiles").select("*").eq("user_id", user_id).execute()
    if res.data:
        data = res.data[0].get("structured_profile", {})
        data["user_id"] = user_id
        try:
            return UserProfile(**data)
        except Exception:
            pass
    return UserProfile(user_id=user_id)


def _save_profile(profile: UserProfile) -> None:
    data = profile.model_dump(exclude_none=True)
    user_id = data.pop("user_id", None)
    if not user_id:
        return
    db.table("profiles").upsert(
        {"user_id": user_id, "structured_profile": data, "updated_at": datetime.utcnow().isoformat()},
        on_conflict="user_id"
    ).execute()


def _get_or_create_application(user_id: str, application_id: str | None) -> dict:
    if application_id:
        res = db.table("applications").select("*").eq("id", application_id).execute()
        if res.data:
            return res.data[0]
    new_id = str(uuid.uuid4())
    app = {
        "id": new_id,
        "user_id": user_id,
        "workflow_state": WorkflowState.START,
        "eligibility_result": {},
        "evidence": {},
        "audit_events": [],
    }
    db.table("applications").insert(app).execute()
    return app


def _add_audit_event(application_id: str, event_type: str, data: dict) -> None:
    event = AuditEvent(type=event_type, data=data).model_dump(mode="json")
    res = db.table("applications").select("audit_events").eq("id", application_id).execute()
    current = []
    if res.data:
        current = res.data[0].get("audit_events") or []
    current.append(event)
    db.table("applications").update({"audit_events": current}).eq("id", application_id).execute()


def _determine_workflow_state(intent: IntentResult, profile: UserProfile, previous_state: str) -> WorkflowState:
    if previous_state == WorkflowState.COMPLETED:
        return WorkflowState.COMPLETED
    if intent.domain == "unknown":
        if previous_state not in ("START", "unknown"):
            return WorkflowState(previous_state)
        return WorkflowState.START

    # If the user is just asking for information, they don't need a full profile.
    if intent.task in ("information", "grievance", "documents") or intent.domain == "payment":
        return WorkflowState.PROFILE_READY

    has_minimum = bool(
        profile.state and profile.loan_amount and
        profile.loan_purpose and profile.age is not None and profile.occupation
    )
    if has_minimum:
        if previous_state in (WorkflowState.START, WorkflowState.INTENT_CAPTURED, WorkflowState.PROFILE_INCOMPLETE):
            return WorkflowState.PROFILE_READY
        return WorkflowState(previous_state)
    if intent.domain != "unknown":
        if previous_state == WorkflowState.START:
            return WorkflowState.INTENT_CAPTURED
        return WorkflowState.PROFILE_INCOMPLETE
    return WorkflowState.START


# ─── Context-Aware Prompt Builder ────────────────────────────────────────────

def _build_system_prompt(context: dict, intent: IntentResult, language: str) -> str:
    """
    Build the full system prompt from all 6 context layers.
    This is what makes the assistant remember everything.
    """
    lang_instruction = (
        "Respond in simple Hindi or Hinglish. Use easy language a common person would understand."
        if language.startswith("hi")
        else "Respond in simple English. Avoid jargon."
    )

    # Layer 2: Summary
    summary = context.get("summary", {})
    summary_text = ""
    if summary:
        parts = []
        if summary.get("intent"):
            parts.append(f"Intent: {summary['intent']}")
        if summary.get("user_state"):
            parts.append(f"User state/location: {summary['user_state']}")
        if summary.get("purpose"):
            parts.append(f"Purpose: {summary['purpose']}")
        if summary.get("requested_amount"):
            parts.append(f"Requested amount: ₹{summary['requested_amount']:,.0f}")
        if summary.get("important_facts"):
            parts.append("Known facts: " + "; ".join(summary["important_facts"]))
        if summary.get("documents_mentioned"):
            parts.append("Documents mentioned: " + ", ".join(summary["documents_mentioned"]))
        if summary.get("decisions_made"):
            parts.append("Decisions already made: " + "; ".join(summary["decisions_made"]))
        if parts:
            summary_text = "\n".join(parts)

    # Layer 3: Profile
    profile = context.get("profile", {})
    profile_parts = []
    for field in ["state", "occupation", "business_type", "loan_purpose", "language"]:
        if profile.get(field):
            profile_parts.append(f"{field}: {profile[field]}")
    if profile.get("loan_amount"):
        profile_parts.append(f"loan_amount: ₹{profile['loan_amount']:,.0f}")
    if profile.get("age"):
        profile_parts.append(f"age: {profile['age']}")
    profile_text = "\n".join(profile_parts) if profile_parts else "No profile collected yet."

    # Layer 4: Document facts
    doc_facts = context.get("document_facts", [])
    doc_text = ""
    if doc_facts:
        lines = []
        for f in doc_facts[:8]:  # Cap for token budget
            conf_pct = int(f["confidence"] * 100)
            evidence = f"(evidence: '{f['evidence']}')" if f.get("evidence") else ""
            lines.append(
                f"  - {f['field']}: {f['value']} "
                f"[confidence {conf_pct}%, from {f.get('document_type', 'document')} "
                f"'{f.get('filename', '')}'] {evidence}"
            )
        doc_text = "\n".join(lines)

    # Layer 5: Workflow
    workflow_state = context.get("workflow_state", "START")

    system = f"""You are Invisible Banker — an expert AI financial assistant for Indian users.
You help people understand financial products, government schemes, loans, UPI issues, and more.

{lang_instruction}

CRITICAL RULES:
1. You have MEMORY. The conversation history below contains everything already discussed.
2. NEVER say "Hello! How can I help?" or any generic greeting if there is conversation history.
3. NEVER restart the conversation — always continue from where it left off.
4. If the user says "haan", "yes", "iske liye", "woh wala", resolve the reference from history.
5. If you genuinely cannot resolve a reference, ask ONE specific clarifying question.
6. Do NOT invent financial facts, interest rates, or eligibility criteria.
7. If you cite a source, it must come from the retrieved evidence below.
8. Mark AI-generated explanations clearly. Mark source-backed facts with their source.
9. For consequential data (income, age, loan amount), prefer document facts over user self-report when they conflict.

CURRENT USER PROFILE:
{profile_text}

CONVERSATION SUMMARY (what has been established):
{summary_text if summary_text else "This is the beginning of the conversation."}

CURRENT WORKFLOW STATE: {workflow_state}
CURRENT DOMAIN: {intent.domain}
CURRENT TOPIC: {intent.topic}
CURRENT TASK: {intent.task}
"""
    if doc_text:
        system += f"\nEXTRACTED DOCUMENT FACTS (from user's uploaded documents):\n{doc_text}\n"

    return system


def _build_context_response_messages(
    system_prompt: str,
    recent_messages: list[dict],
    rag_evidence: str,
    current_message: str,
) -> list[dict]:
    """
    Assemble the full message list for the LLM.
    Order: system → recent history → (evidence injection) → current user message
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(recent_messages)

    # Inject retrieved evidence as context before the current message
    if rag_evidence and rag_evidence != "No relevant source information retrieved.":
        messages.append({
            "role": "system",
            "content": f"RETRIEVED OFFICIAL SOURCE EVIDENCE (use this to answer — do not fabricate):\n{rag_evidence}"
        })

    messages.append({"role": "user", "content": current_message})
    return messages


def _generate_research_interim_message(intent: str, language: str) -> str:
    """Return a holding message while live research is running."""
    if language.startswith("hi"):
        status_map = {
            "business_financing": "व्यवसाय ऋण के लिए आधिकारिक स्रोत खोज रहे हैं...",
            "payment_issue": "UPI/भुगतान शिकायत प्रक्रिया जानकारी प्राप्त कर रहे हैं...",
            "govt_scheme": "सरकारी योजनाओं की जानकारी खोज रहे हैं...",
        }
        return status_map.get(intent, "आधिकारिक वित्तीय स्रोतों में खोज जारी है...")
    else:
        status_map = {
            "business_financing": "Researching official business loan sources...",
            "payment_issue": "Retrieving official UPI/payment complaint guidance...",
            "govt_scheme": "Looking up relevant government schemes...",
        }
        return status_map.get(intent, "Researching relevant official sources...")


# ─── Main Chat Endpoint ───────────────────────────────────────────────────────

@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main conversation endpoint — fully context-aware.

    Pipeline:
    1. Get/create user
    2. Get/create stable conversation_id (NEVER reset mid-conversation)
    3. PERSIST user message immediately
    4. Extract intent (with conversation history for context)
    5. Build full 6-layer context
    6. Check if live research is needed (non-blocking)
    7. Retrieve RAG evidence
    8. Generate response using complete context
    9. PERSIST assistant response
    10. Update conversation summary if needed
    11. Update profile from new information
    12. Return with conversation_id (frontend persists this)
    """
    try:
        # Step 1: User
        user_id = _upsert_user(request.user_id, request.language)

        # Step 2: Stable conversation_id — NEVER create a new one unless there
        # is genuinely no active conversation for this user
        conversation_id = request.conversation_id
        if conversation_id:
            # Verify it belongs to this user
            if not conv_memory.ensure_conversation_belongs_to_user(conversation_id, user_id):
                logger.warning(
                    f"conversation_id {conversation_id} does not belong to user {user_id}. "
                    f"Finding/creating correct conversation."
                )
                conversation_id = conv_memory.get_or_create_conversation(user_id, request.language)
        else:
            conversation_id = conv_memory.get_or_create_conversation(user_id, request.language)

        # Step 3: Persist user message FIRST (so history is complete for processing)
        conv_memory.save_message(
            conversation_id=conversation_id,
            role="user",
            content=request.message,
            language=request.language,
            metadata={"raw_language": request.language},
        )

        # Step 4: Build 6-layer context (needs user_id for profile + docs + workflow)
        # We need intent to filter document facts — extract it first
        # Use recent history for intent context
        recent_for_intent = conv_memory.get_messages_for_llm(conversation_id, limit=6)
        intent = intent_service.extract_intent(
            request.message,
            conversation_history=recent_for_intent[:-1],  # Exclude the message we just saved
        )

        # Step 5: Full context assembly
        context = conv_memory.build_conversation_context(
            conversation_id=conversation_id,
            user_id=user_id,
            current_intent=intent.intent, # Keep legacy intent here for document extraction filtering
        )
        
        # Check topic switch to clear previous workflow if needed
        previous_topic = context.get("summary", {}).get("topic")
        if previous_topic and previous_topic != "unknown" and intent.topic != "unknown":
            if previous_topic.lower() != intent.topic.lower():
                logger.info(f"Topic switch detected: {previous_topic} -> {intent.topic}")
        is_new_conversation = context["is_new_conversation"]

        # Effective language: prefer detected > request > profile stored
        effective_language = (
            intent.detected_language
            or request.language
            or context.get("profile", {}).get("language", "en-IN")
        )

        # Update conversation record with latest intent/language
        conv_memory.update_conversation_intent(conversation_id, f"{intent.domain}|{intent.topic}|{intent.task}", effective_language)

        # Step 6: Application/workflow
        application_id = context.get("application_id")
        previous_workflow_state = context.get("workflow_state", WorkflowState.START)

        if not application_id:
            app = _get_or_create_application(user_id, request.application_id)
            application_id = app["id"]
            previous_workflow_state = app.get("workflow_state", WorkflowState.START)

        _add_audit_event(application_id, "INTENT_CAPTURED", {
            "domain": intent.domain,
            "topic": intent.topic,
            "task": intent.task,
            "language": intent.detected_language,
            "confidence": intent.confidence,
            "conversation_id": conversation_id,
        })

        # Step 7: Live research check (non-blocking — starts background job if needed)
        research_job_started = False
        research_status = ResearchStatus.IDLE
        if needs_live_research(intent.domain, intent.topic, intent.task, conversation_id):
            job_id = start_research_job(
                conversation_id=conversation_id,
                user_id=user_id,
                domain=intent.domain,
                topic=intent.topic,
                task=intent.task,
                query=request.message,
            )
            if job_id:
                research_job_started = True
                research_status = ResearchStatus.ANALYZING
                logger.info(f"Live research job started: {job_id}")

        # Check if a previous research job just completed
        if not research_job_started:
            job_status = get_job_status(conversation_id)
            if job_status and job_status.get("status") == "COMPLETE":
                research_status = ResearchStatus.READY

        # Step 8: RAG retrieval from knowledge base (includes live research results)
        rag_chunks = []
        rag_evidence = ""

        if intent.domain not in ("unknown", "general"):
            query = request.message
            if context.get("summary", {}).get("topic"):
                query = f"{query} {context['summary'].get('topic', '')}"
            elif context.get("summary", {}).get("intent"):
                query = f"{query} {context['summary'].get('purpose', '')} {context['summary'].get('user_state', '')}"
            rag_chunks = search_knowledge(query.strip(), top_k=4)
            rag_evidence = format_evidence_for_llm(rag_chunks)

        # Step 9: Update profile from message
        profile = _get_or_create_profile(user_id)
        updated_profile, newly_filled = intent_service.update_profile_from_message(
            request.message, profile
        )
        if intent.loan_amount and not updated_profile.loan_amount:
            updated_profile.loan_amount = intent.loan_amount
            newly_filled.append("loan_amount")
        if intent.loan_purpose and not updated_profile.loan_purpose:
            updated_profile.loan_purpose = intent.loan_purpose
            newly_filled.append("loan_purpose")
        if intent.state and not updated_profile.state:
            updated_profile.state = intent.state
            newly_filled.append("state")
        if intent.detected_language:
            updated_profile.language = intent.detected_language
        updated_profile.user_id = user_id

        if newly_filled:
            _add_audit_event(application_id, "PROFILE_UPDATED", {"fields": newly_filled})

        _save_profile(updated_profile)

        # Step 10: Determine workflow state
        new_workflow_state = _determine_workflow_state(intent, updated_profile, previous_workflow_state)
        db.table("applications").update({
            "workflow_state": new_workflow_state,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", application_id).execute()

        # Step 11: Build response

        # Only show generic greeting on the VERY FIRST message of a NEW conversation
        if is_new_conversation and intent.domain == "unknown":
            # Truly brand new conversation with no intent — ask an open question
            if effective_language.startswith("hi"):
                reply = "नमस्ते! आप किस वित्तीय ज़रूरत के बारे में जानना चाहते हैं? मैं ऋण, सरकारी योजनाओं, UPI समस्याओं या किसी भी वित्तीय विषय में मदद कर सकता हूं।"
            else:
                reply = "Hello! What financial question can I help you with? I can assist with loans, government schemes, UPI issues, or any financial topic."
        elif research_job_started:
            # Research is running — generate LLM response but prepend the interim message
            interim_topic = intent.topic if intent.topic != "unknown" else intent.domain
            interim_msg = _generate_research_interim_message(interim_topic, effective_language)
            system_prompt = _build_system_prompt(context, intent, effective_language)
            llm_messages = _build_context_response_messages(
                system_prompt=system_prompt,
                recent_messages=context["recent_messages"],
                rag_evidence=rag_evidence,
                current_message=request.message,
            )
            llm_reply = llm_provider.generate(llm_messages)
            reply = f"*{interim_msg}*\n\n{llm_reply}"
        else:
            # Full context-aware response
            system_prompt = _build_system_prompt(context, intent, effective_language)
            llm_messages = _build_context_response_messages(
                system_prompt=system_prompt,
                recent_messages=context["recent_messages"],
                rag_evidence=rag_evidence,
                current_message=request.message,
            )

            # For profile-gathering states, generate a follow-up if needed
            follow_up = None
            if new_workflow_state in (WorkflowState.INTENT_CAPTURED, WorkflowState.PROFILE_INCOMPLETE):
                follow_up = intent_service.generate_follow_up_question(
                    intent, updated_profile, effective_language
                )

            if new_workflow_state == WorkflowState.PROFILE_READY:
                reply = llm_provider.generate(llm_messages)
            elif follow_up and not rag_evidence and not context.get("document_facts"):
                # Profile gathering — just ask the follow-up
                reply = follow_up
            else:
                # Generate full context-aware response
                reply = llm_provider.generate(llm_messages)

        # Step 12: Persist assistant response
        conv_memory.save_message(
            conversation_id=conversation_id,
            role="assistant",
            content=reply,
            language=effective_language,
            metadata={
                "intent": intent.intent,
                "workflow_state": new_workflow_state,
                "research_status": research_status,
                "rag_chunks_used": len(rag_chunks),
            },
        )

        # Step 13: Update conversation summary periodically
        summary_updates = conv_memory.extract_summary_updates_from_intent(
            intent.model_dump(), updated_profile.model_dump(exclude_none=True)
        )
        if summary_updates:
            conv_memory.update_conversation_summary(conversation_id, summary_updates)

        # Persist localStorage-compatible user_id/application_id
        if updated_profile.user_id:
            pass  # already saved

        return ChatResponse(
            reply=reply,
            detected_language=effective_language,
            intent=intent,
            profile=updated_profile,
            workflow_state=new_workflow_state,
            follow_up_questions=[],
            application_id=application_id,
            user_id=user_id,
            conversation_id=conversation_id,
            research_status=research_status,
            is_new_conversation=is_new_conversation,
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


# ─── Conversation History Endpoint ───────────────────────────────────────────

@router.get("/conversation/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str, limit: int = 50):
    """
    Retrieve conversation history for frontend session restoration.
    Called on dashboard mount when a conversation_id exists in localStorage.
    """
    messages = conv_memory.get_recent_messages(conversation_id, limit=limit)
    summary = conv_memory.get_conversation_summary(conversation_id)
    conv = conv_memory.get_conversation(conversation_id)

    return {
        "conversation_id": conversation_id,
        "messages": messages,
        "summary": summary,
        "research_status": conv.get("research_status", "IDLE") if conv else "IDLE",
        "language": conv.get("language", "en-IN") if conv else "en-IN",
    }


@router.post("/conversation/new")
async def new_conversation(user_id: str, language: str = "en-IN"):
    """
    Explicitly start a new conversation for a user.
    Called ONLY when the user clicks 'New Conversation'.
    Marks all existing active conversations as inactive.
    """
    conversation_id = conv_memory.start_new_conversation(user_id, language)
    return {
        "conversation_id": conversation_id,
        "message": "New conversation started.",
    }


@router.get("/conversation/{conversation_id}/research-status")
async def get_research_status(conversation_id: str):
    """Poll research job status for this conversation."""
    conv = conv_memory.get_conversation(conversation_id)
    job = get_job_status(conversation_id)
    return {
        "conversation_id": conversation_id,
        "research_status": conv.get("research_status", "IDLE") if conv else "IDLE",
        "job": job,
    }
