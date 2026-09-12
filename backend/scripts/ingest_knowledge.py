"""
Knowledge ingestion script.

Ingests trusted financial source content into Supabase pgvector for RAG retrieval.

Strategy:
- Use Firecrawl to fetch official scheme pages (if API key configured)
- Fall back to manually provided content if Firecrawl fails/quota exceeded
- Chunk content (~500 words with overlap)
- Embed using Gemini text-embedding-004 (HTTP-only, no torch required)
- Store in Supabase knowledge table with vector(384)

Run: python scripts/ingest_knowledge.py

IMPORTANT: Only run once (or when refreshing sources).
Do NOT run on every user request — knowledge is pre-ingested.

EMBEDDING BACKEND CHANGE (2026-09-11):
Previously used sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2).
Replaced with Gemini text-embedding-004 because torch DLL is blocked by
Windows Application Control policy on this machine.
Gemini outputs outputDimensionality=384 to match existing vector(384) schema.
"""
import sys
import os
import hashlib
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from app.core.database import get_supabase_admin
from app.services.knowledge.rag import embed_text

# ─── Manually curated fallback content (used when Firecrawl unavailable) ──────
# This is REAL content from official sources — NOT invented by the LLM.

MANUAL_KNOWLEDGE = [
    {
        "title": "MUDRA Loan — Tarun Category Eligibility",
        "authority": "MUDRA / Ministry of Finance",
        "source_url": "https://www.mudra.org.in/",
        "source_type": "official_scheme",
        "content": """MUDRA (Micro Units Development & Refinance Agency) provides loans under three categories:
        
Shishu: Up to ₹50,000
Kishor: ₹50,001 to ₹5,00,000  
Tarun: ₹5,00,001 to ₹10,00,000

Eligibility for MUDRA Loans:
- Age: 18 to 65 years
- Indian citizen
- Non-farm income generating business (manufacturing, trading, services)
- No existing loan default / NPA (Non-Performing Asset) with any bank
- Business must be in the non-corporate, non-farm sector
- Can be applied through any scheduled commercial bank, RRB, Small Finance Bank, Cooperative Bank, MFI, or NBFC

Documents typically required:
- Identity proof (Aadhaar, PAN, Voter ID)
- Address proof
- Business proof / Udyam Registration Certificate
- Bank statement (6-12 months)
- Last 2 years IT returns (for larger amounts)
- GST certificate (if applicable)
- Quotation of machinery/equipment (if applicable)

Key features:
- No collateral required for loans up to ₹10 lakh
- Interest rates set by the lending institution (not fixed by MUDRA)
- Repayment tenure: up to 5 years
- MUDRA Card (RuPay debit card) provided for working capital needs

Source: Official MUDRA website (mudra.org.in). Last verified 2026-09-11.""",
        "page_number": None,
    },
    {
        "title": "PM SVANidhi — Street Vendor Loan Scheme",
        "authority": "Ministry of Housing and Urban Affairs",
        "source_url": "https://pmsvanidhi.mohua.gov.in/",
        "source_type": "official_scheme",
        "content": """PM Street Vendor's AtmaNirbhar Nidhi (PM SVANidhi) provides collateral-free working capital loans to street vendors.

Eligibility:
- Street vendors who were vending on or before 24th March 2020
- Must have: Vending Certificate / Identity Card issued by Urban Local Body (ULB), OR
  Letter of Recommendation from ULB/Town Vending Committee (TVC)
- Age: 18 years and above
- Occupation: Street vendor / hawker / mobile vendor / rehri-patri vendor

Loan Details:
- First loan: ₹10,000 (working capital)
- Second loan (after timely repayment): ₹20,000
- Third loan (after timely repayment): ₹50,000
- Tenure: 1 year (renewable)
- Interest subsidy: 7% per annum credited to beneficiary's account

Documents required:
- Aadhaar Card (mandatory)
- Bank account details
- Vending Certificate OR TVC/ULB recommendation letter
- PAN Card (if available)
- Mobile number linked to Aadhaar

Application process:
1. Apply through PM SVANidhi portal (pmsvanidhi.mohua.gov.in)
2. Or through lending institutions (Scheduled Commercial Banks, RRBs, SFBs, MFIs)
3. Or through Common Service Centers (CSC)

Source: PM SVANidhi official portal. Last verified 2026-09-11.""",
        "page_number": None,
    },
    {
        "title": "Stand-Up India Scheme — SC/ST and Women Entrepreneurs",
        "authority": "SIDBI / Ministry of Finance",
        "source_url": "https://www.standupmitra.in/",
        "source_type": "official_scheme",
        "content": """Stand-Up India scheme facilitates bank loans between ₹10 lakh to ₹1 crore to at least one SC or ST borrower and at least one woman borrower per bank branch.

Eligibility:
- SC (Scheduled Caste), ST (Scheduled Tribe), or Woman entrepreneur
- Age: 18 years and above
- Indian citizen
- New enterprise (greenfield project) in manufacturing, services, or trading sector
- Must NOT have defaulted to any bank or financial institution
- At least 51% shareholding and controlling stake held by SC/ST or woman entrepreneur

Loan Details:
- Minimum: ₹10 lakh
- Maximum: ₹1 crore
- Covers: Term loan + working capital (composite loan)
- Repayment period: Up to 7 years
- Moratorium period: Maximum 18 months
- Interest rate: Not more than (base rate + 3% + tenor premium) 

Documents typically required:
- Identity proof (Aadhaar, PAN)
- Address proof
- Category proof (caste certificate for SC/ST)
- Business plan / project report
- Bank statement (12 months)
- Income Tax Return (3 years, if available)
- GST Registration
- Business registration / MOA / AOA
- Photographs

Source: Stand-Up India official portal (standupmitra.in). Last verified 2026-09-11.""",
        "page_number": None,
    },
    {
        "title": "PM Fasal Bima Yojana — Crop Insurance Scheme",
        "authority": "Ministry of Agriculture & Farmers Welfare",
        "source_url": "https://pmfby.gov.in/",
        "source_type": "official_scheme",
        "content": """Pradhan Mantri Fasal Bima Yojana (PMFBY) provides comprehensive crop insurance to farmers against crop failure due to non-preventable natural risks.

Eligibility:
- Farmers (both loanee and non-loanee) growing notified crops in notified areas
- Share croppers and tenant farmers are also eligible
- Must have insurable interest in the crop

Coverage:
- Standing crop losses (due to non-preventable risks — drought, flood, hailstorm, cyclone, fire, disease/pest)
- Post-harvest losses (up to 14 days after harvest)
- Localized calamities (hailstorm, landslide, inundation)
- Prevented sowing (when widespread calamity prevents sowing)

Premium rates (farmer's share):
- Kharif crops: Maximum 2% of Sum Insured
- Rabi crops: Maximum 1.5% of Sum Insured
- Commercial/Horticultural crops: Maximum 5% of Sum Insured
- Remaining premium paid by Central and State Government

Enrollment period:
- Must enroll before the cut-off date set per crop and season
- For loanee farmers: automatic enrollment unless opted out
- For non-loanee farmers: voluntary

Documents required:
- Aadhaar Card
- Bank account details
- Land record / Khasra number / land ownership proof
- Sowing certificate (for non-loanee farmers)

Application: Through Banks, CSCs, insurance company agents, or pmfby.gov.in portal.

Source: PMFBY official portal. Last verified 2026-09-11.""",
        "page_number": None,
    },
    {
        "title": "MUDRA Loan — General Eligibility and Process",
        "authority": "MUDRA / Ministry of Finance",
        "source_url": "https://www.mudra.org.in/",
        "source_type": "official_scheme",
        "content": """MUDRA (Pradhan Mantri MUDRA Yojana — PMMY) Key Facts:

What MUDRA does NOT provide directly:
- MUDRA does not lend directly to micro entrepreneurs
- MUDRA provides refinance to banks/MFIs who lend to micro enterprises
- You apply at your bank, not at MUDRA directly

Who can apply:
- Micro and small enterprises in non-agricultural activities
- Manufacturing, processing, trading, and service sector activities
- Street vendors, artisans, shopkeepers, small manufacturers
- Self-help group (SHG) members

What is NOT eligible:
- Agricultural activities directly (though allied activities like agri-products processing may qualify)
- Applicants with existing NPA (Non-Performing Assets) with any bank
- Applicants who have been blacklisted by any bank

Income range of typical borrowers:
- Annual income generally up to ₹15 lakh (though not a hard limit)
- Loan size determines category (Shishu/Kishor/Tarun)

Rajasthan-specific: MUDRA loans are available through all scheduled banks in Rajasthan including SBI, Bank of Baroda, UCO Bank, Punjab National Bank, and regional rural banks. The Rajasthan government also provides additional subsidy support for MSME borrowers under the state MSME policy.

Source: mudra.org.in and Ministry of Finance official communications. Last verified 2026-09-11.""",
        "page_number": None,
    },
]


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks for better retrieval."""
    words = text.split()
    if len(words) <= chunk_size:
        return [text]
    
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def ingest_firecrawl(source: dict) -> list[str]:
    """Try to ingest using Firecrawl. Returns list of content chunks."""
    import httpx
    from app.core.config import get_settings
    settings = get_settings()
    
    if not settings.firecrawl_api_key:
        return []
    
    try:
        headers = {"Authorization": f"Bearer {settings.firecrawl_api_key}"}
        payload = {
            "url": source["source_url"],
            "formats": ["markdown"],
            "onlyMainContent": True,
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post("https://api.firecrawl.dev/v1/scrape", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        
        content = data.get("data", {}).get("markdown", "")
        if content and len(content) > 100:
            print(f"  ✅ Firecrawl fetched {len(content)} chars from {source['source_url']}")
            return chunk_text(content)
        
    except Exception as e:
        print(f"  ⚠ Firecrawl failed for {source['source_url']}: {e}")
    
    return []


def main():
    print("Starting knowledge ingestion...")
    print(f"Processing {len(MANUAL_KNOWLEDGE)} sources")

    db = get_supabase_admin()

    # Warm-up: test embedding model (HTTP call to Gemini)
    print("Testing Gemini embedding API (text-embedding-004)...")
    test_embed = embed_text("test financial eligibility query")
    print(f"Embedding API ready. Dimension: {len(test_embed)}")

    ingested = 0
    skipped = 0
    
    for source in MANUAL_KNOWLEDGE:
        print(f"\nIngesting: {source['title']}")
        
        # Try Firecrawl first for fresh content
        firecrawl_chunks = ingest_firecrawl(source)
        
        if firecrawl_chunks:
            chunks = firecrawl_chunks
            print(f"  Using Firecrawl content ({len(chunks)} chunks)")
        else:
            chunks = chunk_text(source["content"])
            print(f"  Using manual content ({len(chunks)} chunks)")
        
        for i, chunk in enumerate(chunks):
            c_hash = content_hash(chunk)
            
            # Skip if already ingested (idempotent)
            existing = db.table("knowledge").select("id").eq("content_hash", c_hash).execute()
            if existing.data:
                print(f"  Skip chunk {i+1} (unchanged)")
                skipped += 1
                continue
            
            # Embed
            embedding = embed_text(chunk)
            
            # Insert
            db.table("knowledge").insert({
                "title": source["title"],
                "authority": source["authority"],
                "source_url": source["source_url"],
                "source_type": source["source_type"],
                "content": chunk,
                "embedding": embedding,
                "version": 1,
                "content_hash": c_hash,
                "page_number": source.get("page_number"),
                "metadata": {"chunk_index": i, "total_chunks": len(chunks)},
            }).execute()
            
            ingested += 1
            print(f"  ✅ Ingested chunk {i+1}/{len(chunks)}")
            
            # Rate limit protection
            time.sleep(0.1)
    
    print(f"\n✅ Ingestion complete!")
    print(f"   Ingested: {ingested} new chunks")
    print(f"   Skipped:  {skipped} unchanged chunks")
    
    # Verify
    count_res = db.table("knowledge").select("id", count="exact").execute()
    print(f"   Total knowledge chunks in DB: {count_res.count}")


if __name__ == "__main__":
    main()
