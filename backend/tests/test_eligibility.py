"""
Unit tests for the Deterministic Eligibility Engine.

Tests cover:
- All operators (>=, <=, >, <, ==, !=, IN, NOT_IN)
- Three-state output (ELIGIBLE, INELIGIBLE, NEEDS_REVIEW)
- Missing field detection
- Low confidence gating
- Unknown operator safety
- Complex multi-rule scenarios
"""
import pytest
from app.engine.eligibility import evaluate_product, evaluate_products
from app.models.schemas import EligibilityStatus, UserProfile, ExtractedField, DataSourceType


def make_profile(**kwargs) -> UserProfile:
    """Helper to create test profiles."""
    defaults = {"user_id": "test-user"}
    defaults.update(kwargs)
    return UserProfile(**defaults)


def make_product(name: str, rules: list[dict]) -> dict:
    return {
        "id": f"test-{name.replace(' ', '-').lower()}",
        "name": name,
        "type": "loan",
        "rules": rules,
        "required_documents": [],
    }


# ─── Operator Tests ───────────────────────────────────────────────────────────

class TestOperators:
    def test_gte_pass(self):
        profile = make_profile(age=21)
        product = make_product("Test", [{"field": "age", "operator": ">=", "value": 21}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE

    def test_gte_fail(self):
        profile = make_profile(age=20)
        product = make_product("Test", [{"field": "age", "operator": ">=", "value": 21}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.INELIGIBLE

    def test_lte_pass(self):
        profile = make_profile(age=65)
        product = make_product("Test", [{"field": "age", "operator": "<=", "value": 65}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE

    def test_lte_fail(self):
        profile = make_profile(age=66)
        product = make_product("Test", [{"field": "age", "operator": "<=", "value": 65}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.INELIGIBLE

    def test_eq_pass(self):
        profile = make_profile(state="Rajasthan")
        product = make_product("Test", [{"field": "state", "operator": "==", "value": "Rajasthan"}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE

    def test_neq_pass(self):
        profile = make_profile(is_npa=False)
        product = make_product("Test", [{"field": "is_npa", "operator": "!=", "value": True}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE

    def test_neq_fail(self):
        profile = make_profile(is_npa=True)
        product = make_product("Test", [{"field": "is_npa", "operator": "!=", "value": True}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.INELIGIBLE

    def test_in_pass(self):
        profile = make_profile(state="Rajasthan")
        product = make_product("Test", [{"field": "state", "operator": "IN", "value": ["Rajasthan", "Gujarat"]}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE

    def test_in_fail(self):
        profile = make_profile(state="Kerala")
        product = make_product("Test", [{"field": "state", "operator": "IN", "value": ["Rajasthan", "Gujarat"]}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.INELIGIBLE

    def test_not_in_pass(self):
        profile = make_profile(category="General")
        product = make_product("Test", [{"field": "category", "operator": "NOT_IN", "value": ["SC", "ST"]}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE

    def test_gt_pass(self):
        profile = make_profile(loan_amount=600000)
        product = make_product("Test", [{"field": "loan_amount", "operator": ">", "value": 500000}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE

    def test_lt_pass(self):
        profile = make_profile(loan_amount=400000)
        product = make_product("Test", [{"field": "loan_amount", "operator": "<", "value": 500000}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE


# ─── Three-State Tests ────────────────────────────────────────────────────────

class TestThreeState:
    def test_eligible_all_rules_pass(self):
        profile = make_profile(age=32, is_npa=False, state="Rajasthan")
        product = make_product("MUDRA", [
            {"field": "age", "operator": ">=", "value": 18},
            {"field": "age", "operator": "<=", "value": 65},
            {"field": "is_npa", "operator": "!=", "value": True},
        ])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE
        assert all(r.passed for r in result.rule_results)

    def test_ineligible_one_rule_fails(self):
        profile = make_profile(age=17, is_npa=False)
        product = make_product("MUDRA", [
            {"field": "age", "operator": ">=", "value": 18},
            {"field": "is_npa", "operator": "!=", "value": True},
        ])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.INELIGIBLE

    def test_needs_review_missing_field(self):
        """Missing required field → NEEDS_REVIEW, not ELIGIBLE or INELIGIBLE."""
        profile = make_profile()  # age is None
        product = make_product("Test", [{"field": "age", "operator": ">=", "value": 18}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.NEEDS_REVIEW
        assert len(result.needs_review_reasons) > 0

    def test_needs_review_low_confidence(self):
        """Low confidence extracted field → NEEDS_REVIEW."""
        profile = make_profile(
            monthly_income=ExtractedField(
                value=40000,
                confidence=0.54,  # Below 0.75 threshold
                source_type=DataSourceType.LLM_INTERPRETATION,
            )
        )
        product = make_product("Test", [
            {"field": "monthly_income", "operator": ">=", "value": 30000}
        ])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.NEEDS_REVIEW
        assert any("confidence" in r.lower() for r in result.needs_review_reasons)

    def test_eligible_high_confidence_extracted_field(self):
        """High confidence extracted field → evaluates normally."""
        profile = make_profile(
            monthly_income=ExtractedField(
                value=40000,
                confidence=0.94,  # Above 0.75 threshold
                source_type=DataSourceType.LLM_INTERPRETATION,
            )
        )
        product = make_product("Test", [
            {"field": "monthly_income", "operator": ">=", "value": 30000}
        ])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE


# ─── Safety Tests ─────────────────────────────────────────────────────────────

class TestSafety:
    def test_unknown_operator_needs_review(self):
        """Unknown operator must not return ELIGIBLE — must be NEEDS_REVIEW."""
        profile = make_profile(age=25)
        product = make_product("Test", [{"field": "age", "operator": "REGEX", "value": ".*"}])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.NEEDS_REVIEW

    def test_empty_rules_eligible(self):
        """No rules → ELIGIBLE (no restrictions)."""
        profile = make_profile(age=25)
        product = make_product("Test", [])
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE

    def test_no_products_returns_empty(self):
        profile = make_profile(age=25)
        results = evaluate_products(profile, [])
        assert results == []


# ─── Multi-Product Tests ──────────────────────────────────────────────────────

class TestMultiProduct:
    def test_mudra_tarun_eligible(self):
        """Ravi Kumar demo case — should be eligible for MUDRA Tarun."""
        profile = make_profile(
            age=32,
            is_npa=False,
            loan_amount=500000,
            state="Rajasthan",
            occupation="shopkeeper",
        )
        product = {
            "id": "mudra-tarun",
            "name": "MUDRA Tarun",
            "type": "business_loan",
            "rules": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "age", "operator": "<=", "value": 65},
                {"field": "is_npa", "operator": "!=", "value": True},
            ],
            "required_documents": [],
        }
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.ELIGIBLE

    def test_ineligible_npa(self):
        """Suresh Patel demo case — NPA → INELIGIBLE for MUDRA."""
        profile = make_profile(age=45, is_npa=True, loan_amount=200000)
        product = {
            "id": "mudra-kishor",
            "name": "MUDRA Kishor",
            "type": "business_loan",
            "rules": [
                {"field": "age", "operator": ">=", "value": 18},
                {"field": "is_npa", "operator": "!=", "value": True},
            ],
            "required_documents": [],
        }
        result = evaluate_product(profile, product)
        assert result.status == EligibilityStatus.INELIGIBLE
        failed = [r for r in result.rule_results if r.passed is False]
        assert len(failed) == 1
        assert failed[0].rule.field == "is_npa"
