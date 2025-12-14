from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Request
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta
import uuid
from app.database import supabase
from app.dependencies import get_current_user, get_current_user_optional, get_current_admin
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType
from app.utils.redis_client import redis_client
import json

router = APIRouter(prefix="/recently-viewed", tags=["recently_viewed"])
logger = logging.getLogger(__name__)

# ========== CORE ENDPOINTS ==========

@router.post("/track")
async def track_view(
    request: Request,
    view_data: dict,
    background_tasks: BackgroundTasks,
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Track a product view.
    """
    try:
        # Validate required fields
        if "product_id" not in view_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product ID is required"
            )
        
        product_id = view_data["product_id"]
        
        # Validate product exists and is published
        product_result = supabase.table("products").select(
            "id, title, price, shop_id, is_published"
        ).eq("id", product_id).eq("is_published", True).execute()
        
        if not product_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found or not published"
            )
        
        product = product_result.data[0]
        
        # Create view record
        view_id = str(uuid.uuid4())
        view_payload = {
            "id": view_id,
            "user_id": current_user["id"] if current_user else None,
            "product_id": product_id,
            "viewed_at": view_data.get("viewed_at") or datetime.utcnow().isoformat(),
            "session_id": view_data.get("session_id"),
            "duration_seconds": view_data.get("duration_seconds"),
            "metadata": view_data.get("metadata") or {},
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Record view tracking on blockchain (only for authenticated users)
        view_transaction = None
        if current_user:
            try:
                view_transaction = blockchain_service.create_transaction(
                    transaction_type=TransactionType.PRODUCT_VIEW,
                    user_id=current_user["id"],
                    product_id=product_id,
                    data={
                        "action": "product_view",
                        "product_id": product_id,
                        "product_title": product["title"],
                        "duration_seconds": view_data.get("duration_seconds"),
                        "view_id": view_id,
                        "anonymous": False
                    },
                    metadata={
                        "source": "recently_viewed_route",
                        "has_session": bool(view_data.get("session_id")),
                        "has_duration": "duration_seconds" in view_data
                    }
                )
                
                blockchain_service.add_transaction(view_transaction)
                
                # Add blockchain transaction ID to view
                view_payload["blockchain_tx_id"] = view_transaction.transaction_id
                
            except Exception as e:
                print(f"[BLOCKCHAIN] View tracking transaction failed: {e}")
        
        # Save view to database
        result = supabase.table("recently_viewed").insert(view_payload).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to track view"
            )
        
        # Update product view count in background
        background_tasks.add_task(
            update_product_view_count,
            product_id
        )
        
        # Update real-time view counter
        background_tasks.add_task(
            update_real_time_views,
            product_id,
            current_user["id"] if current_user else None
        )
        
        return {
            "message": "View tracked successfully",
            "view_id": view_id,
            "product_id": product_id,
            "user_id": current_user["id"] if current_user else None,
            "anonymous": not bool(current_user),
            "blockchain_tx_id": view_transaction.transaction_id if view_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error tracking view: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to track view"
        )

@router.get("/")
async def get_recently_viewed_products(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    include_product_details: bool = Query(True)
):
    """
    Get recently viewed products for the current user.
    """
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Get recently viewed items
        result = supabase.table("recently_viewed").select(
            "id, user_id, product_id, viewed_at, session_id, "
            "duration_seconds, metadata, created_at, blockchain_tx_id"
        ).eq("user_id", current_user["id"]).gte(
            "viewed_at", cutoff_date
        ).order("viewed_at", desc=True).limit(limit).execute()
        
        views_data = []
        
        for view in result.data:
            view_item = {
                "id": view["id"],
                "user_id": view["user_id"],
                "product_id": view["product_id"],
                "viewed_at": view["viewed_at"],
                "session_id": view.get("session_id"),
                "duration_seconds": view.get("duration_seconds"),
                "metadata": view.get("metadata") or {},
                "created_at": view["created_at"],
                "blockchain_tx_id": view.get("blockchain_tx_id")
            }
            
            # Add product details if requested
            if include_product_details:
                product_result = supabase.table("products").select(
                    "id, title, price, images, shop_id, description, brand, "
                    "category_ids, average_rating, rating_count"
                ).eq("id", view["product_id"]).execute()
                
                if product_result.data:
                    product = product_result.data[0]
                    view_item["product"] = {
                        "id": product["id"],
                        "title": product["title"],
                        "price": product["price"],
                        "images": product.get("images") or [],
                        "shop_id": product["shop_id"],
                        "description": product.get("description", ""),
                        "brand": product.get("brand", ""),
                        "category_ids": product.get("category_ids") or [],
                        "average_rating": product.get("average_rating"),
                        "rating_count": product.get("rating_count", 0)
                    }
            
            views_data.append(view_item)
        
        return {
            "data": views_data,
            "user_id": current_user["id"],
            "total_views": len(views_data),
            "time_range_days": days
        }
        
    except Exception as e:
        logger.error(f"Error fetching recently viewed products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch recently viewed products"
        )

@router.delete("/clear")
async def clear_recently_viewed_history(
    current_user: dict = Depends(get_current_user)
):
    """
    Clear recently viewed history for the current user.
    """
    try:
        # Get count before deletion
        count_result = supabase.table("recently_viewed").select(
            "id", count="exact"
        ).eq("user_id", current_user["id"]).execute()
        
        items_count = count_result.count or 0
        
        if items_count == 0:
            return {
                "message": "No recently viewed items to clear",
                "user_id": current_user["id"],
                "cleared_count": 0
            }
        
        # Record deletion on blockchain
        clear_transaction = None
        try:
            clear_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.USER_UPDATE,
                user_id=current_user["id"],
                data={
                    "action": "clear_recently_viewed",
                    "user_id": current_user["id"],
                    "items_count": items_count,
                    "user_action": True
                },
                metadata={
                    "source": "recently_viewed_route",
                    "clear_operation": True
                }
            )
            
            blockchain_service.add_transaction(clear_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Clear history transaction failed: {e}")
        
        # Delete all views for this user
        supabase.table("recently_viewed").delete().eq("user_id", current_user["id"]).execute()
        
        return {
            "message": f"Cleared {items_count} recently viewed items",
            "user_id": current_user["id"],
            "cleared_count": items_count,
            "timestamp": datetime.utcnow().isoformat(),
            "blockchain_tx_id": clear_transaction.transaction_id if clear_transaction else None
        }
        
    except Exception as e:
        logger.error(f"Error clearing recently viewed history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear recently viewed history"
        )

@router.get("/stats")
async def get_user_view_stats(
    current_user: dict = Depends(get_current_user),
    days: int = Query(30, ge=1, le=365)
):
    """
    Get viewing statistics for the current user.
    """
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Get user's view stats
        views_result = supabase.table("recently_viewed").select(
            "id, product_id, viewed_at, duration_seconds"
        ).eq("user_id", current_user["id"]).gte(
            "viewed_at", cutoff_date
        ).execute()
        
        views = views_result.data
        total_views = len(views)
        
        # Calculate unique products
        unique_product_ids = set(view["product_id"] for view in views)
        unique_products = len(unique_product_ids)
        
        # Calculate views for today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        views_today_result = supabase.table("recently_viewed").select(
            "id", count="exact"
        ).eq("user_id", current_user["id"]).gte(
            "viewed_at", today_start
        ).execute()
        
        views_today = views_today_result.count or 0
        
        # Calculate views for this week
        week_start = (datetime.utcnow() - timedelta(days=7)).isoformat()
        views_week_result = supabase.table("recently_viewed").select(
            "id", count="exact"
        ).eq("user_id", current_user["id"]).gte(
            "viewed_at", week_start
        ).execute()
        
        views_this_week = views_week_result.count or 0
        
        # Calculate average duration
        total_duration = sum(view.get("duration_seconds", 0) for view in views if view.get("duration_seconds"))
        views_with_duration = sum(1 for view in views if view.get("duration_seconds"))
        average_duration = total_duration / views_with_duration if views_with_duration > 0 else 0
        
        # Find most viewed product
        product_counts = {}
        for view in views:
            product_id = view["product_id"]
            product_counts[product_id] = product_counts.get(product_id, 0) + 1
        
        most_viewed_product_id = max(product_counts, key=product_counts.get) if product_counts else None
        most_viewed_count = product_counts.get(most_viewed_product_id, 0) if most_viewed_product_id else 0
        
        # Get most viewed product details
        most_viewed_product = None
        if most_viewed_product_id:
            product_result = supabase.table("products").select(
                "id, title, price, images"
            ).eq("id", most_viewed_product_id).execute()
            
            if product_result.data:
                most_viewed_product = product_result.data[0]
        
        # Get last view
        last_view = max(views, key=lambda x: x["viewed_at"]) if views else None
        
        return {
            "user_id": current_user["id"],
            "time_period_days": days,
            "total_views": total_views,
            "unique_products": unique_products,
            "views_today": views_today,
            "views_this_week": views_this_week,
            "average_duration_seconds": round(average_duration, 2),
            "most_viewed_product": {
                "product_id": most_viewed_product_id,
                "view_count": most_viewed_count,
                "details": most_viewed_product
            } if most_viewed_product_id else None,
            "last_viewed_at": last_view["viewed_at"] if last_view else None
        }
        
    except Exception as e:
        logger.error(f"Error fetching view stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch view stats"
        )

@router.get("/product/{product_id}/stats")
async def get_product_view_stats(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    days: int = Query(30, ge=1, le=365)
):
    """
    Get view statistics for a specific product (shop owner/admin only).
    """
    try:
        # Validate product exists
        product_result = supabase.table("products").select(
            "id, title, shop_id"
        ).eq("id", product_id).execute()
        
        if not product_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        product = product_result.data[0]
        
        # Check permissions (shop owner or admin)
        if current_user.get("type") != "admin":
            # Check if user is the shop owner
            shop_result = supabase.table("shops").select(
                "user_id"
            ).eq("id", product["shop_id"]).execute()
            
            if not shop_result.data or shop_result.data[0]["user_id"] != current_user["id"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view product view stats"
                )
        
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Get product view stats
        views_result = supabase.table("recently_viewed").select(
            "id, user_id, viewed_at, duration_seconds"
        ).eq("product_id", product_id).gte(
            "viewed_at", cutoff_date
        ).execute()
        
        views = views_result.data
        total_views = len(views)
        
        # Calculate unique viewers
        unique_viewer_ids = set(view["user_id"] for view in views if view["user_id"])
        unique_viewers = len(unique_viewer_ids)
        
        # Calculate views by day
        views_by_day = {}
        current_date = datetime.utcnow()
        for i in range(days):
            day = current_date - timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
            
            day_views_count = sum(1 for view in views if 
                                 day_start <= view["viewed_at"] <= day_end)
            views_by_day[day_str] = day_views_count
        
        # Calculate average duration
        total_duration = sum(view.get("duration_seconds", 0) for view in views if view.get("duration_seconds"))
        views_with_duration = sum(1 for view in views if view.get("duration_seconds"))
        average_duration = total_duration / views_with_duration if views_with_duration > 0 else 0
        
        # Get top viewers (users who viewed this product the most)
        user_view_counts = {}
        for view in views:
            if view["user_id"]:
                user_view_counts[view["user_id"]] = user_view_counts.get(view["user_id"], 0) + 1
        
        top_viewers = []
        for user_id, count in sorted(user_view_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            user_result = supabase.table("users").select(
                "id, name, email, profile_picture"
            ).eq("id", user_id).execute()
            
            if user_result.data:
                user = user_result.data[0]
                top_viewers.append({
                    "user_id": user["id"],
                    "name": user["name"],
                    "email": user["email"],
                    "profile_picture": user.get("profile_picture"),
                    "view_count": count
                })
        
        return {
            "product_id": product_id,
            "product_title": product["title"],
            "shop_id": product["shop_id"],
            "time_range_days": days,
            "total_views": total_views,
            "unique_viewers": unique_viewers,
            "average_duration_seconds": round(average_duration, 2),
            "views_by_day": views_by_day,
            "top_viewers": top_viewers
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product view stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch product view stats"
        )

# ========== RECOMMENDATIONS ==========

@router.get("/recommendations")
async def get_personalized_recommendations(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get personalized product recommendations based on viewing history.
    """
    try:
        # Get recently viewed products
        recent_views_result = supabase.table("recently_viewed").select(
            "product_id"
        ).eq("user_id", current_user["id"]).order(
            "viewed_at", desc=True
        ).limit(10).execute()
        
        recent_views = recent_views_result.data
        
        if not recent_views:
            # If no viewing history, return popular products
            return await get_popular_products(limit)
        
        # Get viewed product IDs
        viewed_product_ids = [view["product_id"] for view in recent_views]
        
        # Get categories of viewed products
        products_result = supabase.table("products").select(
            "id, category_ids"
        ).in_("id", viewed_product_ids).execute()
        
        viewed_products = products_result.data
        
        # Collect all categories from viewed products
        all_categories = set()
        for product in viewed_products:
            if product.get("category_ids"):
                all_categories.update(product["category_ids"])
        
        recommendations = []
        
        if all_categories:
            # Find similar products in same categories
            for category_id in list(all_categories)[:5]:  # Limit to top 5 categories
                similar_result = supabase.table("products").select(
                    "id, title, price, images, shop_id, description, "
                    "average_rating, rating_count, view_count, category_ids"
                ).eq("is_published", True).contains(
                    "category_ids", [category_id]
                ).not_in("id", viewed_product_ids + [p["id"] for p in recommendations]).order(
                    "view_count", desc=True
                ).limit(limit // min(5, len(all_categories)) + 1).execute()
                
                recommendations.extend(similar_result.data)
                
                if len(recommendations) >= limit:
                    break
        
        # If not enough recommendations, add popular products
        if len(recommendations) < limit:
            popular_products = await get_popular_products(limit - len(recommendations))
            # Filter out already recommended products
            recommended_ids = [p["id"] for p in recommendations]
            popular_products = [p for p in popular_products if p["id"] not in recommended_ids]
            recommendations.extend(popular_products)
        
        # Add recommendation metadata
        for product in recommendations:
            product["recommendation_reason"] = "Based on your viewing history"
            product["confidence_score"] = 0.8  # Simulated confidence score
        
        return {
            "data": recommendations[:limit],
            "user_id": current_user["id"],
            "based_on_viewed": viewed_product_ids,
            "total_recommendations": len(recommendations[:limit])
        }
        
    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendations"
        )

@router.get("/recommendations/similar/{product_id}")
async def get_similar_product_recommendations(
    product_id: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    limit: int = Query(10, ge=1, le=20)
):
    """
    Get similar product recommendations based on a specific product.
    """
    try:
        # Validate product exists
        product_result = supabase.table("products").select(
            "id, title, price, images, shop_id, category_ids"
        ).eq("id", product_id).eq("is_published", True).execute()
        
        if not product_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        product = product_result.data[0]
        
        # Get product categories
        category_ids = product.get("category_ids") or []
        
        if not category_ids:
            # If no categories, return popular products
            return {
                "data": await get_popular_products(limit),
                "original_product_id": product_id,
                "reason": "No categories available for this product"
            }
        
        # Find similar products in same categories
        similar_result = supabase.table("products").select(
            "id, title, price, images, shop_id, description, "
            "average_rating, rating_count, view_count, category_ids"
        ).eq("is_published", True).neq("id", product_id).overlap(
            "category_ids", category_ids
        ).order("view_count", desc=True).limit(limit).execute()
        
        similar_products = similar_result.data
        
        # Add similarity metadata
        for similar_product in similar_products:
            similar_product["similarity_reason"] = "Same categories"
            # Calculate simple similarity score based on shared categories
            shared_categories = set(similar_product.get("category_ids") or []) & set(category_ids)
            similar_product["similarity_score"] = len(shared_categories) / max(len(category_ids), 1)
        
        return {
            "data": similar_products,
            "original_product_id": product_id,
            "original_product_title": product["title"],
            "total_similar": len(similar_products),
            "based_on_categories": category_ids
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating similar product recommendations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate similar product recommendations"
        )

@router.get("/trending")
async def get_trending_products_list(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(10, ge=1, le=50),
    category_id: Optional[str] = Query(None)
):
    """
    Get trending products based on recent views.
    """
    try:
        cutoff_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        
        # Build query for trending products
        # Note: This is a simplified approach. In production, you might want to 
        # use a more sophisticated algorithm or pre-computed trending data.
        
        if category_id:
            # Get products in specific category
            products_result = supabase.table("products").select(
                "id, title, price, images, shop_id, description, "
                "average_rating, rating_count, view_count, category_ids"
            ).eq("is_published", True).contains("category_ids", [category_id]).execute()
        else:
            # Get all published products
            products_result = supabase.table("products").select(
                "id, title, price, images, shop_id, description, "
                "average_rating, rating_count, view_count, category_ids"
            ).eq("is_published", True).execute()
        
        products = products_result.data
        
        if not products:
            return {"data": [], "hours": hours, "category_id": category_id}
        
        # Get recent views for these products
        trending_products = []
        for product in products:
            # Get recent view count for this product
            views_result = supabase.table("recently_viewed").select(
                "id", count="exact"
            ).eq("product_id", product["id"]).gte("viewed_at", cutoff_time).execute()
            
            recent_views = views_result.count or 0
            
            if recent_views > 0:
                # Calculate trend score (recent views per hour)
                trend_score = recent_views / hours
                
                trending_products.append({
                    **product,
                    "recent_views": recent_views,
                    "trend_score": round(trend_score, 2),
                    "total_views": product.get("view_count", 0)
                })
        
        # Sort by trend score
        trending_products.sort(key=lambda x: x["trend_score"], reverse=True)
        
        return {
            "data": trending_products[:limit],
            "hours": hours,
            "cutoff_time": cutoff_time,
            "category_id": category_id,
            "total_trending": len(trending_products[:limit])
        }
        
    except Exception as e:
        logger.error(f"Error fetching trending products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch trending products"
        )

# ========== ANONYMOUS USER SUPPORT ==========

@router.get("/session/{session_id}")
async def get_session_views(
    session_id: str,
    limit: int = Query(20, ge=1, le=100),
    include_product_details: bool = Query(True)
):
    """
    Get recently viewed products for a session (anonymous users).
    """
    try:
        # Get session views
        result = supabase.table("recently_viewed").select(
            "id, user_id, product_id, viewed_at, session_id, "
            "duration_seconds, metadata, created_at"
        ).eq("session_id", session_id).is_("user_id", None).order(
            "viewed_at", desc=True
        ).limit(limit).execute()
        
        views_data = []
        
        for view in result.data:
            view_item = {
                "id": view["id"],
                "user_id": view["user_id"],
                "product_id": view["product_id"],
                "viewed_at": view["viewed_at"],
                "session_id": view["session_id"],
                "duration_seconds": view.get("duration_seconds"),
                "metadata": view.get("metadata") or {},
                "created_at": view["created_at"]
            }
            
            # Add product details if requested
            if include_product_details:
                product_result = supabase.table("products").select(
                    "id, title, price, images, shop_id"
                ).eq("id", view["product_id"]).execute()
                
                if product_result.data:
                    product = product_result.data[0]
                    view_item["product"] = {
                        "id": product["id"],
                        "title": product["title"],
                        "price": product["price"],
                        "images": product.get("images") or [],
                        "shop_id": product["shop_id"]
                    }
            
            views_data.append(view_item)
        
        return {
            "data": views_data,
            "session_id": session_id,
            "total_views": len(views_data),
            "anonymous": True
        }
        
    except Exception as e:
        logger.error(f"Error fetching session views: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch session views"
        )

@router.post("/session/{session_id}/merge")
async def merge_session_to_user(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Merge anonymous session views to user account.
    """
    try:
        # Get session views
        result = supabase.table("recently_viewed").select(
            "id, product_id, viewed_at"
        ).eq("session_id", session_id).is_("user_id", None).execute()
        
        session_views = result.data
        
        if not session_views:
            return {
                "message": "No session views to merge",
                "session_id": session_id,
                "user_id": current_user["id"],
                "merged_count": 0
            }
        
        # Record merge action on blockchain
        merge_transaction = None
        try:
            merge_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.USER_UPDATE,
                user_id=current_user["id"],
                data={
                    "action": "merge_session_views",
                    "session_id": session_id,
                    "user_id": current_user["id"],
                    "views_count": len(session_views),
                    "product_ids": [view["product_id"] for view in session_views]
                },
                metadata={
                    "source": "recently_viewed_route",
                    "merge_operation": True
                }
            )
            
            blockchain_service.add_transaction(merge_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Session merge transaction failed: {e}")
        
        # Update views with user ID
        for view in session_views:
            supabase.table("recently_viewed").update({
                "user_id": current_user["id"],
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", view["id"]).execute()
        
        return {
            "message": f"Merged {len(session_views)} views to user account",
            "session_id": session_id,
            "user_id": current_user["id"],
            "merged_count": len(session_views),
            "timestamp": datetime.utcnow().isoformat(),
            "blockchain_tx_id": merge_transaction.transaction_id if merge_transaction else None
        }
        
    except Exception as e:
        logger.error(f"Error merging session views: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to merge session views"
        )

# ========== HELPER FUNCTIONS ==========

async def update_product_view_count(product_id: str):
    """Update product view count in background."""
    try:
        # Get current view count
        result = supabase.table("products").select(
            "view_count"
        ).eq("id", product_id).execute()
        
        if result.data:
            current_count = result.data[0].get("view_count", 0)
            new_count = current_count + 1
            
            # Update product view count
            supabase.table("products").update({
                "view_count": new_count,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", product_id).execute()
            
    except Exception as e:
        logger.error(f"Error updating product view count: {str(e)}")

async def get_popular_products(limit: int = 10) -> List[Dict[str, Any]]:
    """Get popular products based on view count."""
    try:
        result = supabase.table("products").select(
            "id, title, price, images, shop_id, description, "
            "average_rating, rating_count, view_count, category_ids"
        ).eq("is_published", True).order(
            "view_count", desc=True
        ).limit(limit).execute()
        
        return result.data or []
        
    except Exception as e:
        logger.error(f"Error getting popular products: {str(e)}")
        return []

async def update_real_time_views(product_id: str, user_id: Optional[str] = None):
    """Update real-time view counter in Redis."""
    try:
        now = datetime.utcnow()
        
        # Increment total views counter
        await redis_client.incr(f"product:{product_id}:views:total")
        
        # Increment minute and hour counters
        minute_key = f"product:{product_id}:views:minute:{now.strftime('%Y%m%d%H%M')}"
        hour_key = f"product:{product_id}:views:hour:{now.strftime('%Y%m%d%H')}"
        
        await redis_client.incr(minute_key)
        await redis_client.incr(hour_key)
        
        # Set expiry for minute and hour counters
        await redis_client.expire(minute_key, 120)  # 2 minutes
        await redis_client.expire(hour_key, 7200)   # 2 hours
        
        # Track user-specific view if authenticated
        if user_id:
            user_view_key = f"user:{user_id}:product:{product_id}:views"
            await redis_client.incr(user_view_key)
            await redis_client.expire(user_view_key, 86400)  # 24 hours
            
    except Exception as e:
        logger.error(f"Error updating real-time views: {str(e)}")

async def get_real_time_view_stats(product_id: str) -> Dict[str, Any]:
    """Get real-time view statistics from Redis."""
    try:
        now = datetime.utcnow()
        
        # Get current minute views
        current_minute = now.strftime('%Y%m%d%H%M')
        prev_minute = (now - timedelta(minutes=1)).strftime('%Y%m%d%H%M')
        
        current_minute_views = await redis_client.get(f"product:{product_id}:views:minute:{current_minute}")
        prev_minute_views = await redis_client.get(f"product:{product_id}:views:minute:{prev_minute}")
        
        # Get current hour views
        current_hour = now.strftime('%Y%m%d%H')
        current_hour_views = await redis_client.get(f"product:{product_id}:views:hour:{current_hour}")
        
        # Get total views
        total_views = await redis_client.get(f"product:{product_id}:views:total")
        
        return {
            "product_id": product_id,
            "current_minute_views": int(current_minute_views) if current_minute_views else 0,
            "previous_minute_views": int(prev_minute_views) if prev_minute_views else 0,
            "current_hour_views": int(current_hour_views) if current_hour_views else 0,
            "total_views": int(total_views) if total_views else 0,
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting real-time view stats: {str(e)}")
        return {}

async def update_product_conversion(product_id: str, event_type: str):
    """Update product conversion metrics."""
    try:
        # Update product based on event type
        if event_type == "add_to_cart":
            # Get current cart count
            result = supabase.table("products").select(
                "cart_count"
            ).eq("id", product_id).execute()
            
            if result.data:
                current_count = result.data[0].get("cart_count", 0)
                new_count = current_count + 1
                
                supabase.table("products").update({
                    "cart_count": new_count,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", product_id).execute()
                
        elif event_type == "purchase":
            # Get current total sold
            result = supabase.table("products").select(
                "total_sold"
            ).eq("id", product_id).execute()
            
            if result.data:
                current_sold = result.data[0].get("total_sold", 0)
                new_sold = current_sold + 1
                
                supabase.table("products").update({
                    "total_sold": new_sold,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", product_id).execute()
                
    except Exception as e:
        logger.error(f"Error updating product conversion: {str(e)}")