from fastapi import APIRouter, Depends, HTTPException, status
from app.database import supabase
from app.dependencies import get_current_admin

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/metrics")
async def get_admin_metrics(current_user: dict = Depends(get_current_admin)):
    # Get basic platform metrics
    total_users = supabase.table("users").select("count", count="exact").execute()
    total_shops = supabase.table("shops").select("count", count="exact").execute()
    total_products = supabase.table("products").select("count", count="exact").execute()
    total_orders = supabase.table("orders").select("count", count="exact").execute()
    
    return {
        "total_users": total_users.count,
        "total_shops": total_shops.count,
        "total_products": total_products.count,
        "total_orders": total_orders.count,
        "pending_verifications": supabase.table("shops").select("count", count="exact").eq("verified", False).execute().count
    }

@router.post("/shops/{shop_id}/verify")
async def verify_shop(shop_id: str, current_user: dict = Depends(get_current_admin)):
    result = supabase.table("shops").update({"verified": True}).eq("id", shop_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {"message": "Shop verified successfully"}

@router.get("/shops/pending")
async def get_pending_shops(current_user: dict = Depends(get_current_admin)):
    result = supabase.table("shops").select("*").eq("verified", False).execute()
    return result.data