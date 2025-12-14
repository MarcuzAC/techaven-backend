from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, asc, and_, or_, case
import logging
import math

from model.models import Review, ReviewHelpfulVote, Product, Order, OrderItem, User
# Update import path and fix ReviewReport reference
from app.model.models import (
    ReviewCreate, ReviewResponse, ReviewUpdate, ReviewHelpful,
    ReviewFilter, ProductResponse, ReviewStatus  # Import enums from your models
)
from services.blockchain_service import create_blockchain_transaction
from utils.pagination import apply_pagination
from utils.validation import validate_uuid, validate_rating

logger = logging.getLogger(__name__)

def create_review(db: Session, review_data: ReviewCreate, user_id: str) -> Review:
    """Create a new review."""
    try:
        # Check if product exists
        product = db.query(Product).filter(
            and_(
                Product.id == review_data.product_id,
                Product.is_published == True
            )
        ).first()
        
        if not product:
            raise ValueError("Product not found or not published")
        
        # Create review
        review = Review(
            product_id=review_data.product_id,
            user_id=user_id,
            order_id=review_data.order_id,
            rating=review_data.rating,
            title=review_data.title,
            comment=review_data.comment,
            images=review_data.images,
            is_anonymous=review_data.is_anonymous,
            status=ReviewStatus.PENDING.value,  # Default to pending for moderation
            is_verified_purchase=False  # Will be set based on order verification
        )
        
        # Verify purchase if order_id is provided
        if review_data.order_id:
            is_verified = verify_purchase_eligibility(
                db, user_id, review_data.product_id, review_data.order_id
            )
            review.is_verified_purchase = is_verified
        
        db.add(review)
        db.commit()
        db.refresh(review)
        
        # Update product rating stats
        update_product_rating_stats(db, review_data.product_id)
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="review_create",
            user_id=user_id,
            data={
                "review_id": review.id,
                "product_id": review_data.product_id,
                "rating": review_data.rating,
                "order_id": review_data.order_id
            }
        )
        
        return review
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating review: {str(e)}")
        raise

def get_reviews(db: Session, filter_params: ReviewFilter, helpful_first: bool = False) -> Tuple[List[Review], int]:
    """Get reviews with filtering and pagination."""
    try:
        query = db.query(Review)
        
        # Apply filters
        if filter_params.product_id:
            query = query.filter(Review.product_id == filter_params.product_id)
        
        if filter_params.user_id:
            query = query.filter(Review.user_id == filter_params.user_id)
        
        if filter_params.shop_id:
            # Get product IDs for this shop
            product_ids = db.query(Product.id).filter(Product.shop_id == filter_params.shop_id).all()
            product_ids = [pid[0] for pid in product_ids]
            query = query.filter(Review.product_id.in_(product_ids))
        
        if filter_params.rating:
            query = query.filter(Review.rating == filter_params.rating)
        
        if filter_params.status:
            query = query.filter(Review.status == filter_params.status.value if isinstance(filter_params.status, ReviewStatus) else filter_params.status)
        else:
            # Default to approved reviews only
            query = query.filter(Review.status == ReviewStatus.APPROVED.value)
        
        if filter_params.verified_purchase is not None:
            query = query.filter(Review.is_verified_purchase == filter_params.verified_purchase)
        
        if filter_params.start_date:
            query = query.filter(Review.created_at >= filter_params.start_date)
        
        if filter_params.end_date:
            query = query.filter(Review.created_at <= filter_params.end_date)
        
        # Apply sorting
        if helpful_first:
            # Sort by helpful count first, then by other criteria
            query = query.order_by(
                desc(Review.helpful_count),
                desc(Review.created_at)
            )
        else:
            if filter_params.sort_by == "rating":
                order_by = Review.rating
            elif filter_params.sort_by == "helpful_count":
                order_by = Review.helpful_count
            else:
                order_by = Review.created_at
            
            if filter_params.sort_order == "asc":
                query = query.order_by(asc(order_by))
            else:
                query = query.order_by(desc(order_by))
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        query = apply_pagination(query, filter_params.offset, filter_params.limit)
        
        reviews = query.all()
        return reviews, total
        
    except Exception as e:
        logger.error(f"Error getting reviews: {str(e)}")
        raise

