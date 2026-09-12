"""
Seed the sources registry table with all known financial information sources.

P0 sources (crawl_enabled=True): 12 sources approved for immediate crawl.
All others: crawl_enabled=False — metadata only until P0 is demo-solid.

See: obsidian-vault/03_KNOWLEDGE/Source Registry.md for rationale.

Run: python scripts/seed_sources.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from app.core.database import get_supabase_admin

db = get_supabase_admin()

# ─── ALL SOURCES ──────────────────────────────────────────────────────────────
# crawl_enabled=True ONLY for P0 approved sources.
# Source of truth: 03_KNOWLEDGE/Source Registry.md

ALL_SOURCES = [

    # ═══════════════════════════════════════════════════
    # P0 ENABLED — RBI / Government / Top Banks
    # ═══════════════════════════════════════════════════

    {
        "name": "RBI Master Directions",
        "category": "regulatory",
        "authority_level": 1,
        "base_url": "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx",
        "crawl_enabled": True,
        "product_data": False,
        "regulatory_data": True,
        "scheme_data": False,
        "document_data": False,
        "crawl_subpaths": [
            "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx",
            "https://www.rbi.org.in/Scripts/NotificationUser.aspx",
            "https://www.rbi.org.in/Scripts/FAQView.aspx",
        ],
        "crawl_exclude_patterns": [],
        "refresh_days": 7,
        "notes": "P0: Primary lending regulator. Master Directions consolidate regulatory instructions.",
    },
    {
        "name": "myScheme.gov.in",
        "category": "govt_scheme",
        "authority_level": 2,
        "base_url": "https://www.myscheme.gov.in",
        "crawl_enabled": True,
        "product_data": False,
        "regulatory_data": False,
        "scheme_data": True,
        "document_data": False,
        "crawl_subpaths": [
            "https://www.myscheme.gov.in/schemes",
            "https://www.myscheme.gov.in/search",
        ],
        "crawl_exclude_patterns": ["login", "register", "profile"],
        "refresh_days": 14,
        "notes": "P0: One-stop government scheme discovery. Has eligibility data for 3000+ schemes.",
    },
    {
        "name": "Pradhan Mantri Awas Yojana (PMAY-U)",
        "category": "housing_finance",
        "authority_level": 2,
        "base_url": "https://pmay-urban.gov.in",
        "crawl_enabled": True,
        "product_data": False,
        "regulatory_data": False,
        "scheme_data": True,
        "document_data": True,
        "crawl_subpaths": [
            "https://pmay-urban.gov.in/",
            "https://pmaymis.gov.in/",
        ],
        "crawl_exclude_patterns": ["login", "admin", "report"],
        "refresh_days": 7,
        "notes": "P0: Official source for PMAY-Urban housing scheme.",
    },
    {
        "name": "DFS Schemes and Services",
        "category": "govt_scheme",
        "authority_level": 2,
        "base_url": "https://financialservices.gov.in",
        "crawl_enabled": True,
        "product_data": False,
        "regulatory_data": False,
        "scheme_data": True,
        "document_data": False,
        "crawl_subpaths": [
            "https://financialservices.gov.in/schemes-and-services",
            "https://financialservices.gov.in/banking",
        ],
        "crawl_exclude_patterns": ["login", "admin"],
        "refresh_days": 14,
        "notes": "P0: PMJDY, PMMY, APY, PMJJBY, PMSBY, Stand-Up India, JanSamarth listed here.",
    },
    {
        "name": "State Bank of India",
        "category": "bank_psb",
        "authority_level": 3,
        "base_url": "https://sbi.co.in",
        "crawl_enabled": True,
        "product_data": True,
        "regulatory_data": False,
        "scheme_data": False,
        "document_data": False,
        "crawl_subpaths": [
            "https://sbi.co.in/web/business/loans",
            "https://sbi.co.in/web/business/msme",
            "https://sbi.co.in/web/personal-banking/loans",
            "https://sbi.co.in/web/agri-rural/agriculture-banking/loan",
            "https://sbi.co.in/web/interest-rates/interest-rates",
        ],
        "crawl_exclude_patterns": ["news", "press-release", "career", "contact", "feedback", "nri"],
        "refresh_days": 30,
        "notes": "P0: Largest PSB by volume. Focus: business/MSME/agri loans, interest rates, eligibility.",
    },
    {
        "name": "HDFC Bank",
        "category": "bank_private",
        "authority_level": 3,
        "base_url": "https://www.hdfcbank.com",
        "crawl_enabled": True,
        "product_data": True,
        "regulatory_data": False,
        "scheme_data": False,
        "document_data": False,
        "crawl_subpaths": [
            "https://www.hdfcbank.com/sme",
            "https://www.hdfcbank.com/content/bbp/repositories/723fb80a-2dde-42a3-9793-7ae1be57c87f",
            "https://www.hdfcbank.com/personal/borrow",
            "https://www.hdfcbank.com/msme-banking",
        ],
        "crawl_exclude_patterns": ["news", "media", "career", "csr", "investor"],
        "refresh_days": 30,
        "notes": "P0: Largest private bank. Strong MSME + business loan portfolio.",
    },
    {
        "name": "ICICI Bank",
        "category": "bank_private",
        "authority_level": 3,
        "base_url": "https://www.icicibank.com",
        "crawl_enabled": True,
        "product_data": True,
        "regulatory_data": False,
        "scheme_data": False,
        "document_data": False,
        "crawl_subpaths": [
            "https://www.icicibank.com/business-banking",
            "https://www.icicibank.com/personal-banking/loans",
            "https://www.icicibank.com/msme",
        ],
        "crawl_exclude_patterns": ["news", "media", "career", "investor", "nri"],
        "refresh_days": 30,
        "notes": "P0: Major MSME + business loan provider. Good eligibility pages.",
    },
    {
        "name": "Punjab National Bank",
        "category": "bank_psb",
        "authority_level": 3,
        "base_url": "https://www.pnbindia.in",
        "crawl_enabled": True,
        "product_data": True,
        "regulatory_data": False,
        "scheme_data": False,
        "document_data": False,
        "crawl_subpaths": [
            "https://www.pnbindia.in/msme-loans.html",
            "https://www.pnbindia.in/agriculture-loans.html",
            "https://www.pnbindia.in/personal-loans.html",
            "https://www.pnbindia.in/business-loans.html",
            "https://www.pnbindia.in/interest-rates.html",
        ],
        "crawl_exclude_patterns": ["news", "press", "career", "tender"],
        "refresh_days": 30,
        "notes": "P0: PSB with strong north India + rural coverage. Selected for geographic balance.",
    },
    {
        "name": "Bank of Baroda",
        "category": "bank_psb",
        "authority_level": 3,
        "base_url": "https://www.bankofbaroda.in",
        "crawl_enabled": True,
        "product_data": True,
        "regulatory_data": False,
        "scheme_data": False,
        "document_data": False,
        "crawl_subpaths": [
            "https://www.bankofbaroda.in/business-banking/msme-loans",
            "https://www.bankofbaroda.in/personal-banking/loans",
            "https://www.bankofbaroda.in/agriculture-banking",
            "https://www.bankofbaroda.in/interest-rates",
        ],
        "crawl_exclude_patterns": ["news", "media", "career", "investor"],
        "refresh_days": 30,
        "notes": "P0: PSB with strong MSME + agri focus. Large rural branch network.",
    },
    {
        "name": "AU Small Finance Bank",
        "category": "sfb",
        "authority_level": 3,
        "base_url": "https://www.aubank.in",
        "crawl_enabled": True,
        "product_data": True,
        "regulatory_data": False,
        "scheme_data": False,
        "document_data": False,
        "crawl_subpaths": [
            "https://www.aubank.in/business-loans",
            "https://www.aubank.in/personal-loans",
            "https://www.aubank.in/msme",
        ],
        "crawl_exclude_patterns": ["career", "investor", "media"],
        "refresh_days": 30,
        "notes": "P0: Leading SFB. Best microfinance + MSME product coverage among SFBs.",
    },
    {
        "name": "PMEGP Portal",
        "category": "government",
        "authority_level": 2,
        "base_url": "https://pmegp.msme.gov.in",
        "crawl_enabled": True,
        "product_data": False,
        "regulatory_data": False,
        "scheme_data": True,
        "document_data": False,
        "crawl_subpaths": [
            "https://pmegp.msme.gov.in/",
            "https://pmegp.msme.gov.in/Public/PMEGP.aspx",
        ],
        "crawl_exclude_patterns": ["login", "admin", "report"],
        "refresh_days": 14,
        "notes": "P0: Employment-generation financing scheme. Eligibility and subsidy details.",
    },
    {
        "name": "CGTMSE",
        "category": "government",
        "authority_level": 2,
        "base_url": "https://www.cgtmse.in",
        "crawl_enabled": True,
        "product_data": False,
        "regulatory_data": False,
        "scheme_data": True,
        "document_data": False,
        "crawl_subpaths": [
            "https://www.cgtmse.in/",
            "https://www.cgtmse.in/Guarantee.aspx",
        ],
        "crawl_exclude_patterns": ["login", "member"],
        "refresh_days": 30,
        "notes": "P0: Credit guarantee for MSME loans. Required for business loan eligibility.",
    },
    {
        "name": "Stand-Up India / Standupmitra",
        "category": "government",
        "authority_level": 2,
        "base_url": "https://www.standupmitra.in",
        "crawl_enabled": True,
        "product_data": False,
        "regulatory_data": False,
        "scheme_data": True,
        "document_data": False,
        "crawl_subpaths": [
            "https://www.standupmitra.in/",
            "https://www.standupmitra.in/Home/SUISchemes",
        ],
        "crawl_exclude_patterns": ["login", "register"],
        "refresh_days": 14,
        "notes": "P0: SC/ST/women entrepreneur loans. Already partially ingested as CACHED_REAL.",
    },

    # ═══════════════════════════════════════════════════
    # DEFERRED — Public Sector Banks (remaining)
    # ═══════════════════════════════════════════════════

    {"name": "Bank of India", "category": "bank_psb", "authority_level": 3, "base_url": "https://bankofindia.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred: P0 PSBs cover majority of use cases."},
    {"name": "Bank of Maharashtra", "category": "bank_psb", "authority_level": 3, "base_url": "https://www.bankofmaharashtra.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Canara Bank", "category": "bank_psb", "authority_level": 3, "base_url": "https://canarabank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Central Bank of India", "category": "bank_psb", "authority_level": 3, "base_url": "https://www.centralbankofindia.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Indian Bank", "category": "bank_psb", "authority_level": 3, "base_url": "https://www.indianbank.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Indian Overseas Bank", "category": "bank_psb", "authority_level": 3, "base_url": "https://www.iob.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Punjab & Sind Bank", "category": "bank_psb", "authority_level": 3, "base_url": "https://punjabandsindbank.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "UCO Bank", "category": "bank_psb", "authority_level": 3, "base_url": "https://www.ucobank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Union Bank of India", "category": "bank_psb", "authority_level": 3, "base_url": "https://www.unionbankofindia.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},

    # ═══════════════════════════════════════════════════
    # DEFERRED — Private Banks
    # ═══════════════════════════════════════════════════

    {"name": "Axis Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.axisbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Bandhan Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.bandhanbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "CSB Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.csb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "City Union Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.cityunionbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "DCB Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.dcbbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Dhanlaxmi Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.dhanbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Federal Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.federalbank.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "IndusInd Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.indusind.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "IDFC FIRST Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.idfcfirstbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Jammu & Kashmir Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.jkbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Karnataka Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://karnatakabank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Karur Vysya Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.kvb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Kotak Mahindra Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.kotak.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Nainital Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.nainitalbank.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "RBL Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.rblbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "South Indian Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.southindianbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Tamilnad Mercantile Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.tmb.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "YES Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.yesbank.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "IDBI Bank", "category": "bank_private", "authority_level": 3, "base_url": "https://www.idbibank.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},

    # ═══════════════════════════════════════════════════
    # DEFERRED — Small Finance Banks (remaining 10)
    # ═══════════════════════════════════════════════════

    {"name": "Capital Small Finance Bank", "category": "sfb", "authority_level": 3, "base_url": "https://www.capitalbank.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Equitas Small Finance Bank", "category": "sfb", "authority_level": 3, "base_url": "https://www.equitasbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "ESAF Small Finance Bank", "category": "sfb", "authority_level": 3, "base_url": "https://www.esafbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Suryoday Small Finance Bank", "category": "sfb", "authority_level": 3, "base_url": "https://www.suryodaybank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Ujjivan Small Finance Bank", "category": "sfb", "authority_level": 3, "base_url": "https://www.ujjivansfb.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Utkarsh Small Finance Bank", "category": "sfb", "authority_level": 3, "base_url": "https://utkarsh.bank", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "slice SFB", "category": "sfb", "authority_level": 3, "base_url": "https://www.sliceit.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Jana Small Finance Bank", "category": "sfb", "authority_level": 3, "base_url": "https://www.janabank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Shivalik Small Finance Bank", "category": "sfb", "authority_level": 3, "base_url": "https://www.shivalikbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Unity Small Finance Bank", "category": "sfb", "authority_level": 3, "base_url": "https://www.unitybank.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},

    # ═══════════════════════════════════════════════════
    # DEFERRED — Payments Banks
    # ═══════════════════════════════════════════════════

    {"name": "India Post Payments Bank", "category": "payments_bank", "authority_level": 3, "base_url": "https://www.ippbonline.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Fino Payments Bank", "category": "payments_bank", "authority_level": 3, "base_url": "https://www.finobank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Airtel Payments Bank", "category": "payments_bank", "authority_level": 3, "base_url": "https://www.airtel.in/bank", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "NSDL Payments Bank", "category": "payments_bank", "authority_level": 3, "base_url": "https://nsdlbank.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Paytm Payments Bank", "category": "payments_bank", "authority_level": 5, "base_url": "https://www.paytmbank.com", "crawl_enabled": False, "product_data": False, "notes": "Reference only. RBI banking licence cancelled. Do not use for product discovery."},

    # ═══════════════════════════════════════════════════
    # DEFERRED — Regional Rural Banks (28)
    # ═══════════════════════════════════════════════════

    {"name": "Andhra Pradesh Grameena Bank", "category": "rrb", "authority_level": 3, "base_url": "https://apgb.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred. Crawl via DFS RRB directory."},
    {"name": "Arunachal Pradesh Rural Bank", "category": "rrb", "authority_level": 3, "base_url": "https://aprb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Assam Gramin Vikas Bank", "category": "rrb", "authority_level": 3, "base_url": "https://agvb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Bihar Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://bihargb.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Chhattisgarh Rajya Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://crgbank.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Gujarat Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://gujaratgrameen.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Sarva Haryana Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://shgb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Himachal Pradesh Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://hpgb.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "J&K Grameen Bank", "category": "rrb", "authority_level": 3, "base_url": "https://jkgb.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Jharkhand Rajya Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://jrgb.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Karnataka Grameena Bank", "category": "rrb", "authority_level": 3, "base_url": "https://karnatakagb.com", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Kerala Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://keralagb.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "MP Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://mpgb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Maharashtra Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://mahagramin.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Manipur Rural Bank", "category": "rrb", "authority_level": 3, "base_url": "https://manipurrural.bank", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Meghalaya Rural Bank", "category": "rrb", "authority_level": 3, "base_url": "https://meghalayaruralbank.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Mizoram Rural Bank", "category": "rrb", "authority_level": 3, "base_url": "https://mrb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Nagaland Rural Bank", "category": "rrb", "authority_level": 3, "base_url": "https://nagalandrb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Odisha Grameen Bank", "category": "rrb", "authority_level": 3, "base_url": "https://odishabank.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Puducherry Grama Bank", "category": "rrb", "authority_level": 3, "base_url": "https://pygb.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Punjab Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://pgb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Rajasthan Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://rgb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Tamil Nadu Grama Bank", "category": "rrb", "authority_level": 3, "base_url": "https://tngb.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Telangana Grameena Bank", "category": "rrb", "authority_level": 3, "base_url": "https://tgbhyd.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Tripura Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://tripuragramin.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "UP Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://upgb.bank", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "Uttarakhand Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://ukgb.org", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},
    {"name": "West Bengal Gramin Bank", "category": "rrb", "authority_level": 3, "base_url": "https://wbgb.bank", "crawl_enabled": False, "product_data": True, "notes": "Deferred."},

    # ═══════════════════════════════════════════════════
    # DEFERRED — Regulatory (non-RBI)
    # ═══════════════════════════════════════════════════

    {"name": "IRDAI", "category": "insurance", "authority_level": 1, "base_url": "https://irdai.gov.in", "crawl_enabled": False, "regulatory_data": True, "notes": "Deferred. P1+ for insurance eligibility."},
    {"name": "PFRDA", "category": "pension", "authority_level": 1, "base_url": "https://www.pfrda.org.in", "crawl_enabled": False, "regulatory_data": True, "notes": "Deferred. P1+ for pension products."},
    {"name": "SEBI", "category": "securities", "authority_level": 1, "base_url": "https://www.sebi.gov.in", "crawl_enabled": False, "regulatory_data": True, "notes": "Deferred. P2+ for investment products."},
    {"name": "IFSCA", "category": "regulatory", "authority_level": 1, "base_url": "https://ifsca.gov.in", "crawl_enabled": False, "regulatory_data": True, "notes": "Deferred. GIFT IFSC reference only."},

    # ═══════════════════════════════════════════════════
    # DEFERRED — Government (additional)
    # ═══════════════════════════════════════════════════

    {"name": "India.gov.in", "category": "government", "authority_level": 2, "base_url": "https://www.india.gov.in", "crawl_enabled": False, "scheme_data": True, "notes": "Deferred. Master government portal."},
    {"name": "JanSamarth", "category": "government", "authority_level": 2, "base_url": "https://www.jansamarth.in", "crawl_enabled": False, "scheme_data": True, "notes": "Deferred. Credit-linked government schemes."},
    {"name": "MSME Ministry", "category": "msme", "authority_level": 2, "base_url": "https://msme.gov.in", "crawl_enabled": False, "scheme_data": True, "notes": "Deferred. P1 for full MSME scheme coverage."},
    {"name": "Udyam Registration", "category": "government", "authority_level": 2, "base_url": "https://udyamregistration.gov.in", "crawl_enabled": False, "document_data": True, "notes": "Deferred. MSME registration reference."},
    {"name": "NPCI", "category": "government", "authority_level": 2, "base_url": "https://www.npci.org.in", "crawl_enabled": False, "regulatory_data": True, "notes": "Deferred. P1 for payment/UPI grievance RAG."},
    {"name": "DigiLocker", "category": "government", "authority_level": 2, "base_url": "https://www.digilocker.gov.in", "crawl_enabled": False, "document_data": True, "notes": "Deferred. P1 for document help RAG."},
    {"name": "UIDAI", "category": "government", "authority_level": 2, "base_url": "https://uidai.gov.in", "crawl_enabled": False, "document_data": True, "notes": "Deferred. Aadhaar reference."},
    {"name": "Income Tax India", "category": "government", "authority_level": 2, "base_url": "https://www.incometax.gov.in", "crawl_enabled": False, "document_data": True, "notes": "Deferred. PAN/ITR reference."},
    {"name": "GST Portal", "category": "government", "authority_level": 2, "base_url": "https://www.gst.gov.in", "crawl_enabled": False, "document_data": True, "notes": "Deferred. GST reference."},

    # ═══════════════════════════════════════════════════
    # DEFERRED — Development Financial Institutions
    # ═══════════════════════════════════════════════════

    {"name": "SIDBI", "category": "government", "authority_level": 2, "base_url": "https://www.sidbi.in", "crawl_enabled": False, "scheme_data": True, "product_data": True, "notes": "Deferred. P1 for MSME refinance schemes."},
    {"name": "NABARD", "category": "government", "authority_level": 2, "base_url": "https://www.nabard.org", "crawl_enabled": False, "scheme_data": True, "notes": "Deferred. Agriculture/rural finance."},
    {"name": "NHB", "category": "government", "authority_level": 2, "base_url": "https://www.nhb.org.in", "crawl_enabled": False, "scheme_data": True, "notes": "Deferred. Housing finance."},
    {"name": "EXIM Bank", "category": "government", "authority_level": 2, "base_url": "https://www.eximbankindia.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred. Export/import finance."},

    # ═══════════════════════════════════════════════════
    # DEFERRED — Foreign Banks (reference only)
    # ═══════════════════════════════════════════════════

    {"name": "DBS India", "category": "foreign_bank", "authority_level": 4, "base_url": "https://www.dbs.com/in", "crawl_enabled": False, "product_data": True, "notes": "Deferred. Foreign bank reference."},
    {"name": "HSBC India", "category": "foreign_bank", "authority_level": 4, "base_url": "https://www.hsbc.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred. Foreign bank reference."},
    {"name": "Standard Chartered India", "category": "foreign_bank", "authority_level": 4, "base_url": "https://www.sc.com/in", "crawl_enabled": False, "product_data": True, "notes": "Deferred. Foreign bank reference."},
    {"name": "Citibank India", "category": "foreign_bank", "authority_level": 4, "base_url": "https://www.online.citibank.co.in", "crawl_enabled": False, "product_data": True, "notes": "Deferred. Foreign bank reference."},
]


def main():
    print("Seeding sources registry...")
    print(f"Total sources: {len(ALL_SOURCES)}")
    p0 = sum(1 for s in ALL_SOURCES if s.get("crawl_enabled", False))
    print(f"P0 enabled (crawl_enabled=True): {p0}")
    print(f"Deferred (crawl_enabled=False): {len(ALL_SOURCES) - p0}")
    print()

    inserted = 0
    skipped = 0
    errors = 0

    for source in ALL_SOURCES:
        # Check if already exists by base_url
        existing = db.table("sources").select("id, name").eq("base_url", source["base_url"]).execute()
        if existing.data:
            print(f"  [SKIP] Already exists: {source['name']}")
            skipped += 1
            continue

        # Build insert record with defaults
        record = {
            "name": source["name"],
            "category": source["category"],
            "authority_level": source["authority_level"],
            "base_url": source["base_url"],
            "crawl_enabled": source.get("crawl_enabled", False),
            "product_data": source.get("product_data", False),
            "regulatory_data": source.get("regulatory_data", False),
            "scheme_data": source.get("scheme_data", False),
            "document_data": source.get("document_data", False),
            "crawl_subpaths": source.get("crawl_subpaths", []),
            "crawl_exclude_patterns": source.get("crawl_exclude_patterns", []),
            "refresh_days": source.get("refresh_days", 30),
            "last_crawl_status": "PENDING",
            "chunks_count": 0,
            "notes": source.get("notes", ""),
        }

        try:
            db.table("sources").insert(record).execute()
            flag = "[P0]" if source.get("crawl_enabled") else "    "
            print(f"  {flag} {source['name']} ({source['category']})")
            inserted += 1
        except Exception as e:
            print(f"  [ERR] {source['name']}: {e}")
            errors += 1

    print()
    print("=" * 50)
    print(f"Done. Inserted: {inserted} | Skipped: {skipped} | Errors: {errors}")
    print(f"P0 enabled sources: {p0}")
    print("=" * 50)


if __name__ == "__main__":
    main()
