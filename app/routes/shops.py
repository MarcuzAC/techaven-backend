from fastapi import APIRouter, Depends, HTTPException, status
from app.database import supabase
from app.models import ShopCreate, ShopResponse
from app.dependencies import get_current_merchant, get_current_user

router = APIRouter(prefix="/shops", tags=["shops"])

@router.post("/", response_model=dict)
async def create_shop(shop_data: ShopCreate, current_user: dict = Depends(get_current_merchant)):
    # Check if user already has a shop
    existing_shop = supabase.table("shops").select("*").eq("user_id", current_user["id"]).execute()
    if existing_shop.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a shop"
        )
    
    shop_data_dict = shop_data.dict()
    shop_data_dict["user_id"] = current_user["id"]
    shop_data_dict["verified"] = False
    
    result = supabase.table("shops").insert(shop_data_dict).execute()
    return {"message": "Shop created successfully", "shop_id": result.data[0]["id"]}

@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(shop_id: str):
    result = supabase.table("shops").select("*").eq("id", shop_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    return result.data[0]

@router.get("/")
async def get_shops(verified: bool = None, limit: int = 20, offset: int = 0):
    query = supabase.table("shops").select("*")
    
    if verified is not None:
        query = query.eq("verified", verified)
    
    result = query.range(offset, offset + limit - 1).execute()
    return result.data

@router.put("/{shop_id}")
async def update_shop(shop_id: str, shop_data: ShopCreate, current_user: dict = Depends(get_current_merchant)):
    # Verify the shop belongs to the current user
    shop = supabase.table("shops").select("*").eq("id", shop_id).eq("user_id", current_user["id"]).execute()
    if not shop.data:
        raise HTTPException(status_code=404, detail="Shop not found or access denied")
    
    result = supabase.table("shops").update(shop_data.dict()).eq("id", shop_id).execute()
    return {"message": "Shop updated successfully"}