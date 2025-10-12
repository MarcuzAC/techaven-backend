from fastapi import APIRouter, Depends, HTTPException, status
from app.database import supabase
from app.models import PromotionCreate, PromotionResponse
from app.dependencies import get_current_merchant

router = APIRouter(prefix="/promotions", tags=["promotions"])

@router.post("/", response_model=dict)
async def create_promotion(promo_data: PromotionCreate, current_user: dict = Depends(get_current_merchant)):
    # Get user's shop
    shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_id = shop_result.data[0]["id"]
    promo_dict = promo_data.dict()
    promo_dict["shop_id"] = shop_id
    promo_dict["status"] = "pending"  # Needs admin approval
    
    # Verify product belongs to shop if specified
    if promo_dict["product_id"]:
        product = supabase.table("products").select("shop_id").eq("id", promo_dict["product_id"]).execute()
        if not product.data or product.data[0]["shop_id"] != shop_id:
            raise HTTPException(status_code=400, detail="Product not found or doesn't belong to your shop")
    
    result = supabase.table("promotions").insert(promo_dict).execute()
    return {"message": "Promotion created successfully", "promotion_id": result.data[0]["id"]}

@router.get("/")
async def get_shop_promotions(current_user: dict = Depends(get_current_merchant)):
    shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_id = shop_result.data[0]["id"]
    result = supabase.table("promotions").select("*").eq("shop_id", shop_id).execute()
    return result.data