# Invisible Banker — HACK MUJ 4.0

> **The Invisible Banker**: Turning Financial Intent into Action

An AI financial assistant that understands Indian language voice/text, interprets financial documents, and guides users through verified financial product workflows with complete source traceability.

## Architecture

```
USER VOICE/TEXT → SARVAM STT → GROQ LLM → SUPABASE → RAG KNOWLEDGE → ELIGIBILITY ENGINE → DASHBOARD
```

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + Tailwind CSS |
| Backend | Python 3.11 + FastAPI + Pydantic |
| Database | Supabase (PostgreSQL + pgvector) |
| LLM (Primary) | Groq (llama-3.3-70b-versatile) |
| LLM (Fallback) | Gemini 1.5 Flash |
| Voice STT | Sarvam AI (saaras:v4) |
| PDF Extraction | PyMuPDF + pdfplumber |
| Knowledge Ingestion | Firecrawl |
| Embeddings | sentence-transformers (multilingual) |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Supabase account (project configured)

### Backend Setup

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
cp ../.env.example .env
# Edit .env with your credentials

uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
# Edit .env.local with Supabase public keys

npm run dev
```

### Database Setup

```bash
cd backend
python scripts/init_db.py     # Create tables
python scripts/seed_products.py  # Seed financial products
python scripts/ingest_knowledge.py  # Ingest source documents
```

## Project Structure

```
InvisibleBanker/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── core/                # Config, DB, security
│   │   ├── api/routes/          # API route handlers
│   │   ├── services/            # Business logic
│   │   │   ├── llm/             # LLM provider abstraction
│   │   │   ├── document/        # Document extraction
│   │   │   ├── knowledge/       # RAG pipeline
│   │   │   └── voice/           # Sarvam STT
│   │   ├── engine/              # Deterministic eligibility engine
│   │   └── models/              # Pydantic schemas
│   ├── scripts/                 # Setup, seeding, ingestion
│   ├── tests/                   # Unit tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/               # Route pages
│   │   ├── components/          # UI components
│   │   ├── services/            # API calls
│   │   ├── hooks/               # React hooks
│   │   └── lib/                 # Utilities
│   ├── package.json
│   └── vite.config.js
├── obsidian-vault/              # Project memory (not source code)
├── .env.example                 # Credential template (safe to commit)
├── .gitignore
└── README.md
```

## Core Principles

- **LLM understands. Sources provide evidence. Code decides. Database remembers. Human handles uncertainty. LLM explains.**
- LLM never determines eligibility — deterministic Python engine does
- Every consequential claim traces to an official source
- Voice failure → text fallback (always works)
- Low confidence → NEEDS_REVIEW (never silent assumption)

## Demo Scenarios

| Case | Profile | Expected Result |
|------|---------|----------------|
| Ravi — Shopkeeper | Age 32, Rajasthan, Business 3yr, Income ₹40k/mo, Loan ₹5L | MUDRA Tarun: ELIGIBLE |
| Priya — New Vendor | Age 19, Street vendor, No bank account | PM SVANidhi: NEEDS_REVIEW |
| Kumar — Defaulted | Age 45, Existing NPA | All products: INELIGIBLE |

## Environment Variables

See [.env.example](.env.example) for all required variables.

**CRITICAL:** `SUPABASE_SERVICE_ROLE_KEY` is backend-only. Never expose to frontend.
