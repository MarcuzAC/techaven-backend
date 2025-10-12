from fastapi import APIRouter, Depends
from app.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    return current_user

@router.get("/{user_id}")
async def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
    from app.database import supabase
    result = supabase.table("users").select("id, name, email, type, created_at").eq("id", user_id).execute()
    if not result.data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return result.data[0]