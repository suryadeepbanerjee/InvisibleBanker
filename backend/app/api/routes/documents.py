"""
Document upload and processing API routes.
"""
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.document.extractor import process_document
from app.core.database import get_supabase_admin
from app.models.schemas import DocumentStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
db = get_supabase_admin()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    application_id: str = Form(...),
):
    """
    Upload and process a financial document.
    
    Pipeline:
    1. Validate file
    2. Store in Supabase Storage (private)
    3. Extract text and structured fields
    4. Check for conflicts with existing profile data
    5. Return extraction results with confidence scores
    """
    # Validate file type
    if not file.filename.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
        raise HTTPException(status_code=400, detail="Only PDF and image files are supported")

    # Read file
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    try:
        document_id = str(uuid.uuid4())

        # Store in Supabase Storage (private bucket)
        storage_path = f"{user_id}/{document_id}/{file.filename}"
        try:
            db.storage.from_("financial-documents").upload(
                storage_path,
                pdf_bytes,
                file_options={"content-type": file.content_type or "application/pdf"},
            )
        except Exception as e:
            logger.warning(f"Storage upload failed (continuing with extraction): {e}")
            storage_path = f"local/{document_id}"  # Fallback path

        # Load existing profile fields for conflict detection
        profile_res = db.table("profiles").select("structured_profile").eq("user_id", user_id).execute()
        existing_fields = {}
        if profile_res.data:
            sp = profile_res.data[0].get("structured_profile", {})
            existing_fields = {k: v for k, v in sp.items() if isinstance(v, dict) and "value" in v}

        # Process document
        result = process_document(
            pdf_bytes=pdf_bytes,
            filename=file.filename,
            document_id=document_id,
            existing_profile_fields=existing_fields,
        )

        # Store document record
        doc_record = {
            "id": document_id,
            "user_id": user_id,
            "type": result["document_type"],
            "storage_path": storage_path,
            "extracted_text": result["extracted_text"][:10000],  # Limit text storage
            "extracted_json": result["extracted_fields"],
            "confidence": result["overall_confidence"],
            "status": result["status"],
            "metadata": {
                "filename": file.filename,
                "page_count": result.get("page_count", 0),
                "type_confidence": result["type_confidence"],
                "low_confidence_fields": result["low_confidence_fields"],
                "conflicts": result["conflicts"],
            },
        }
        db.table("documents").insert(doc_record).execute()

        # Add audit event
        app_res = db.table("applications").select("audit_events").eq("id", application_id).execute()
        events = app_res.data[0].get("audit_events", []) if app_res.data else []
        events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "type": "DOCUMENT_UPLOADED",
            "data": {
                "document_id": document_id,
                "document_type": result["document_type"],
                "confidence": result["overall_confidence"],
                "status": result["status"],
                "fields_extracted": list(result["extracted_fields"].keys()),
            }
        })
        db.table("applications").update({
            "audit_events": events,
            "workflow_state": "DOCUMENT_ANALYSIS",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", application_id).execute()

        return {
            "document_id": document_id,
            "document_type": result["document_type"],
            "type_confidence": result["type_confidence"],
            "extracted_fields": result["extracted_fields"],
            "overall_confidence": result["overall_confidence"],
            "status": result["status"],
            "low_confidence_fields": result["low_confidence_fields"],
            "conflicts": result["conflicts"],
            "needs_review": result["status"] == DocumentStatus.NEEDS_REVIEW,
            "message": (
                "Document requires review for some fields."
                if result["status"] == DocumentStatus.NEEDS_REVIEW
                else "Document processed successfully."
            ),
        }

    except Exception as e:
        logger.error(f"Document upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")


@router.post("/{document_id}/confirm")
async def confirm_field(
    document_id: str,
    field_name: str = Form(...),
    confirmed_value: str = Form(...),
    action: str = Form(...),  # CONFIRM, CORRECT, REJECT
    application_id: str = Form(...),
):
    """
    Human review: confirm, correct, or reject an extracted field.
    
    After confirmation, the profile is updated and affected rules will be rerun.
    """
    try:
        # Load document
        doc_res = db.table("documents").select("*").eq("id", document_id).execute()
        if not doc_res.data:
            raise HTTPException(status_code=404, detail="Document not found")

        doc = doc_res.data[0]
        extracted = doc.get("extracted_json", {})
        user_id = doc["user_id"]

        if action == "CONFIRM":
            # Field confirmed as-is — mark as human_confirmed
            if field_name in extracted:
                extracted[field_name]["source_type"] = "human_confirmed"
                extracted[field_name]["confidence"] = 1.0
        elif action == "CORRECT":
            # Field corrected — update value, mark human_confirmed
            if field_name in extracted:
                extracted[field_name]["value"] = confirmed_value
                extracted[field_name]["source_type"] = "human_confirmed"
                extracted[field_name]["confidence"] = 1.0
            else:
                extracted[field_name] = {
                    "value": confirmed_value,
                    "confidence": 1.0,
                    "source_type": "human_confirmed",
                }
        elif action == "REJECT":
            # Field rejected — remove it
            extracted.pop(field_name, None)

        # Update document
        db.table("documents").update({
            "extracted_json": extracted,
            "status": DocumentStatus.CONFIRMED,
        }).eq("id", document_id).execute()

        # Update profile with confirmed value
        if action in ("CONFIRM", "CORRECT") and field_name in extracted:
            profile_res = db.table("profiles").select("structured_profile").eq("user_id", user_id).execute()
            if profile_res.data:
                sp = profile_res.data[0].get("structured_profile", {}) or {}
                sp[field_name] = extracted[field_name]
                db.table("profiles").update({
                    "structured_profile": sp,
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("user_id", user_id).execute()

        # Audit event
        app_res = db.table("applications").select("audit_events").eq("id", application_id).execute()
        events = app_res.data[0].get("audit_events", []) if app_res.data else []
        events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "type": "HUMAN_REVIEW",
            "data": {
                "action": action,
                "field": field_name,
                "confirmed_value": confirmed_value if action == "CORRECT" else None,
                "document_id": document_id,
            }
        })
        db.table("applications").update({"audit_events": events}).eq("id", application_id).execute()

        return {
            "success": True,
            "action": action,
            "field": field_name,
            "message": f"Field '{field_name}' {action.lower()}ed. Rerun eligibility check to update results.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Field confirmation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}")
async def get_user_documents(user_id: str):
    """Get all documents for a user."""
    res = db.table("documents").select(
        "id, type, status, confidence, metadata, created_at"
    ).eq("user_id", user_id).execute()
    return {"documents": res.data or []}
