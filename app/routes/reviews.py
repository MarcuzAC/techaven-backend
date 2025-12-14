from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
import uuid
from app.database import supabase
from app.dependencies import get_current_user
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType
import json

router = APIRouter(prefix="/reviews", tags=["reviews"])
logger = logging.getLogger(__name__)

# ========== CORE ENDPOINTS ==========

@router.get("/")
async def get_reviews_list(
    current_user: dict = Depends(get_current_user),
    product_id: Optional[str] = Query(None, description="Filter by product ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filter by rating"),
    status: Optional[str] = Query(None, description="Filter by review status"),
    verified_purchase: Optional[bool] = Query(None, description="Filter by verified purchase"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get reviews with filtering and pagination.
    """
    try:
        # Build query - using the exact column names from your database
        query = supabase.table("reviews").select(
            "id, product_id, user_id, order_id, rating, title, comment, "
            "images, is_anonymous, status, helpful_count, not_helpful_count, "
            "is_verified_purchase, created_at, updated_at, blockchain_tx_id",
            count="exact"
        )
        
        # Apply filters
        if product_id:
            query = query.eq("product_id", product_id)
        if user_id:
            query = query.eq("user_id", user_id)
        if rating:
            query = query.eq("rating", rating)
        if status:
            query = query.eq("status", status)
        if verified_purchase is not None:
            query = query.eq("is_verified_purchase", verified_purchase)
        
        # Apply pagination and sorting
        query = query.order("created_at", desc=True)
        query = query.range(offset, offset + limit - 1)
        
        # Execute query
        result = query.execute()
        
        # Get user and product information for each review
        reviews_data = []
        for review in result.data:
            # Get user info if not anonymous
            user_info = None
            if not review.get("is_anonymous"):
                user_result = supabase.table("users").select(
                    "id, name, profile_picture"
                ).eq("id", review["user_id"]).execute()
                
                if user_result.data:
                    user = user_result.data[0]
                    user_info = {
                        "id": user["id"],
                        "name": user["name"],
                        "profile_picture": user.get("profile_picture")
                    }
            
            # Get product info
            product_result = supabase.table("products").select(
                "id, title, price, images"
            ).eq("id", review["product_id"]).execute()
            
            product_info = None
            if product_result.data:
                product = product_result.data[0]
                product_info = {
                    "id": product["id"],
                    "title": product["title"],
                    "price": product["price"],
                    "images": product.get("images") or []
                }
            
            reviews_data.append({
                "id": review["id"],
                "product_id": review["product_id"],
                "user_id": review["user_id"],
                "order_id": review["order_id"],
                "rating": review["rating"],
                "title": review["title"],
                "comment": review["comment"],
                "images": review.get("images") or [],
                "is_anonymous": review["is_anonymous"],
                "status": review["status"],
                "helpful_count": review["helpful_count"],
                "not_helpful_count": review["not_helpful_count"],
                "is_verified_purchase": review["is_verified_purchase"],
                "created_at": review["created_at"],
                "updated_at": review["updated_at"],
                "blockchain_tx_id": review.get("blockchain_tx_id"),
                "user": user_info,
                "product": product_info
            })
        
        return {
            "data": reviews_data,
            "pagination": {
                "total": result.count,
                "skip": offset,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching reviews: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch reviews"
        )

@router.get("/product/{product_id}")
async def get_product_reviews(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    rating: Optional[int] = Query(None, ge=1, le=5),
    verified_purchase: Optional[bool] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0)
):
    """
    Get reviews for a specific product.
    """
    try:
        # Validate product exists and is published
        product_result = supabase.table("products").select(
            "id, title, price, images, is_published"
        ).eq("id", product_id).execute()
        
        if not product_result.data or not product_result.data[0].get("is_published", True):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        product = product_result.data[0]
        
        # Build query for approved reviews
        query = supabase.table("reviews").select(
            "id, product_id, user_id, order_id, rating, title, comment, "
            "images, is_anonymous, status, helpful_count, not_helpful_count, "
            "is_verified_purchase, created_at, updated_at, blockchain_tx_id"
        ).eq("product_id", product_id).eq("status", "approved")
        
        # Apply filters
        if rating:
            query = query.eq("rating", rating)
        if verified_purchase is not None:
            query = query.eq("is_verified_purchase", verified_purchase)
        
        # Get reviews sorted by helpfulness and recency
        query = query.order("helpful_count", desc=True).order("created_at", desc=True)
        query = query.range(offset, offset + limit - 1)
        
        result = query.execute()
        
        # Transform response
        reviews_data = []
        for review in result.data:
            # Get user info if not anonymous
            user_info = None
            if not review.get("is_anonymous"):
                user_result = supabase.table("users").select(
                    "id, name, profile_picture"
                ).eq("id", review["user_id"]).execute()
                
                if user_result.data:
                    user = user_result.data[0]
                    user_info = {
                        "id": user["id"],
                        "name": user["name"],
                        "profile_picture": user.get("profile_picture")
                    }
            
            reviews_data.append({
                "id": review["id"],
                "product_id": review["product_id"],
                "user_id": review["user_id"],
                "order_id": review["order_id"],
                "rating": review["rating"],
                "title": review["title"],
                "comment": review["comment"],
                "images": review.get("images") or [],
                "is_anonymous": review["is_anonymous"],
                "status": review["status"],
                "helpful_count": review["helpful_count"],
                "not_helpful_count": review["not_helpful_count"],
                "is_verified_purchase": review["is_verified_purchase"],
                "created_at": review["created_at"],
                "updated_at": review["updated_at"],
                "blockchain_tx_id": review.get("blockchain_tx_id"),
                "user": user_info,
                "product": {
                    "id": product["id"],
                    "title": product["title"],
                    "price": product["price"],
                    "images": product.get("images") or []
                }
            })
        
        return {
            "data": reviews_data,
            "pagination": {
                "skip": offset,
                "limit": limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product reviews: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch product reviews"
        )

@router.get("/product/{product_id}/stats")
async def get_product_review_stats(
    product_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get review statistics for a product.
    """
    try:
        # Validate product exists
        product_result = supabase.table("products").select(
            "id, title"
        ).eq("id", product_id).eq("is_published", True).execute()
        
        if not product_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Get all approved reviews for this product
        reviews_result = supabase.table("reviews").select(
            "rating, images, is_verified_purchase, helpful_count"
        ).eq("product_id", product_id).eq("status", "approved").execute()
        
        reviews = reviews_result.data
        total_reviews = len(reviews)
        
        if total_reviews == 0:
            return {
                "product_id": product_id,
                "average_rating": 0,
                "total_reviews": 0,
                "rating_distribution": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0},
                "verified_purchases": 0,
                "with_images": 0,
                "helpful_reviews": 0
            }
        
        # Calculate statistics
        total_rating = sum(review["rating"] for review in reviews)
        average_rating = round(total_rating / total_reviews, 1)
        
        # Rating distribution
        rating_counts = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
        for review in reviews:
            rating_str = str(review["rating"])
            if rating_str in rating_counts:
                rating_counts[rating_str] += 1
        
        # Other statistics
        verified_purchases = sum(1 for review in reviews if review.get("is_verified_purchase"))
        with_images = sum(1 for review in reviews if review.get("images") and len(review["images"]) > 0)
        helpful_reviews = sum(1 for review in reviews if review.get("helpful_count", 0) > 0)
        
        return {
            "product_id": product_id,
            "average_rating": average_rating,
            "total_reviews": total_reviews,
            "rating_distribution": rating_counts,
            "verified_purchases": verified_purchases,
            "with_images": with_images,
            "helpful_reviews": helpful_reviews
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product review stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch product review stats"
        )

@router.get("/user/me")
async def get_my_reviews(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get reviews by the current user.
    """
    try:
        # Get user's reviews
        query = supabase.table("reviews").select(
            "id, product_id, user_id, order_id, rating, title, comment, "
            "images, is_anonymous, status, helpful_count, not_helpful_count, "
            "is_verified_purchase, created_at, updated_at, blockchain_tx_id"
        ).eq("user_id", current_user["id"]).order("created_at", desc=True)
        
        query = query.range(offset, offset + limit - 1)
        result = query.execute()
        
        # Transform response
        reviews_data = []
        for review in result.data:
            # Get product info
            product_result = supabase.table("products").select(
                "id, title, price, images"
            ).eq("id", review["product_id"]).execute()
            
            product_info = None
            if product_result.data:
                product = product_result.data[0]
                product_info = {
                    "id": product["id"],
                    "title": product["title"],
                    "price": product["price"],
                    "images": product.get("images") or []
                }
            
            reviews_data.append({
                "id": review["id"],
                "product_id": review["product_id"],
                "user_id": review["user_id"],
                "order_id": review["order_id"],
                "rating": review["rating"],
                "title": review["title"],
                "comment": review["comment"],
                "images": review.get("images") or [],
                "is_anonymous": review["is_anonymous"],
                "status": review["status"],
                "helpful_count": review["helpful_count"],
                "not_helpful_count": review["not_helpful_count"],
                "is_verified_purchase": review["is_verified_purchase"],
                "created_at": review["created_at"],
                "updated_at": review["updated_at"],
                "blockchain_tx_id": review.get("blockchain_tx_id"),
                "user": {
                    "id": current_user["id"],
                    "name": current_user["name"],
                    "profile_picture": current_user.get("profile_picture")
                } if not review["is_anonymous"] else None,
                "product": product_info
            })
        
        return {
            "data": reviews_data,
            "pagination": {
                "skip": offset,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching user reviews: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user reviews"
        )

@router.get("/{review_id}")
async def get_review(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific review by ID.
    """
    try:
        # Get review
        result = supabase.table("reviews").select(
            "id, product_id, user_id, order_id, rating, title, comment, "
            "images, is_anonymous, status, helpful_count, not_helpful_count, "
            "is_verified_purchase, created_at, updated_at, blockchain_tx_id"
        ).eq("id", review_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found"
            )
        
        review = result.data[0]
        
        # Get user info if not anonymous
        user_info = None
        if not review.get("is_anonymous"):
            user_result = supabase.table("users").select(
                "id, name, profile_picture"
            ).eq("id", review["user_id"]).execute()
            
            if user_result.data:
                user = user_result.data[0]
                user_info = {
                    "id": user["id"],
                    "name": user["name"],
                    "profile_picture": user.get("profile_picture")
                }
        
        # Get product info
        product_result = supabase.table("products").select(
            "id, title, price, images"
        ).eq("id", review["product_id"]).execute()
        
        product_info = None
        if product_result.data:
            product = product_result.data[0]
            product_info = {
                "id": product["id"],
                "title": product["title"],
                "price": product["price"],
                "images": product.get("images") or []
            }
        
        return {
            "id": review["id"],
            "product_id": review["product_id"],
            "user_id": review["user_id"],
            "order_id": review["order_id"],
            "rating": review["rating"],
            "title": review["title"],
            "comment": review["comment"],
            "images": review.get("images") or [],
            "is_anonymous": review["is_anonymous"],
            "status": review["status"],
            "helpful_count": review["helpful_count"],
            "not_helpful_count": review["not_helpful_count"],
            "is_verified_purchase": review["is_verified_purchase"],
            "created_at": review["created_at"],
            "updated_at": review["updated_at"],
            "blockchain_tx_id": review.get("blockchain_tx_id"),
            "user": user_info,
            "product": product_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch review"
        )

@router.post("/")
async def create_product_review(
    review_data: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new review for a product.
    """
    try:
        # Validate required fields
        required_fields = ["product_id", "rating", "title", "comment"]
        for field in required_fields:
            if field not in review_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required field: {field}"
                )
        
        # Check if product exists and is published
        product_result = supabase.table("products").select(
            "id, title, price, images, is_published"
        ).eq("id", review_data["product_id"]).execute()
        
        if not product_result.data or not product_result.data[0].get("is_published", True):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        product = product_result.data[0]
        
        # Check if user has already reviewed this product
        existing_review = supabase.table("reviews").select("id").eq(
            "product_id", review_data["product_id"]
        ).eq("user_id", current_user["id"]).neq("status", "deleted").execute()
        
        if existing_review.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already reviewed this product"
            )
        
        # Verify purchase if order_id is provided
        is_verified_purchase = False
        if review_data.get("order_id"):
            # Check if order contains this product and belongs to user
            order_item_result = supabase.table("order_items").select(
                "id"
            ).eq("product_id", review_data["product_id"]).eq(
                "order_id", review_data["order_id"]
            ).execute()
            
            # Check if order exists and belongs to user
            order_result = supabase.table("orders").select(
                "user_id, status"
            ).eq("id", review_data["order_id"]).eq("user_id", current_user["id"]).execute()
            
            if not order_item_result.data or not order_result.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Order does not contain this product or does not belong to you"
                )
            
            # Check if order is delivered or completed
            order_status = order_result.data[0]["status"]
            if order_status not in ["delivered", "completed"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Can only review products from delivered or completed orders"
                )
            
            is_verified_purchase = True
        
        # Create review data
        review_id = str(uuid.uuid4())
        review_payload = {
            "id": review_id,
            "product_id": review_data["product_id"],
            "user_id": current_user["id"],
            "order_id": review_data.get("order_id"),
            "rating": review_data["rating"],
            "title": review_data["title"],
            "comment": review_data["comment"],
            "images": review_data.get("images") or [],
            "is_anonymous": review_data.get("is_anonymous", False),
            "status": "pending",  # Default to pending for moderation
            "helpful_count": 0,
            "not_helpful_count": 0,
            "is_verified_purchase": is_verified_purchase,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Create review on blockchain
        review_transaction = None
        try:
            review_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.REVIEW_CREATE,
                user_id=current_user["id"],
                product_id=review_data["product_id"],
                data={
                    "action": "review_creation",
                    "review_id": review_id,
                    "product_title": product["title"],
                    "rating": review_data["rating"],
                    "is_anonymous": review_data.get("is_anonymous", False),
                    "is_verified_purchase": is_verified_purchase
                },
                metadata={
                    "source": "reviews_route",
                    "has_images": len(review_data.get("images") or []) > 0,
                    "has_order": bool(review_data.get("order_id"))
                }
            )
            
            blockchain_service.add_transaction(review_transaction)
            
            # Add blockchain transaction ID to review
            review_payload["blockchain_tx_id"] = review_transaction.transaction_id
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Review creation transaction failed: {e}")
        
        # Create review in database
        result = supabase.table("reviews").insert(review_payload).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create review"
            )
        
        created_review = result.data[0]
        
        # Update product rating stats in background
        background_tasks.add_task(
            update_product_rating_stats,
            review_data["product_id"]
        )
        
        # Prepare response
        user_info = None
        if not created_review["is_anonymous"]:
            user_info = {
                "id": current_user["id"],
                "name": current_user["name"],
                "profile_picture": current_user.get("profile_picture")
            }
        
        return {
            "message": "Review created successfully",
            "review": {
                "id": created_review["id"],
                "product_id": created_review["product_id"],
                "user_id": created_review["user_id"],
                "order_id": created_review["order_id"],
                "rating": created_review["rating"],
                "title": created_review["title"],
                "comment": created_review["comment"],
                "images": created_review.get("images") or [],
                "is_anonymous": created_review["is_anonymous"],
                "status": created_review["status"],
                "helpful_count": created_review["helpful_count"],
                "not_helpful_count": created_review["not_helpful_count"],
                "is_verified_purchase": created_review["is_verified_purchase"],
                "created_at": created_review["created_at"],
                "updated_at": created_review.get("updated_at"),
                "blockchain_tx_id": created_review.get("blockchain_tx_id"),
                "user": user_info,
                "product": {
                    "id": product["id"],
                    "title": product["title"],
                    "price": product["price"],
                    "images": product.get("images") or []
                }
            },
            "blockchain_tx_id": review_transaction.transaction_id if review_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create review"
        )

@router.put("/{review_id}")
async def update_review_details(
    review_id: str,
    review_data: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Update a review.
    """
    try:
        # Get existing review
        result = supabase.table("reviews").select("*").eq("id", review_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found"
            )
        
        review = result.data[0]
        
        # Check if user owns this review or is admin
        if review["user_id"] != current_user["id"] and current_user.get("type") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this review"
            )
        
        # Check if review can be modified
        if review["status"] == "deleted":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update a deleted review"
            )
        
        # Track if rating changed
        rating_changed = "rating" in review_data and review_data["rating"] != review["rating"]
        
        # Prepare update data
        update_data = {}
        allowed_fields = ["rating", "title", "comment", "images", "is_anonymous"]
        
        for field in allowed_fields:
            if field in review_data:
                update_data[field] = review_data[field]
        
        # Admin/moderator can update status
        if "status" in review_data and current_user.get("type") in ["admin", "moderator"]:
            update_data["status"] = review_data["status"]
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid fields to update"
            )
        
        update_data["updated_at"] = datetime.utcnow().isoformat()
        
        # Update review in database
        update_result = supabase.table("reviews").update(update_data).eq("id", review_id).execute()
        
        if not update_result.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update review"
            )
        
        updated_review = update_result.data[0]
        
        # Record update on blockchain
        update_transaction = None
        try:
            update_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.REVIEW_UPDATE,
                user_id=current_user["id"],
                product_id=review["product_id"],
                data={
                    "action": "review_update",
                    "review_id": review_id,
                    "updated_fields": list(update_data.keys()),
                    "old_rating": review["rating"] if rating_changed else None,
                    "new_rating": review_data.get("rating") if rating_changed else None,
                    "is_anonymous": updated_review["is_anonymous"]
                },
                metadata={
                    "source": "reviews_route",
                    "admin_action": current_user.get("type") in ["admin", "moderator"],
                    "rating_changed": rating_changed
                }
            )
            
            blockchain_service.add_transaction(update_transaction)
            
            # Update blockchain transaction ID
            supabase.table("reviews").update({
                "blockchain_tx_id": update_transaction.transaction_id
            }).eq("id", review_id).execute()
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Review update transaction failed: {e}")
        
        # Update product rating if rating changed
        if rating_changed:
            background_tasks.add_task(
                update_product_rating_stats,
                review["product_id"]
            )
        
        # Get user and product info for response
        user_info = None
        if not updated_review["is_anonymous"]:
            user_result = supabase.table("users").select(
                "id, name, profile_picture"
            ).eq("id", updated_review["user_id"]).execute()
            
            if user_result.data:
                user = user_result.data[0]
                user_info = {
                    "id": user["id"],
                    "name": user["name"],
                    "profile_picture": user.get("profile_picture")
                }
        
        product_result = supabase.table("products").select(
            "id, title, price, images"
        ).eq("id", updated_review["product_id"]).execute()
        
        product_info = None
        if product_result.data:
            product = product_result.data[0]
            product_info = {
                "id": product["id"],
                "title": product["title"],
                "price": product["price"],
                "images": product.get("images") or []
            }
        
        return {
            "message": "Review updated successfully",
            "review": {
                "id": updated_review["id"],
                "product_id": updated_review["product_id"],
                "user_id": updated_review["user_id"],
                "order_id": updated_review["order_id"],
                "rating": updated_review["rating"],
                "title": updated_review["title"],
                "comment": updated_review["comment"],
                "images": updated_review.get("images") or [],
                "is_anonymous": updated_review["is_anonymous"],
                "status": updated_review["status"],
                "helpful_count": updated_review["helpful_count"],
                "not_helpful_count": updated_review["not_helpful_count"],
                "is_verified_purchase": updated_review["is_verified_purchase"],
                "created_at": updated_review["created_at"],
                "updated_at": updated_review.get("updated_at"),
                "blockchain_tx_id": updated_review.get("blockchain_tx_id") or update_transaction.transaction_id if update_transaction else None,
                "user": user_info,
                "product": product_info
            },
            "updated_fields": list(update_data.keys()),
            "blockchain_tx_id": update_transaction.transaction_id if update_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update review"
        )

