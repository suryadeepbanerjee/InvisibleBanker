"""
FastAPI Application Entry Point — Invisible Banker

Architecture:
- /api/chat      → Conversation, intent extraction, profile update
- /api/voice     → Sarvam STT (with text fallback)
- /api/documents → Upload, extraction, human review
- /api/eligibility → Deterministic rules engine
- /api/workflow  → Application state management
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.routes import chat, voice, documents, eligibility, workflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Invisible Banker API",
    description="AI Financial Assistant for Indian Users — HACK MUJ 4.0",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(chat.router, prefix="/api")
app.include_router(voice.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(eligibility.router, prefix="/api")
app.include_router(workflow.router, prefix="/api")


@app.get("/")
async def root():
    return {
        "service": "Invisible Banker API",
        "version": "1.0.0",
        "hackathon": "HACK MUJ 4.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "environment": settings.environment}
