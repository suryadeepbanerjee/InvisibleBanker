"""
Deterministic Eligibility Engine

Rules are stored as JSON on products.
This module evaluates them with pure Python — no LLM involvement.

Supported operators: >=, <=, >, <, ==, !=, IN, NOT_IN

Returns: ELIGIBLE | INELIGIBLE | NEEDS_REVIEW

NEEDS_REVIEW is triggered by:
- Missing required field in profile
- Field confidence below threshold (when ExtractedField)
- Unrecognized operator (safety fallback)
"""
import logging
from typing import Any
from app.models.schemas import (
    EligibilityStatus,
    EligibilityRule,
    RuleResult,
    ProductEligibility,
    UserProfile,
    ExtractedField,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SUPPORTED_OPERATORS = {">=", "<=", ">", "<", "==", "!=", "IN", "NOT_IN"}


def _get_profile_value(profile: UserProfile, field: str) -> tuple[Any, float]:
    """
    Extract a field value from the profile.
    
    Returns (value, confidence).
    If field is an ExtractedField, returns its value and confidence.
    If field is missing, returns (None, 0.0).
    """
    raw = getattr(profile, field, None)

    if raw is None:
        return None, 0.0

    if isinstance(raw, ExtractedField):
        return raw.value, raw.confidence

    if isinstance(raw, dict) and "value" in raw:
        return raw["value"], raw.get("confidence", 1.0)

    # Plain value — assume full confidence (user-stated or LLM-extracted at medium confidence)
    return raw, 0.9


def _evaluate_single_rule(
    rule: EligibilityRule,
    actual_value: Any,
    confidence: float,
) -> RuleResult:
    """Evaluate a single rule against an actual value."""
    threshold = settings.confidence_threshold

    # Missing value → NEEDS_REVIEW
    if actual_value is None:
        return RuleResult(
            rule=rule,
            passed=None,
            actual_value=None,
            reason=f"Field '{rule.field}' is missing from profile",
        )

    # Low confidence → NEEDS_REVIEW
    if confidence < threshold:
        return RuleResult(
            rule=rule,
            passed=None,
            actual_value=actual_value,
            reason=f"Field '{rule.field}' has low confidence ({confidence:.0%} < {threshold:.0%}). Requires human review.",
        )

    # Unknown operator → safety fallback
    if rule.operator not in SUPPORTED_OPERATORS:
        logger.error(f"Unknown operator: {rule.operator}")
        return RuleResult(
            rule=rule,
            passed=None,
            actual_value=actual_value,
            reason=f"Unknown operator '{rule.operator}' — cannot evaluate safely",
        )

    # Evaluate
    try:
        op = rule.operator
        rv = rule.value

        if op == ">=":
            passed = actual_value >= rv
        elif op == "<=":
            passed = actual_value <= rv
        elif op == ">":
            passed = actual_value > rv
        elif op == "<":
            passed = actual_value < rv
        elif op == "==":
            passed = actual_value == rv
        elif op == "!=":
            passed = actual_value != rv
        elif op == "IN":
            passed = actual_value in rv
        elif op == "NOT_IN":
            passed = actual_value not in rv
        else:
            passed = None  # Should never reach here

        reason = ""
        if not passed:
            reason = f"'{rule.field}' is {actual_value!r}, but must be {op} {rv!r}"

        return RuleResult(rule=rule, passed=passed, actual_value=actual_value, reason=reason)

    except TypeError as e:
        logger.warning(f"Type error evaluating rule {rule.field} {rule.operator} {rule.value}: {e}")
        return RuleResult(
            rule=rule,
            passed=None,
            actual_value=actual_value,
            reason=f"Cannot compare '{rule.field}' ({type(actual_value).__name__}) with {rule.value!r}: {e}",
        )


def evaluate_product(
    profile: UserProfile,
    product: dict,
    evidence_chunks: list[dict] | None = None,
) -> ProductEligibility:
    """
    Evaluate user eligibility for a single product.
    
    Args:
        profile: User's structured profile
        product: Product dict with 'id', 'name', 'rules' (list of rule dicts)
        evidence_chunks: RAG-retrieved evidence chunks for this product
    
    Returns:
        ProductEligibility with status and detailed rule results
    """
    rules_raw = product.get("rules", [])
    product_id = str(product.get("id", ""))
    product_name = product.get("name", "Unknown Product")

    rule_results: list[RuleResult] = []
    needs_review_reasons: list[str] = []

    for rule_dict in rules_raw:
        try:
            rule = EligibilityRule(**rule_dict)
        except Exception as e:
            logger.warning(f"Invalid rule format in product {product_name}: {e}")
            continue

        actual_value, confidence = _get_profile_value(profile, rule.field)
        result = _evaluate_single_rule(rule, actual_value, confidence)
        rule_results.append(result)

        if result.passed is None:
            needs_review_reasons.append(result.reason)

    # Determine overall status
    if any(r.passed is None for r in rule_results):
        status = EligibilityStatus.NEEDS_REVIEW
    elif all(r.passed for r in rule_results):
        status = EligibilityStatus.ELIGIBLE
    else:
        status = EligibilityStatus.INELIGIBLE

    return ProductEligibility(
        product_id=product_id,
        product_name=product_name,
        status=status,
        rule_results=rule_results,
        needs_review_reasons=needs_review_reasons,
        evidence_chunks=evidence_chunks or [],
    )


def evaluate_products(
    profile: UserProfile,
    products: list[dict],
    evidence_map: dict[str, list[dict]] | None = None,
) -> list[ProductEligibility]:
    """
    Evaluate eligibility for multiple products.
    
    Returns list of ProductEligibility results, one per product.
    """
    results = []
    for product in products:
        pid = str(product.get("id", ""))
        chunks = (evidence_map or {}).get(pid, [])
        result = evaluate_product(profile, product, chunks)
        results.append(result)
    return results