def get_review_by_id(db: Session, review_id: str) -> Optional[Review]:
    """Get review by ID."""
    try:
        review = db.query(Review).filter(Review.id == review_id).first()
        return review
    except Exception as e:
        logger.error(f"Error getting review by ID: {str(e)}")
        return None

def update_review(db: Session, review_id: str, update_data: ReviewUpdate) -> Optional[Review]:
    """Update review."""
    try:
        review = get_review_by_id(db, review_id)
        if not review:
            return None
        
        # Check if review can be modified
        if review.status == ReviewStatus.DELETED.value:
            raise ValueError("Cannot update a deleted review")
        
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(review, field) and value is not None:
                setattr(review, field, value)
        
        review.updated_at = datetime.utcnow()
        
        # If rating changed, update product stats
        if "rating" in update_dict and update_dict["rating"] != review.rating:
            update_product_rating_stats(db, review.product_id)
        
        db.commit()
        db.refresh(review)
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="review_update",
            user_id=review.user_id,
            data={
                "review_id": review_id,
                "changes": update_dict,
                "updated_at": datetime.utcnow().isoformat()
            }
        )
        
        return review
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating review: {str(e)}")
        return None

def delete_review(db: Session, review_id: str) -> bool:
    """Delete review (soft delete)."""
    try:
        review = get_review_by_id(db, review_id)
        if not review:
            return False
        
        # Soft delete
        review.status = ReviewStatus.DELETED.value
        review.deleted_at = datetime.utcnow()
        review.updated_at = datetime.utcnow()
        
        # Update product rating stats
        update_product_rating_stats(db, review.product_id)
        
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="review_delete",
            user_id=review.user_id,
            data={"review_id": review_id}
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting review: {str(e)}")
        return False

def mark_review_helpful(db: Session, review_id: str, user_id: str, is_helpful: bool) -> Optional[Review]:
    """Mark review as helpful or not helpful."""
    try:
        review = get_review_by_id(db, review_id)
        if not review or review.status != ReviewStatus.APPROVED.value:
            return None
        
        # Check if user is trying to rate their own review
        if review.user_id == user_id:
            raise ValueError("Cannot rate your own review")
        
        # Check if user has already voted
        existing_vote = db.query(ReviewHelpfulVote).filter(
            and_(
                ReviewHelpfulVote.review_id == review_id,
                ReviewHelpfulVote.user_id == user_id
            )
        ).first()
        
        if existing_vote:
            # Update existing vote
            if existing_vote.is_helpful != is_helpful:
                # Adjust counts
                if existing_vote.is_helpful:
                    review.helpful_count = max(0, review.helpful_count - 1)
                else:
                    review.not_helpful_count = max(0, review.not_helpful_count - 1)
                
                existing_vote.is_helpful = is_helpful
                
                if is_helpful:
                    review.helpful_count += 1
                else:
                    review.not_helpful_count += 1
        else:
            # Create new vote
            vote = ReviewHelpfulVote(
                review_id=review_id,
                user_id=user_id,
                is_helpful=is_helpful
            )
            db.add(vote)
            
            if is_helpful:
                review.helpful_count += 1
            else:
                review.not_helpful_count += 1
        
        review.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(review)
        
        return review
    except Exception as e:
        db.rollback()
        logger.error(f"Error marking review helpful: {str(e)}")
        return None

