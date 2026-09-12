"""
Workflow state and application management API.
"""
import logging
from fastapi import APIRouter, HTTPException
from app.core.database import get_supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflow", tags=["workflow"])
db = get_supabase_admin()


@router.get("/application/{application_id}")
async def get_application(application_id: str):
    """Get full application state including audit trail."""
    res = db.table("applications").select("*").eq("id", application_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Application not found")
    return res.data[0]


@router.get("/user/{user_id}/latest")
async def get_latest_application(user_id: str):
    """Get the user's most recent application for session continuity."""
    res = (
        db.table("applications")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return {"application": None}
    return {"application": res.data[0]}


@router.post("/application/{application_id}/select-product")
async def select_product(application_id: str, product_id: str):
    """User selects a specific product to proceed with."""
    from datetime import datetime

    db.table("applications").update({
        "selected_product_id": product_id,
        "workflow_state": "USER_SELECTED_OPTION",
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", application_id).execute()

    return {"success": True, "workflow_state": "USER_SELECTED_OPTION"}
