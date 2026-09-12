"""
Eligibility API routes.

Runs the deterministic eligibility engine against all seeded products
and returns recommendations with source evidence.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    EligibilityRequest, EligibilityResponse, WorkflowState, UserProfile,
)
from app.engine.eligibility import evaluate_products
from app.engine.recommendation import (
    check_document_readiness, rank_recommendations, generate_explanations
)
from app.services.knowledge import rag
from app.core.database import get_supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/eligibility", tags=["eligibility"])
db = get_supabase_admin()


def _load_profile(user_id: str) -> UserProfile:
    res = db.table("profiles").select("*").eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = res.data[0].get("structured_profile", {})
    data["user_id"] = user_id
    return UserProfile(**data)


def _load_all_products() -> list[dict]:
    res = db.table("products").select("*").eq("active_version", 1).execute()
    return res.data or []


def _load_user_documents(user_id: str) -> list[dict]:
    res = db.table("documents").select("id, type, status, confidence").eq("user_id", user_id).execute()
    return res.data or []


@router.post("/check", response_model=EligibilityResponse)
async def check_eligibility(request: EligibilityRequest):
    """
    Run deterministic eligibility check for all products.
    
    Pipeline:
    1. Load user profile
    2. Load all active products
    3. Retrieve RAG evidence per product
    4. Run eligibility engine (deterministic)
    5. Check document readiness per product
    6. Rank recommendations (deterministic)
    7. Generate LLM explanations (labeled as AI-generated)
    8. Update workflow state
    9. Return results with full evidence
    """
    try:
        # 1. Load profile
        profile = _load_profile(request.user_id)

        # 2. Load products
        products = _load_all_products()
        if not products:
            raise HTTPException(status_code=404, detail="No active products found. Run seed_products.py first.")

        # 3. Retrieve RAG evidence per product
        evidence_map: dict[str, list[dict]] = {}
        evidence_for_ui: list[dict] = []

        query = f"{profile.loan_purpose or 'loan'} {profile.state or ''} eligibility criteria".strip()

        for product in products:
            pid = str(product.get("id", ""))
            chunks = rag.search_knowledge_for_product(product.get("name", ""), query)
            evidence_map[pid] = chunks
            evidence_for_ui.extend(rag.format_evidence_for_ui(chunks))

        # 4. Run eligibility engine (DETERMINISTIC)
        eligibility_results = evaluate_products(profile, products, evidence_map)

        # 5. Check document readiness
        uploaded_documents = _load_user_documents(request.user_id)
        readiness_map = {}
        for product in products:
            pid = str(product.get("id", ""))
            readiness = check_document_readiness(product, uploaded_documents)
            readiness_map[pid] = readiness

        # 6. Rank recommendations (DETERMINISTIC)
        recommendations = rank_recommendations(
            eligibility_results, readiness_map, profile, products
        )

        # 7. Generate LLM explanations (labeled as AI-generated)
        language = profile.language or "en-IN"
        recommendations = generate_explanations(recommendations, profile, language)

        # 8. Update workflow state
        db.table("applications").update({
            "workflow_state": WorkflowState.OPTIONS_FOUND,
            "eligibility_result": {
                "results": [r.model_dump(mode="json") for r in recommendations]
            },
            "evidence": {"chunks": evidence_for_ui},
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", request.application_id).execute()

        # Add audit event
        res = db.table("applications").select("audit_events").eq("id", request.application_id).execute()
        current_events = res.data[0].get("audit_events", []) if res.data else []
        current_events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "type": "ELIGIBILITY_CHECK_COMPLETE",
            "data": {
                "products_evaluated": len(products),
                "eligible_count": sum(1 for r in recommendations if r.eligibility.status.value == "ELIGIBLE"),
                "needs_review_count": sum(1 for r in recommendations if r.eligibility.status.value == "NEEDS_REVIEW"),
                "ineligible_count": sum(1 for r in recommendations if r.eligibility.status.value == "INELIGIBLE"),
            }
        })
        db.table("applications").update({"audit_events": current_events}).eq("id", request.application_id).execute()

        return EligibilityResponse(
            application_id=request.application_id,
            recommendations=recommendations,
            workflow_state=WorkflowState.OPTIONS_FOUND,
            evidence_summary=evidence_for_ui,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Eligibility check error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Eligibility check failed: {str(e)}")
