import json
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Dict, Any
from app.blockchain.service import BlockchainService
from app.database import supabase
from app.model.models import ProductResponse, TransactionType
from app.dependencies import get_current_user

router = APIRouter(prefix="/favorites", tags=["favorites"])

@router.get("/", response_model=List[ProductResponse])
async def get_favorites(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(20, le=100),
    offset: int = 0
):
    """Get user's favorite products"""
    # Get favorite product IDs
    favorites_result = supabase.table("user_favorites").select(
        "product_id"
    ).eq("user_id", current_user["id"]).range(offset, offset + limit - 1).execute()
    
    if not favorites_result.data:
        return []
    
    product_ids = [item["product_id"] for item in favorites_result.data]
    
    # Get product details
    products_result = supabase.table("products").select(
        "*, shops(name, verified)"
    ).in_("id", product_ids).execute()
    
    products = []
    for product in products_result.data:
        if product.get("specs"):
            product["specs"] = json.loads(product["specs"])
        
        # Get categories
        categories_result = supabase.table("product_categories").select(
            "category_id, categories(name, icon)"
        ).eq("product_id", product["id"]).execute()
        
        product["categories"] = [item["categories"] for item in categories_result.data]
        products.append(product)
    
    return products

@router.post("/{product_id}", status_code=status.HTTP_201_CREATED)
async def add_to_favorites(
    product_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Add product to favorites"""
    # Check if product exists
    product_result = supabase.table("products").select("id").eq("id", product_id).execute()
    if not product_result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check if already in favorites
    existing = supabase.table("user_favorites").select("*").eq(
        "user_id", current_user["id"]
    ).eq("product_id", product_id).execute()
    
    if existing.data:
        raise HTTPException(status_code=400, detail="Product already in favorites")
    
    # Add to favorites
    result = supabase.table("user_favorites").insert({
        "user_id": current_user["id"],
        "product_id": product_id
    }).execute()
    
    # Record on blockchain
    try:
        favorite_transaction = BlockchainService.create_transaction(
            transaction_type=TransactionType.REVIEW_CREATE,  # Use appropriate type
            user_id=current_user["id"],
            data={
                "action": "add_to_favorites",
                "product_id": product_id,
                "user_id": current_user["id"]
            },
            product_id=product_id,
            metadata={
                "source": "favorites_route",
                "favorite_added": True
            }
        )
        
        BlockchainService.add_transaction(favorite_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {"message": "Product added to favorites"}

@router.delete("/{product_id}")
async def remove_from_favorites(
    product_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Remove product from favorites"""
    result = supabase.table("user_favorites").delete().eq(
        "user_id", current_user["id"]
    ).eq("product_id", product_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found in favorites")
    
    # Record on blockchain
    try:
        unfavorite_transaction = BlockchainService.create_transaction(
            transaction_type=TransactionType.REVIEW_CREATE,  # Use appropriate type
            user_id=current_user["id"],
            data={
                "action": "remove_from_favorites",
                "product_id": product_id,
                "user_id": current_user["id"]
            },
            product_id=product_id,
            metadata={
                "source": "favorites_route",
                "favorite_removed": True
            }
        )
        
        BlockchainService.add_transaction(unfavorite_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {"message": "Product removed from favorites"}

@router.get("/count")
async def get_favorites_count(current_user: dict = Depends(get_current_user)):
    """Get count of favorite products"""
    result = supabase.table("user_favorites").select(
        "count", count="exact"
    ).eq("user_id", current_user["id"]).execute()
    
    return {"count": result.count or 0}

@router.get("/check/{product_id}")
async def check_favorite(
    product_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Check if product is in favorites"""
    result = supabase.table("user_favorites").select("*").eq(
        "user_id", current_user["id"]
    ).eq("product_id", product_id).execute()
    
    return {"is_favorite": len(result.data) > 0}