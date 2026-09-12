"""
Recommendation Engine

Deterministic ranking of products by eligibility and document readiness.
The LLM explains the ranking — it does NOT create it.

Ranking criteria (in order of priority):
1. ELIGIBLE > NEEDS_REVIEW > INELIGIBLE
2. Document completeness (higher is better)
3. Amount fit (requested amount within product range)
4. Source authority (higher-authority products ranked higher on tie)
"""
import logging
from app.models.schemas import (
    EligibilityStatus,
    ProductEligibility,
    ProductRecommendation,
    DocumentReadiness,
    DocumentCheckItem,
    UserProfile,
)
from app.services.llm import provider as llm

logger = logging.getLogger(__name__)

STATUS_RANK = {
    EligibilityStatus.ELIGIBLE: 0,
    EligibilityStatus.NEEDS_REVIEW: 1,
    EligibilityStatus.INELIGIBLE: 2,
}


def check_document_readiness(
    product: dict,
    uploaded_documents: list[dict],
) -> DocumentReadiness:
    """
    Check document readiness for a product.
    
    Returns a checklist of required vs. uploaded documents.
    """
    required_types = product.get("required_documents", [])
    uploaded_types = {d.get("type", "") for d in uploaded_documents}

    items = []
    present_count = 0

    for req in required_types:
        doc_type = req.get("type", "") if isinstance(req, dict) else req
        label = req.get("label", doc_type) if isinstance(req, dict) else doc_type
        present = doc_type in uploaded_types

        # Find matching document ID
        doc_id = None
        for d in uploaded_documents:
            if d.get("type") == doc_type:
                doc_id = str(d.get("id", ""))
                break

        items.append(DocumentCheckItem(
            document_type=doc_type,
            label=label,
            present=present,
            document_id=doc_id,
        ))
        if present:
            present_count += 1

    return DocumentReadiness(
        product_id=str(product.get("id", "")),
        product_name=product.get("name", "Unknown"),
        required=items,
        total=len(items),
        present=present_count,
    )


def rank_recommendations(
    eligibility_results: list[ProductEligibility],
    document_readiness_map: dict[str, DocumentReadiness],
    profile: UserProfile,
    products: list[dict],
) -> list[ProductRecommendation]:
    """
    Deterministically rank products and create recommendations.
    
    Returns sorted list with rank and reason.
    The LLM will later add explanations to each recommendation.
    """
    product_map = {str(p.get("id", "")): p for p in products}

    scored = []
    for elg in eligibility_results:
        pid = elg.product_id
        product = product_map.get(pid, {})
        readiness = document_readiness_map.get(pid)

        if not readiness:
            readiness = DocumentReadiness(
                product_id=pid,
                product_name=elg.product_name,
                required=[],
                total=0,
                present=0,
            )

        # Score: (status_rank, -doc_completeness, -amount_fit_score)
        status_score = STATUS_RANK.get(elg.status, 3)
        doc_score = -readiness.completeness_pct  # Negate: higher completeness = lower sort value = better rank

        # Amount fit: check if loan amount is within product range
        amount_fit = 0
        if profile.loan_amount:
            min_amt = product.get("min_amount", 0)
            max_amt = product.get("max_amount", float("inf"))
            if min_amt <= profile.loan_amount <= max_amt:
                amount_fit = -1  # Fits

        scored.append({
            "eligibility": elg,
            "readiness": readiness,
            "product": product,
            "sort_key": (status_score, doc_score, amount_fit),
        })

    # Sort by sort_key ascending
    scored.sort(key=lambda x: x["sort_key"])

    recommendations = []
    for rank_idx, item in enumerate(scored, start=1):
        elg = item["eligibility"]
        readiness = item["readiness"]
        product = item["product"]

        # Build rank reason
        if elg.status == EligibilityStatus.ELIGIBLE:
            rank_reason = f"Eligible — {readiness.present}/{readiness.total} required documents available"
        elif elg.status == EligibilityStatus.NEEDS_REVIEW:
            reasons = elg.needs_review_reasons[:2]
            rank_reason = f"Needs review — {'; '.join(reasons)}"
        else:
            failed_rules = [r for r in elg.rule_results if r.passed is False]
            if failed_rules:
                rank_reason = f"Ineligible — {failed_rules[0].reason}"
            else:
                rank_reason = "Ineligible"

        recommendations.append(ProductRecommendation(
            product_id=elg.product_id,
            product_name=elg.product_name,
            product_type=product.get("type", "loan"),
            eligibility=elg,
            document_readiness=readiness,
            rank=rank_idx,
            rank_reason=rank_reason,
            source_metadata=product.get("source_metadata", {}),
        ))

    return recommendations


def generate_explanations(
    recommendations: list[ProductRecommendation],
    profile: UserProfile,
    language: str = "en-IN",
) -> list[ProductRecommendation]:
    """
    Add LLM-generated explanations to each recommendation.
    
    The LLM explains the deterministic result — it does NOT change it.
    Explanations are clearly labeled as AI-generated in the UI.
    """
    for rec in recommendations:
        try:
            context = f"""
Product: {rec.product_name}
Eligibility Status: {rec.eligibility.status}
Rank Reason: {rec.rank_reason}
Documents Available: {rec.document_readiness.present}/{rec.document_readiness.total}
Missing Documents: {[item.label for item in rec.document_readiness.required if not item.present]}

Explain this result to the user in 2-3 simple sentences. 
DO NOT change the eligibility status.
DO NOT invent new information.
Label this as: "AI-generated explanation based on deterministic eligibility check"
"""
            rec.explanation = llm.explain(
                system_prompt="You explain financial eligibility results to Indian users in simple language.",
                user_content=context,
                language=language,
            )
        except Exception as e:
            logger.warning(f"Failed to generate explanation for {rec.product_name}: {e}")
            rec.explanation = rec.rank_reason  # Fallback to deterministic reason

    return recommendations