def get_product_reviews_stats(db: Session, product_id: str) -> Dict[str, Any]:
    """Get review statistics for a product."""
    try:
        # Get all approved reviews for product
        reviews = db.query(Review).filter(
            and_(
                Review.product_id == product_id,
                Review.status == ReviewStatus.APPROVED.value
            )
        ).all()
        
        if not reviews:
            return {
                "average_rating": 0,
                "total_reviews": 0,
                "rating_distribution": {},
                "verified_purchases": 0,
                "with_images": 0,
                "helpful_reviews": 0
            }
        
        # Calculate statistics
        total_reviews = len(reviews)
        total_rating = sum(review.rating for review in reviews)
        average_rating = total_rating / total_reviews
        
        # Rating distribution
        rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for review in reviews:
            rating_distribution[review.rating] = rating_distribution.get(review.rating, 0) + 1
        
        # Other stats
        verified_purchases = sum(1 for review in reviews if review.is_verified_purchase)
        with_images = sum(1 for review in reviews if review.images and len(review.images) > 0)
        helpful_reviews = sum(1 for review in reviews if review.helpful_count > 0)
        
        return {
            "average_rating": round(average_rating, 1),
            "total_reviews": total_reviews,
            "rating_distribution": rating_distribution,
            "verified_purchases": verified_purchases,
            "with_images": with_images,
            "helpful_reviews": helpful_reviews
        }
    except Exception as e:
        logger.error(f"Error getting product reviews stats: {str(e)}")
        return {}

def get_user_reviews(db: Session, user_id: str, limit: int = 20, offset: int = 0) -> List[Review]:
    """Get reviews by a specific user."""
    try:
        reviews = db.query(Review).filter(
            and_(
                Review.user_id == user_id,
                Review.status != ReviewStatus.DELETED.value
            )
        ).order_by(desc(Review.created_at)).offset(offset).limit(limit).all()
        
        return reviews
    except Exception as e:
        logger.error(f"Error getting user reviews: {str(e)}")
        return []

def verify_purchase_eligibility(db: Session, user_id: str, product_id: str, order_id: str) -> bool:
    """Verify if user purchased the product and is eligible to review."""
    try:
        # Check if order exists and belongs to user
        order = db.query(Order).filter(
            and_(
                Order.id == order_id,
                Order.user_id == user_id,
                Order.status == "delivered"  # Only delivered orders can be reviewed
            )
        ).first()
        
        if not order:
            return False
        
        # Check if order contains the product
        order_item = db.query(OrderItem).filter(
            and_(
                OrderItem.order_id == order_id,
                OrderItem.product_id == product_id
            )
        ).first()
        
        if not order_item:
            return False
        
        # Check if review period has expired (e.g., 90 days after delivery)
        review_period_days = 90
        if order.delivered_at:
            review_deadline = order.delivered_at + timedelta(days=review_period_days)
            if datetime.utcnow() > review_deadline:
                return False
        
        # Check if user has already reviewed this product from this order
        existing_review = db.query(Review).filter(
            and_(
                Review.order_id == order_id,
                Review.product_id == product_id,
                Review.user_id == user_id,
                Review.status != ReviewStatus.DELETED.value
            )
        ).first()
        
        if existing_review:
            return False
        
        return True
    except Exception as e:
        logger.error(f"Error verifying purchase eligibility: {str(e)}")
        return False

def moderate_review(db: Session, review_id: str, status: ReviewStatus, moderator_id: str, 
                   notes: str = None) -> Optional[Review]:
    """Moderate a review (approve/reject)."""
    try:
        review = get_review_by_id(db, review_id)
        if not review:
            return None
        
        # Update review
        old_status = review.status
        review.status = status.value if isinstance(status, ReviewStatus) else status
        review.moderated_by = moderator_id
        review.moderated_at = datetime.utcnow()
        review.moderator_notes = notes
        review.updated_at = datetime.utcnow()
        
        # If status changed to/from approved, update product rating
        if (old_status == ReviewStatus.APPROVED.value and review.status != ReviewStatus.APPROVED.value) or \
           (old_status != ReviewStatus.APPROVED.value and review.status == ReviewStatus.APPROVED.value):
            update_product_rating_stats(db, review.product_id)
        
        db.commit()
        db.refresh(review)
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="review_moderate",
            user_id=moderator_id,
            data={
                "review_id": review_id,
                "old_status": old_status,
                "new_status": review.status,
                "notes": notes,
                "moderated_at": datetime.utcnow().isoformat()
            }
        )
        
        return review
    except Exception as e:
        db.rollback()
        logger.error(f"Error moderating review: {str(e)}")
        return None

