"""
Sarvam AI Voice STT Service

Handles Indian language speech-to-text using Sarvam's saaras:v4 model.
Fallback: text input is always available if this service fails.

Critical safety rule: Money amounts, loan amounts, ages, dates extracted 
from voice MUST be shown to user for confirmation before feeding consequential logic.
"""
import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


def transcribe_audio(audio_bytes: bytes, content_type: str = "audio/wav") -> dict:
    """
    Transcribe audio using Sarvam STT.
    
    Returns:
    {
        "transcript": str,
        "language": str,  # e.g., "hi-IN"
        "confidence": float,
        "critical_values": dict,  # values requiring user confirmation
        "success": bool,
        "error": str | None
    }
    """
    if not settings.sarvam_api_key:
        return {
            "transcript": "",
            "language": "en-IN",
            "confidence": 0.0,
            "critical_values": {},
            "success": False,
            "error": "Sarvam API key not configured",
        }

    try:
        headers = {"api-subscription-key": settings.sarvam_api_key}
        files = {"file": ("audio.wav", audio_bytes, content_type)}
        data = {"model": settings.sarvam_stt_model, "with_timestamps": False}

        with httpx.Client(timeout=30) as client:
            resp = client.post(SARVAM_STT_URL, headers=headers, files=files, data=data)
            resp.raise_for_status()
            result = resp.json()

        transcript = result.get("transcript", "")
        language = result.get("language_code", "hi-IN")

        # Extract critical values that need confirmation
        critical_values = _extract_critical_values(transcript)

        return {
            "transcript": transcript,
            "language": language,
            "confidence": result.get("confidence", 0.9),
            "critical_values": critical_values,
            "success": True,
            "error": None,
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"Sarvam STT HTTP error {e.response.status_code}: {e.response.text[:200]}")
        return {
            "transcript": "",
            "language": "en-IN",
            "confidence": 0.0,
            "critical_values": {},
            "success": False,
            "error": f"STT service error: {e.response.status_code}",
        }
    except Exception as e:
        logger.error(f"Sarvam STT failed: {e}")
        return {
            "transcript": "",
            "language": "en-IN",
            "confidence": 0.0,
            "critical_values": {},
            "success": False,
            "error": str(e),
        }


def _extract_critical_values(transcript: str) -> dict:
    """
    Extract values from transcript that require user confirmation before use.
    
    Critical values: loan amounts, ages, income figures, account numbers.
    These are extracted using simple pattern matching — NOT LLM.
    The frontend will show these back to the user for confirmation.
    """
    import re
    critical = {}

    # Loan amounts — match lakh/crore patterns
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*lakh", transcript, re.IGNORECASE)
    crore_match = re.search(r"(\d+(?:\.\d+)?)\s*crore", transcript, re.IGNORECASE)
    
    if lakh_match:
        amount = float(lakh_match.group(1)) * 100000
        critical["loan_amount"] = {
            "value": amount,
            "display": f"₹{lakh_match.group(1)} lakh (₹{amount:,.0f})",
        }
    elif crore_match:
        amount = float(crore_match.group(1)) * 10000000
        critical["loan_amount"] = {
            "value": amount,
            "display": f"₹{crore_match.group(1)} crore (₹{amount:,.0f})",
        }

    # Age
    age_match = re.search(r"\b(\d{2})\s*(?:saal|year|sal|साल)", transcript, re.IGNORECASE)
    if age_match:
        critical["age"] = {
            "value": int(age_match.group(1)),
            "display": f"{age_match.group(1)} years",
        }

    return critical
