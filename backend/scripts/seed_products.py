"""
Seed financial products with real eligibility rules.

Products seeded (with sources from official documents):
1. MUDRA Loan — Tarun (₹5L–₹10L)
2. MUDRA Loan — Kishor (₹50K–₹5L)  
3. PM SVANidhi — Street Vendor Credit
4. Stand-Up India Scheme
5. PM Fasal Bima Yojana (Crop Insurance)

Run: python scripts/seed_products.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from app.core.database import get_supabase_admin

PRODUCTS = [
    {
        "name": "MUDRA Loan — Tarun Category",
        "type": "business_loan",
        "min_amount": 500001,
        "max_amount": 1000000,
        "active_version": 1,
        "rules": [
            {
                "field": "age",
                "operator": ">=",
                "value": 18,
                "source_url": "https://www.mudra.org.in/",
                "authority": "MUDRA (Ministry of Finance)",
                "document_title": "MUDRA Loan Eligibility",
                "last_verified": "2026-09-11",
            },
            {
                "field": "age",
                "operator": "<=",
                "value": 65,
                "source_url": "https://www.mudra.org.in/",
                "authority": "MUDRA (Ministry of Finance)",
                "document_title": "MUDRA Loan Eligibility",
                "last_verified": "2026-09-11",
            },
            {
                "field": "is_npa",
                "operator": "!=",
                "value": True,
                "source_url": "https://www.mudra.org.in/",
                "authority": "MUDRA (Ministry of Finance)",
                "document_title": "MUDRA Eligibility — No Existing Bank Default",
                "last_verified": "2026-09-11",
            },
        ],
        "required_documents": [
            {"type": "pan_card", "label": "PAN Card"},
            {"type": "bank_statement", "label": "Bank Statement (6 months)"},
            {"type": "business_registration", "label": "Business Registration/Udyam Certificate"},
            {"type": "gst_certificate", "label": "GST Certificate (if applicable)"},
            {"type": "income_tax_return", "label": "Income Tax Return (latest)"},
        ],
        "source_metadata": {
            "authority": "MUDRA / Ministry of Finance",
            "source_url": "https://www.mudra.org.in/",
            "description": "Micro Units Development & Refinance Agency loan for micro enterprises",
            "interest_rate_note": "Interest rates set by lending banks — MUDRA does not specify fixed rates. Contact your bank.",
            "last_verified": "2026-09-11",
        },
    },
    {
        "name": "MUDRA Loan — Kishor Category",
        "type": "business_loan",
        "min_amount": 50001,
        "max_amount": 500000,
        "active_version": 1,
        "rules": [
            {
                "field": "age",
                "operator": ">=",
                "value": 18,
                "source_url": "https://www.mudra.org.in/",
                "authority": "MUDRA (Ministry of Finance)",
                "document_title": "MUDRA Loan Eligibility",
                "last_verified": "2026-09-11",
            },
            {
                "field": "is_npa",
                "operator": "!=",
                "value": True,
                "source_url": "https://www.mudra.org.in/",
                "authority": "MUDRA (Ministry of Finance)",
                "document_title": "MUDRA Eligibility — No Existing Bank Default",
                "last_verified": "2026-09-11",
            },
        ],
        "required_documents": [
            {"type": "pan_card", "label": "PAN Card"},
            {"type": "bank_statement", "label": "Bank Statement (6 months)"},
            {"type": "business_registration", "label": "Business Registration/Udyam Certificate"},
        ],
        "source_metadata": {
            "authority": "MUDRA / Ministry of Finance",
            "source_url": "https://www.mudra.org.in/",
            "description": "MUDRA Kishor: ₹50,001 to ₹5,00,000 for established micro enterprises",
            "last_verified": "2026-09-11",
        },
    },
    {
        "name": "PM SVANidhi — Street Vendor Credit",
        "type": "micro_credit",
        "min_amount": 10000,
        "max_amount": 50000,
        "active_version": 1,
        "rules": [
            {
                "field": "occupation",
                "operator": "IN",
                "value": ["street_vendor", "vendor", "hawker", "street vendor", "mobile vendor"],
                "source_url": "https://pmsvanidhi.mohua.gov.in/",
                "authority": "Ministry of Housing and Urban Affairs",
                "document_title": "PM SVANidhi Scheme Guidelines",
                "last_verified": "2026-09-11",
            },
            {
                "field": "age",
                "operator": ">=",
                "value": 18,
                "source_url": "https://pmsvanidhi.mohua.gov.in/",
                "authority": "Ministry of Housing and Urban Affairs",
                "document_title": "PM SVANidhi Eligibility",
                "last_verified": "2026-09-11",
            },
        ],
        "required_documents": [
            {"type": "aadhaar", "label": "Aadhaar Card"},
            {"type": "pan_card", "label": "PAN Card"},
            {"type": "bank_statement", "label": "Bank Account (for disbursement)"},
        ],
        "source_metadata": {
            "authority": "Ministry of Housing and Urban Affairs",
            "source_url": "https://pmsvanidhi.mohua.gov.in/",
            "description": "PM Street Vendor's AtmaNirbhar Nidhi — working capital loans for street vendors",
            "interest_rate_note": "7% interest subsidy available. Check scheme portal for current rates.",
            "last_verified": "2026-09-11",
        },
    },
    {
        "name": "Stand-Up India Scheme",
        "type": "business_loan",
        "min_amount": 1000000,
        "max_amount": 10000000,
        "active_version": 1,
        "rules": [
            {
                "field": "age",
                "operator": ">=",
                "value": 18,
                "source_url": "https://www.standupmitra.in/",
                "authority": "SIDBI / Ministry of Finance",
                "document_title": "Stand-Up India Scheme Guidelines",
                "last_verified": "2026-09-11",
            },
            {
                "field": "category",
                "operator": "IN",
                "value": ["SC", "ST", "Woman", "woman", "female"],
                "source_url": "https://www.standupmitra.in/",
                "authority": "SIDBI / Ministry of Finance",
                "document_title": "Stand-Up India — SC/ST/Women Eligibility",
                "last_verified": "2026-09-11",
            },
            {
                "field": "is_npa",
                "operator": "!=",
                "value": True,
                "source_url": "https://www.standupmitra.in/",
                "authority": "SIDBI / Ministry of Finance",
                "document_title": "Stand-Up India Eligibility — No NPA",
                "last_verified": "2026-09-11",
            },
        ],
        "required_documents": [
            {"type": "pan_card", "label": "PAN Card"},
            {"type": "aadhaar", "label": "Aadhaar Card"},
            {"type": "bank_statement", "label": "Bank Statement (12 months)"},
            {"type": "business_registration", "label": "Business Registration"},
            {"type": "income_tax_return", "label": "Income Tax Return (3 years)"},
            {"type": "gst_return", "label": "GST Returns"},
        ],
        "source_metadata": {
            "authority": "SIDBI / Ministry of Finance",
            "source_url": "https://www.standupmitra.in/",
            "description": "Loans for SC/ST and women entrepreneurs for greenfield enterprises",
            "last_verified": "2026-09-11",
        },
    },
    {
        "name": "PM Fasal Bima Yojana — Crop Insurance",
        "type": "insurance",
        "min_amount": 0,
        "max_amount": 0,
        "active_version": 1,
        "rules": [
            {
                "field": "occupation",
                "operator": "IN",
                "value": ["farmer", "kisan", "agriculturist", "agriculture", "farming"],
                "source_url": "https://pmfby.gov.in/",
                "authority": "Ministry of Agriculture & Farmers Welfare",
                "document_title": "PM Fasal Bima Yojana Guidelines",
                "last_verified": "2026-09-11",
            },
        ],
        "required_documents": [
            {"type": "aadhaar", "label": "Aadhaar Card"},
            {"type": "bank_statement", "label": "Bank Account"},
            {"type": "pan_card", "label": "PAN Card"},
        ],
        "source_metadata": {
            "authority": "Ministry of Agriculture & Farmers Welfare",
            "source_url": "https://pmfby.gov.in/",
            "description": "Pradhan Mantri Fasal Bima Yojana — crop insurance scheme for farmers",
            "last_verified": "2026-09-11",
        },
    },
]


def main():
    print("Seeding financial products...")
    db = get_supabase_admin()

    seeded = 0
    skipped = 0

    for product in PRODUCTS:
        # Check if already exists by name
        res = db.table("products").select("id").eq("name", product["name"]).execute()
        if res.data:
            print(f"  [skip] Already exists: {product['name']}")
            skipped += 1
            continue

        db.table("products").insert(product).execute()
        print(f"  [OK] Seeded: {product['name']}")
        seeded += 1

    print(f"\nDone. Seeded: {seeded} products, Skipped: {skipped} (already existed)")
    print("\nReal users are created automatically when someone uses the app.")
    print("No demo/fake users needed.")


if __name__ == "__main__":
    main()
