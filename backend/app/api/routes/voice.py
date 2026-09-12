"""
Voice STT API route.
"""
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.voice.sarvam import transcribe_audio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Transcribe audio using Sarvam STT.
    
    Returns transcript, detected language, and critical values requiring confirmation.
    The application always works with text input if this endpoint fails.
    """
    if not audio.content_type or not audio.content_type.startswith("audio"):
        raise HTTPException(status_code=400, detail="Audio file required")

    audio_bytes = await audio.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file")

    result = transcribe_audio(audio_bytes, audio.content_type)

    if not result["success"]:
        # Return error but don't crash — text input is always available
        return {
            "success": False,
            "error": result["error"],
            "fallback_message": "Voice recognition unavailable. Please type your message instead.",
        }

    return {
        "success": True,
        "transcript": result["transcript"],
        "language": result["language"],
        "confidence": result["confidence"],
        "critical_values": result["critical_values"],
        "confirmation_required": len(result["critical_values"]) > 0,
        "confirmation_message": _build_confirmation_message(result["critical_values"]),
    }


def _build_confirmation_message(critical_values: dict) -> str | None:
    if not critical_values:
        return None
    parts = []
    if "loan_amount" in critical_values:
        parts.append(f"loan amount: {critical_values['loan_amount']['display']}")
    if "age" in critical_values:
        parts.append(f"age: {critical_values['age']['display']}")
    return f"Please confirm — you mentioned: {', '.join(parts)}. Is that correct?"