def get_recent_reviews(db: Session, limit: int = 10, shop_id: str = None) -> List[Review]:
    """Get recent approved reviews."""
    try:
        query = db.query(Review).filter(
            Review.status == ReviewStatus.APPROVED.value
        ).order_by(desc(Review.created_at))
        
        if shop_id:
            # Get product IDs for this shop
            product_ids = db.query(Product.id).filter(Product.shop_id == shop_id).all()
            product_ids = [pid[0] for pid in product_ids]
            query = query.filter(Review.product_id.in_(product_ids))
        
        reviews = query.limit(limit).all()
        return reviews
    except Exception as e:
        logger.error(f"Error getting recent reviews: {str(e)}")
        return []

def get_top_helpful_reviews(db: Session, limit: int = 10, days: int = 30) -> List[Review]:
    """Get top helpful reviews from the last N days."""
    try:
        date_threshold = datetime.utcnow() - timedelta(days=days)
        
        reviews = db.query(Review).filter(
            and_(
                Review.status == ReviewStatus.APPROVED.value,
                Review.created_at >= date_threshold,
                Review.helpful_count > 0
            )
        ).order_by(
            desc(Review.helpful_count),
            desc(Review.created_at)
        ).limit(limit).all()
        
        return reviews
    except Exception as e:
        logger.error(f"Error getting top helpful reviews: {str(e)}")
        return []

def calculate_product_rating(db: Session, product_id: str) -> None:
    """Calculate and update product rating based on approved reviews."""
    try:
        # Get all approved reviews for product
        reviews = db.query(Review).filter(
            and_(
                Review.product_id == product_id,
                Review.status == ReviewStatus.APPROVED.value
            )
        ).all()
        
        if not reviews:
            # No approved reviews, reset rating
            product = db.query(Product).filter(Product.id == product_id).first()
            if product:
                product.average_rating = None
                product.rating_count = 0
                db.commit()
            return
        
        # Calculate new rating
        total_rating = sum(review.rating for review in reviews)
        average_rating = total_rating / len(reviews)
        
        # Update product
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            product.average_rating = round(average_rating, 1)
            product.rating_count = len(reviews)
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error calculating product rating: {str(e)}")

def check_review_eligibility(db: Session, user_id: str, product_id: str) -> Dict[str, Any]:
    """Check if user is eligible to review a product."""
    try:
        # Check if product exists
        product = db.query(Product).filter(
            and_(
                Product.id == product_id,
                Product.is_published == True
            )
        ).first()
        
        if not product:
            return {"can_review": False, "reason": "Product not found"}
        
        # Check if user has already reviewed this product
        existing_review = db.query(Review).filter(
            and_(
                Review.product_id == product_id,
                Review.user_id == user_id,
                Review.status != ReviewStatus.DELETED.value
            )
        ).first()
        
        if existing_review:
            return {"can_review": False, "reason": "Already reviewed this product"}
        
        # Check if user has purchased this product
        orders_with_product = db.query(Order).join(OrderItem).filter(
            and_(
                Order.user_id == user_id,
                OrderItem.product_id == product_id,
                Order.status == "delivered"
            )
        ).all()
        
        if not orders_with_product:
            return {"can_review": False, "reason": "Must purchase product before reviewing"}
        
        # Check if review period has expired for all purchases
        review_period_days = 90
        can_review = False
        for order in orders_with_product:
            if order.delivered_at:
                review_deadline = order.delivered_at + timedelta(days=review_period_days)
                if datetime.utcnow() <= review_deadline:
                    can_review = True
                    break
        
        if not can_review:
            return {"can_review": False, "reason": "Review period has expired"}
        
        return {"can_review": True, "reason": "Eligible to review"}
    except Exception as e:
        logger.error(f"Error checking review eligibility: {str(e)}")
        return {"can_review": False, "reason": "Error checking eligibility"}

def update_product_rating_stats(db: Session, product_id: str) -> None:
    """Update product rating statistics."""
    try:
        calculate_product_rating(db, product_id)
    except Exception as e:
        logger.error(f"Error updating product rating stats: {str(e)}")