@router.delete("/{review_id}")
async def delete_review(
    review_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a review.
    """
    try:
        # Get review
        result = supabase.table("reviews").select("*").eq("id", review_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found"
            )
        
        review = result.data[0]
        
        # Check if user owns this review or is admin
        if review["user_id"] != current_user["id"] and current_user.get("type") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this review"
            )
        
        # Record deletion on blockchain
        delete_transaction = None
        try:
            # Get product info for blockchain record
            product_result = supabase.table("products").select(
                "id, title"
            ).eq("id", review["product_id"]).execute()
            
            product_title = "Unknown Product"
            if product_result.data:
                product_title = product_result.data[0]["title"]
            
            delete_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.REVIEW_DELETE,
                user_id=current_user["id"],
                product_id=review["product_id"],
                data={
                    "action": "review_deletion",
                    "review_id": review_id,
                    "product_title": product_title,
                    "original_rating": review["rating"],
                    "was_verified_purchase": review["is_verified_purchase"],
                    "helpful_count": review["helpful_count"]
                },
                metadata={
                    "source": "reviews_route",
                    "admin_action": current_user.get("type") == "admin",
                    "soft_delete": True
                }
            )
            
            blockchain_service.add_transaction(delete_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Review deletion transaction failed: {e}")
        
        # Soft delete by changing status
        update_result = supabase.table("reviews").update({
            "status": "deleted",
            "updated_at": datetime.utcnow().isoformat(),
            "blockchain_tx_id": delete_transaction.transaction_id if delete_transaction else review.get("blockchain_tx_id")
        }).eq("id", review_id).execute()
        
        # Update product rating stats
        background_tasks.add_task(
            update_product_rating_stats,
            review["product_id"]
        )
        
        return {
            "message": "Review deleted successfully",
            "review_id": review_id,
            "product_id": review["product_id"],
            "blockchain_tx_id": delete_transaction.transaction_id if delete_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete review"
        )

@router.post("/{review_id}/helpful")
async def mark_review_as_helpful(
    review_id: str,
    is_helpful: bool = Query(True, description="Mark as helpful (true) or not helpful (false)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Mark a review as helpful or not helpful.
    """
    try:
        # Get review
        result = supabase.table("reviews").select(
            "id, user_id, status, helpful_count, not_helpful_count"
        ).eq("id", review_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found"
            )
        
        review = result.data[0]
        
        # Check if review is approved
        if review["status"] != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rate unapproved reviews"
            )
        
        # Check if user is trying to rate their own review
        if review["user_id"] == current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rate your own review"
            )
        
        # Prepare update
        update_data = {
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if is_helpful:
            update_data["helpful_count"] = review.get("helpful_count", 0) + 1
        else:
            update_data["not_helpful_count"] = review.get("not_helpful_count", 0) + 1
        
        # Update review
        supabase.table("reviews").update(update_data).eq("id", review_id).execute()
        
        # Record helpful action on blockchain
        helpful_transaction = None
        try:
            helpful_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.REVIEW_HELPFUL,
                user_id=current_user["id"],
                data={
                    "action": "review_helpful_rating",
                    "review_id": review_id,
                    "is_helpful": is_helpful,
                    "review_owner_id": review["user_id"]
                },
                metadata={
                    "source": "reviews_route",
                    "voter_id": current_user["id"]
                }
            )
            
            blockchain_service.add_transaction(helpful_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Helpful rating transaction failed: {e}")
        
        return {
            "message": f"Review marked as {'helpful' if is_helpful else 'not helpful'}",
            "review_id": review_id,
            "is_helpful": is_helpful,
            "new_helpful_count": update_data.get("helpful_count", review.get("helpful_count")),
            "new_not_helpful_count": update_data.get("not_helpful_count", review.get("not_helpful_count")),
            "blockchain_tx_id": helpful_transaction.transaction_id if helpful_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking review as helpful: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark review as helpful"
        )

@router.get("/recent")
async def get_recent_reviews(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get recent approved reviews.
    """
    try:
        # Get recent approved reviews
        result = supabase.table("reviews").select(
            "id, product_id, user_id, order_id, rating, title, comment, "
            "images, is_anonymous, status, helpful_count, not_helpful_count, "
            "is_verified_purchase, created_at, updated_at, blockchain_tx_id"
        ).eq("status", "approved").order("created_at", desc=True).limit(limit).execute()
        
        reviews_data = []
        for review in result.data:
            # Get user info if not anonymous
            user_info = None
            if not review.get("is_anonymous"):
                user_result = supabase.table("users").select(
                    "id, name, profile_picture"
                ).eq("id", review["user_id"]).execute()
                
                if user_result.data:
                    user = user_result.data[0]
                    user_info = {
                        "id": user["id"],
                        "name": user["name"],
                        "profile_picture": user.get("profile_picture")
                    }
            
            # Get product info
            product_result = supabase.table("products").select(
                "id, title, price, images"
            ).eq("id", review["product_id"]).execute()
            
            product_info = None
            if product_result.data:
                product = product_result.data[0]
                product_info = {
                    "id": product["id"],
                    "title": product["title"],
                    "price": product["price"],
                    "images": product.get("images") or []
                }
            
            reviews_data.append({
                "id": review["id"],
                "product_id": review["product_id"],
                "user_id": review["user_id"],
                "order_id": review["order_id"],
                "rating": review["rating"],
                "title": review["title"],
                "comment": review["comment"],
                "images": review.get("images") or [],
                "is_anonymous": review["is_anonymous"],
                "status": review["status"],
                "helpful_count": review["helpful_count"],
                "not_helpful_count": review["not_helpful_count"],
                "is_verified_purchase": review["is_verified_purchase"],
                "created_at": review["created_at"],
                "updated_at": review.get("updated_at"),
                "blockchain_tx_id": review.get("blockchain_tx_id"),
                "user": user_info,
                "product": product_info
            })
        
        return {"data": reviews_data}
        
    except Exception as e:
        logger.error(f"Error fetching recent reviews: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch recent reviews"
        )

@router.post("/{review_id}/report")
async def report_review(
    review_id: str,
    report_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Report a review for inappropriate content.
    """
    try:
        # Validate report data
        reason = report_data.get("reason")
        if not reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Report reason is required"
            )
        
        # Get review
        result = supabase.table("reviews").select(
            "id, user_id, status, product_id"
        ).eq("id", review_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found"
            )
        
        review = result.data[0]
        
        # Check if user is reporting their own review
        if review["user_id"] == current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot report your own review"
            )
        
        # Flag the review
        supabase.table("reviews").update({
            "status": "flagged",
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", review_id).execute()
        
        # Record report on blockchain
        report_transaction = None
        try:
            report_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.REVIEW_REPORT,
                user_id=current_user["id"],
                product_id=review["product_id"],
                data={
                    "action": "review_report",
                    "review_id": review_id,
                    "reason": reason,
                    "details": report_data.get("details"),
                    "review_owner_id": review["user_id"]
                },
                metadata={
                    "source": "reviews_route",
                    "reporter_id": current_user["id"]
                }
            )
            
            blockchain_service.add_transaction(report_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Review report transaction failed: {e}")
        
        # Create report record
        report_id = str(uuid.uuid4())
        supabase.table("review_reports").insert({
            "id": report_id,
            "review_id": review_id,
            "user_id": current_user["id"],
            "reason": reason,
            "details": report_data.get("details"),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        return {
            "message": "Review reported successfully",
            "report_id": report_id,
            "review_id": review_id,
            "status": "flagged",
            "blockchain_tx_id": report_transaction.transaction_id if report_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reporting review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to report review"
        )

# ========== ADMIN/MODERATION ENDPOINTS ==========

@router.put("/{review_id}/moderate")
async def moderate_review_status(
    review_id: str,
    moderation_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Moderate a review (admin/moderator only).
    """
    try:
        # Check if user is admin or moderator
        if current_user.get("type") not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins and moderators can moderate reviews"
            )
        
        status = moderation_data.get("status")
        notes = moderation_data.get("notes")
        
        if not status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status is required for moderation"
            )
        
        # Get review
        result = supabase.table("reviews").select(
            "id, user_id, status, product_id, rating"
        ).eq("id", review_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found"
            )
        
        review = result.data[0]
        old_status = review["status"]
        
        # Update review status
        update_result = supabase.table("reviews").update({
            "status": status,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", review_id).execute()
        
        # Record moderation on blockchain
        moderation_transaction = None
        try:
            moderation_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.REVIEW_MODERATE,
                user_id=current_user["id"],
                product_id=review["product_id"],
                data={
                    "action": "review_moderation",
                    "review_id": review_id,
                    "old_status": old_status,
                    "new_status": status,
                    "notes": notes,
                    "rating": review["rating"],
                    "review_owner_id": review["user_id"]
                },
                metadata={
                    "source": "reviews_route",
                    "moderator_id": current_user["id"],
                    "moderator_role": current_user.get("type")
                }
            )
            
            blockchain_service.add_transaction(moderation_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Review moderation transaction failed: {e}")
        
        # Update product rating stats if status changed to/from approved
        if old_status != status and (status == "approved" or old_status == "approved"):
            update_product_rating_stats(review["product_id"])
        
        # Create moderation log
        log_id = str(uuid.uuid4())
        supabase.table("review_moderation_logs").insert({
            "id": log_id,
            "review_id": review_id,
            "moderator_id": current_user["id"],
            "old_status": old_status,
            "new_status": status,
            "notes": notes,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        # Get updated review for response
        updated_review = supabase.table("reviews").select("*").eq("id", review_id).execute()
        
        return {
            "message": f"Review status updated to {status}",
            "review_id": review_id,
            "old_status": old_status,
            "new_status": status,
            "moderator_id": current_user["id"],
            "product_id": review["product_id"],
            "blockchain_tx_id": moderation_transaction.transaction_id if moderation_transaction else None,
            "review": updated_review.data[0] if updated_review.data else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moderating review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to moderate review"
        )

@router.get("/admin/pending")
async def get_pending_reviews(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get pending reviews for moderation (admin/moderator only).
    """
    try:
        if current_user.get("type") not in ["admin", "moderator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins and moderators can view pending reviews"
            )
        
        # Get pending and flagged reviews
        result = supabase.table("reviews").select(
            "id, product_id, user_id, order_id, rating, title, comment, "
            "images, is_anonymous, status, helpful_count, not_helpful_count, "
            "is_verified_purchase, created_at, updated_at, blockchain_tx_id",
            count="exact"
        ).in_("status", ["pending", "flagged"]).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        reviews_data = []
        for review in result.data:
            # Get user info if not anonymous
            user_info = None
            if not review.get("is_anonymous"):
                user_result = supabase.table("users").select(
                    "id, name, profile_picture"
                ).eq("id", review["user_id"]).execute()
                
                if user_result.data:
                    user = user_result.data[0]
                    user_info = {
                        "id": user["id"],
                        "name": user["name"],
                        "profile_picture": user.get("profile_picture")
                    }
            
            # Get product info
            product_result = supabase.table("products").select(
                "id, title, price, images"
            ).eq("id", review["product_id"]).execute()
            
            product_info = None
            if product_result.data:
                product = product_result.data[0]
                product_info = {
                    "id": product["id"],
                    "title": product["title"],
                    "price": product["price"],
                    "images": product.get("images") or []
                }
            
            reviews_data.append({
                "id": review["id"],
                "product_id": review["product_id"],
                "user_id": review["user_id"],
                "order_id": review["order_id"],
                "rating": review["rating"],
                "title": review["title"],
                "comment": review["comment"],
                "images": review.get("images") or [],
                "is_anonymous": review["is_anonymous"],
                "status": review["status"],
                "helpful_count": review["helpful_count"],
                "not_helpful_count": review["not_helpful_count"],
                "is_verified_purchase": review["is_verified_purchase"],
                "created_at": review["created_at"],
                "updated_at": review.get("updated_at"),
                "blockchain_tx_id": review.get("blockchain_tx_id"),
                "user": user_info,
                "product": product_info
            })
        
        return {
            "data": reviews_data,
            "pagination": {
                "total": result.count,
                "skip": offset,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching pending reviews: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch pending reviews"
        )

# ========== HELPER FUNCTIONS ==========

def update_product_rating_stats(product_id: str):
    """
    Update product rating statistics after review changes.
    """
    try:
        # Get approved reviews for this product
        result = supabase.table("reviews").select(
            "rating"
        ).eq("product_id", product_id).eq("status", "approved").execute()
        
        reviews = result.data
        
        if not reviews:
            # Reset product stats if no approved reviews
            supabase.table("products").update({
                "average_rating": None,
                "rating_count": 0,
                "review_count": 0,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", product_id).execute()
            return
        
        # Calculate statistics
        total_rating = sum(review["rating"] for review in reviews)
        average_rating = total_rating / len(reviews)
        
        # Update product
        supabase.table("products").update({
            "average_rating": average_rating,
            "rating_count": len(reviews),
            "review_count": len(reviews),
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", product_id).execute()
        
        # Record stats update on blockchain
        try:
            stats_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.PRODUCT_UPDATE,
                product_id=product_id,
                data={
                    "action": "product_rating_update",
                    "product_id": product_id,
                    "new_average_rating": average_rating,
                    "total_reviews": len(reviews)
                },
                metadata={
                    "source": "reviews_stats_update",
                    "trigger": "review_change"
                }
            )
            
            blockchain_service.add_transaction(stats_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Product stats update transaction failed: {e}")
            
    except Exception as e:
        logger.error(f"Error updating product rating stats: {str(e)}")