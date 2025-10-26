from fastapi import APIRouter, Depends, Query
from app.dependencies import get_current_user
from app.recommendations import recommendation_engine

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

@router.get("/personalized")
async def get_personalized_recommendations(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=50)
):
    """Get personalized product recommendations for the current user"""
    return recommendation_engine.get_personalized_recommendations(current_user["id"], limit)

@router.get("/trending")
async def get_trending_products(
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(15, ge=1, le=50)
):
    """Get trending products based on recent blockchain activity"""
    return recommendation_engine.get_trending_products(days, limit)

@router.get("/popular")
async def get_popular_products(limit: int = Query(20, ge=1, le=100)):
    """Get popular products based on orders and blockchain activity"""
    return recommendation_engine.get_popular_products(limit)

@router.get("/shop/{shop_id}/insights")
async def get_shop_recommendations(
    shop_id: str,
    current_user: dict = Depends(get_current_user),
    limit: int = Query(5, ge=1, le=20)
):
    """Get shop improvement recommendations based on blockchain data"""
    # Verify shop ownership or admin access
    if current_user["type"] not in ["admin", "merchant"]:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    
    return recommendation_engine.get_shop_recommendations(shop_id, limit)