def report_review(db: Session, review_id: str, user_id: str, reason: str, 
                 details: str = None) -> bool:
    """Report a review for inappropriate content."""
    try:
        review = get_review_by_id(db, review_id)
        if not review:
            return False
        
        # Check if user has already reported this review
        # Note: ReviewReport model might not exist in your models, 
        # so we'll check if the review is already flagged
        if review.status == ReviewStatus.FLAGGED.value:
            return False
        
        # Flag the review for moderation
        review.status = ReviewStatus.FLAGGED.value
        review.flagged_at = datetime.utcnow()
        review.flag_reason = reason
        review.flag_details = details
        review.updated_at = datetime.utcnow()
        
        # Optional: Create a review report entry if you have the model
        # For now, we'll just flag the review
        
        db.commit()
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error reporting review: {str(e)}")
        return False

def get_shop_review_analytics(db: Session, shop_id: str, start_date: datetime = None, 
                             end_date: datetime = None) -> Dict[str, Any]:
    """Get review analytics for a shop."""
    try:
        # Get shop products
        products = db.query(Product).filter(Product.shop_id == shop_id).all()
        product_ids = [p.id for p in products]
        
        if not product_ids:
            return {
                "shop_id": shop_id,
                "average_rating": 0,
                "total_reviews": 0,
                "rating_distribution": {},
                "top_products": [],
                "recent_reviews": []
            }
        
        # Set default date range
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        # Get reviews for shop products
        reviews_query = db.query(Review).filter(
            and_(
                Review.product_id.in_(product_ids),
                Review.status == ReviewStatus.APPROVED.value,
                Review.created_at.between(start_date, end_date)
            )
        )
        
        total_reviews = reviews_query.count()
        
        # Calculate average rating
        avg_rating_result = db.query(func.avg(Review.rating)).filter(
            and_(
                Review.product_id.in_(product_ids),
                Review.status == ReviewStatus.APPROVED.value,
                Review.created_at.between(start_date, end_date)
            )
        ).first()
        
        average_rating = avg_rating_result[0] or 0
        
        # Get rating distribution
        distribution_query = db.query(
            Review.rating,
            func.count(Review.id).label('count')
        ).filter(
            and_(
                Review.product_id.in_(product_ids),
                Review.status == ReviewStatus.APPROVED.value,
                Review.created_at.between(start_date, end_date)
            )
        ).group_by(Review.rating).order_by(Review.rating.desc())
        
        rating_distribution = {str(row.rating): row.count for row in distribution_query.all()}
        
        # Get top products by rating
        top_products_query = db.query(
            Product.id,
            Product.title,
            func.avg(Review.rating).label('avg_rating'),
            func.count(Review.id).label('review_count')
        ).join(Review, Review.product_id == Product.id).filter(
            and_(
                Product.shop_id == shop_id,
                Review.status == ReviewStatus.APPROVED.value,
                Review.created_at.between(start_date, end_date)
            )
        ).group_by(Product.id, Product.title).order_by(
            desc('avg_rating'),
            desc('review_count')
        ).limit(5)
        
        top_products = []
        for row in top_products_query.all():
            top_products.append({
                "product_id": row.id,
                "title": row.title,
                "average_rating": float(row.avg_rating) if row.avg_rating else 0,
                "review_count": row.review_count
            })
        
        # Get recent reviews
        recent_reviews = reviews_query.order_by(desc(Review.created_at)).limit(10).all()
        
        return {
            "shop_id": shop_id,
            "date_range": {"start_date": start_date, "end_date": end_date},
            "average_rating": round(float(average_rating), 1),
            "total_reviews": total_reviews,
            "rating_distribution": rating_distribution,
            "top_products": top_products,
            "recent_reviews": [
                {
                    "id": review.id,
                    "product_id": review.product_id,
                    "rating": review.rating,
                    "comment": review.comment[:100] + "..." if len(review.comment) > 100 else review.comment,
                    "created_at": review.created_at.isoformat() if review.created_at else None
                }
                for review in recent_reviews
            ]
        }
    except Exception as e:
        logger.error(f"Error getting shop review analytics: {str(e)}")
        return {}