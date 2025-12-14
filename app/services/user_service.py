from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, asc, and_, or_
import logging

from model.models import User, Shop, Order, Review, Address, Wishlist
# Update import path to match your project structure
from app.model.models import (
    UserResponse, UserUpdate, UserFilter, PaginatedResponse,
    UserStats, AddressResponse, AddressCreate, AddressUpdate,
    OrderStatus, UserType  # Import enums from your models
)
from services.blockchain_service import create_blockchain_transaction
from utils.pagination import apply_pagination
from utils.validation import validate_uuid

logger = logging.getLogger(__name__)

def get_users(db: Session, filter_params: UserFilter) -> Tuple[List[User], int]:
    """Get users with filtering and pagination."""
    try:
        query = db.query(User)
        
        # Apply filters
        if filter_params.type:
            query = query.filter(User.type == filter_params.type)
        
        if filter_params.is_active is not None:
            query = query.filter(User.is_active == filter_params.is_active)
        
        if filter_params.is_verified is not None:
            query = query.filter(User.is_verified == filter_params.is_verified)
        
        if filter_params.search:
            search_term = f"%{filter_params.search}%"
            query = query.filter(
                or_(
                    User.name.ilike(search_term),
                    User.email.ilike(search_term),
                    User.phone_number.ilike(search_term)
                )
            )
        
        if filter_params.created_after:
            query = query.filter(User.created_at >= filter_params.created_after)
        
        if filter_params.created_before:
            query = query.filter(User.created_at <= filter_params.created_before)
        
        # Apply sorting
        if filter_params.sort_by == "name":
            order_by = User.name
        elif filter_params.sort_by == "email":
            order_by = User.email
        else:
            order_by = User.created_at
        
        if filter_params.sort_order == "asc":
            query = query.order_by(asc(order_by))
        else:
            query = query.order_by(desc(order_by))
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        query = apply_pagination(query, filter_params.offset, filter_params.limit)
        
        users = query.all()
        return users, total
        
    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        raise

def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """Get user by ID with related data."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        return user
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}")
        return None

def get_user_with_details(db: Session, user_id: str) -> Optional[Dict[str, Any]]:
    """Get user with all related details."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        # Get user's shops
        shops = db.query(Shop).filter(
            and_(
                Shop.user_id == user_id,
                Shop.is_active == True
            )
        ).all()
        
        # Get user's addresses
        addresses = db.query(Address).filter(
            and_(
                Address.user_id == user_id,
                Address.is_deleted == False
            )
        ).all()
        
        # Get user's wishlists
        wishlists = db.query(Wishlist).filter(Wishlist.user_id == user_id).all()
        
        # Get user's recent orders
        recent_orders = db.query(Order).filter(
            Order.user_id == user_id
        ).order_by(desc(Order.created_at)).limit(5).all()
        
        # Get user's recent reviews
        recent_reviews = db.query(Review).filter(
            Review.user_id == user_id
        ).order_by(desc(Review.created_at)).limit(5).all()
        
        return {
            "user": user,
            "shops": shops,
            "addresses": addresses,
            "wishlists": wishlists,
            "recent_orders": recent_orders,
            "recent_reviews": recent_reviews,
            "stats": {
                "total_orders": db.query(Order).filter(Order.user_id == user_id).count(),
                "total_reviews": db.query(Review).filter(Review.user_id == user_id).count(),
                "total_shops": len(shops),
                "total_wishlists": len(wishlists)
            }
        }
    except Exception as e:
        logger.error(f"Error getting user with details: {str(e)}")
        return None

def update_user_profile(db: Session, user_id: str, update_data: UserUpdate) -> Optional[User]:
    """Update user profile."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        # Update fields
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(user, field) and value is not None:
                setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="user_update",
            user_id=user_id,
            data={"updates": update_dict}
        )
        
        return user
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user profile: {str(e)}")
        return None

def delete_user_account(db: Session, user_id: str, reason: str = None) -> bool:
    """Delete user account (soft delete)."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        # Soft delete user
        user.is_active = False
        user.deleted_at = datetime.utcnow()
        user.deletion_reason = reason
        user.updated_at = datetime.utcnow()
        
        # Deactivate all user's shops
        db.query(Shop).filter(Shop.user_id == user_id).update({
            "is_active": False,
            "is_suspended": True,
            "suspension_reason": "User account deleted",
            "updated_at": datetime.utcnow()
        })
        
        # Cancel pending orders
        db.query(Order).filter(
            and_(
                Order.user_id == user_id,
                Order.status.in_(["pending", "confirmed", "processing"])
            )
        ).update({
            "status": "cancelled",
            "cancelled_at": datetime.utcnow(),
            "cancellation_reason": "User account deleted",
            "updated_at": datetime.utcnow()
        })
        
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="user_delete",
            user_id=user_id,
            data={
                "deleted_at": datetime.utcnow().isoformat(),
                "reason": reason
            }
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting user account: {str(e)}")
        return False

def export_user_data(db: Session, user_id: str) -> Dict[str, Any]:
    """Export all user data for GDPR compliance."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {}
        
        # Get all user data
        shops = db.query(Shop).filter(Shop.user_id == user_id).all()
        addresses = db.query(Address).filter(Address.user_id == user_id).all()
        orders = db.query(Order).filter(Order.user_id == user_id).all()
        reviews = db.query(Review).filter(Review.user_id == user_id).all()
        wishlists = db.query(Wishlist).filter(Wishlist.user_id == user_id).all()
        
        return {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone_number": user.phone_number,
                "type": user.type,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "is_verified": user.is_verified,
                "is_active": user.is_active
            },
            "shops": [
                {
                    "id": shop.id,
                    "name": shop.name,
                    "description": shop.description,
                    "created_at": shop.created_at.isoformat() if shop.created_at else None
                }
                for shop in shops
            ],
            "addresses": [
                {
                    "id": addr.id,
                    "label": addr.label,
                    "full_name": addr.full_name,
                    "phone": addr.phone,
                    "street": addr.street,
                    "city": addr.city,
                    "state": addr.state,
                    "postal_code": addr.postal_code,
                    "country": addr.country,
                    "is_default": addr.is_default,
                    "created_at": addr.created_at.isoformat() if addr.created_at else None
                }
                for addr in addresses
            ],
            "orders": [
                {
                    "id": order.id,
                    "order_number": order.order_number,
                    "total_amount": order.total_amount,
                    "status": order.status,
                    "created_at": order.created_at.isoformat() if order.created_at else None
                }
                for order in orders
            ],
            "reviews": [
                {
                    "id": review.id,
                    "product_id": review.product_id,
                    "rating": review.rating,
                    "comment": review.comment,
                    "created_at": review.created_at.isoformat() if review.created_at else None
                }
                for review in reviews
            ],
            "wishlists": [
                {
                    "id": wishlist.id,
                    "name": wishlist.name,
                    "item_count": len(wishlist.items) if wishlist.items else 0,
                    "created_at": wishlist.created_at.isoformat() if wishlist.created_at else None
                }
                for wishlist in wishlists
            ],
            "exported_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error exporting user data: {str(e)}")
        return {}

# Address management
def create_user_address(db: Session, user_id: str, address_data: AddressCreate) -> Optional[Address]:
    """Create a new address for user."""
    try:
        # If this is set as default, update other addresses
        if address_data.is_default:
            db.query(Address).filter(
                and_(
                    Address.user_id == user_id,
                    Address.is_default == True,
                    Address.is_deleted == False
                )
            ).update({"is_default": False})
        
        address = Address(
            user_id=user_id,
            **address_data.dict()
        )
        
        db.add(address)
        db.commit()
        db.refresh(address)
        
        return address
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating user address: {str(e)}")
        return None

def get_user_addresses(db: Session, user_id: str) -> List[Address]:
    """Get all addresses for user."""
    try:
        addresses = db.query(Address).filter(
            and_(
                Address.user_id == user_id,
                Address.is_deleted == False
            )
        ).order_by(desc(Address.is_default), asc(Address.created_at)).all()
        
        return addresses
    except Exception as e:
        logger.error(f"Error getting user addresses: {str(e)}")
        return []

def get_user_address_by_id(db: Session, user_id: str, address_id: str) -> Optional[Address]:
    """Get a specific address for user."""
    try:
        address = db.query(Address).filter(
            and_(
                Address.id == address_id,
                Address.user_id == user_id,
                Address.is_deleted == False
            )
        ).first()
        
        return address
    except Exception as e:
        logger.error(f"Error getting user address by ID: {str(e)}")
        return None

def update_user_address(db: Session, user_id: str, address_id: str, update_data: AddressUpdate) -> Optional[Address]:
    """Update user address."""
    try:
        address = get_user_address_by_id(db, user_id, address_id)
        if not address:
            return None
        
        # If setting as default, update other addresses
        if update_data.is_default == True:
            db.query(Address).filter(
                and_(
                    Address.user_id == user_id,
                    Address.id != address_id,
                    Address.is_default == True,
                    Address.is_deleted == False
                )
            ).update({"is_default": False})
        
        # Update fields
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(address, field) and value is not None:
                setattr(address, field, value)
        
        address.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(address)
        
        return address
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user address: {str(e)}")
        return None

def delete_user_address(db: Session, user_id: str, address_id: str) -> bool:
    """Delete user address (soft delete)."""
    try:
        address = get_user_address_by_id(db, user_id, address_id)
        if not address:
            return False
        
        # If this was the default address, set another as default
        if address.is_default:
            # Find another address to set as default
            another_address = db.query(Address).filter(
                and_(
                    Address.user_id == user_id,
                    Address.id != address_id,
                    Address.is_deleted == False
                )
            ).first()
            
            if another_address:
                another_address.is_default = True
                another_address.updated_at = datetime.utcnow()
        
        # Soft delete the address
        address.is_deleted = True
        address.deleted_at = datetime.utcnow()
        address.updated_at = datetime.utcnow()
        
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting user address: {str(e)}")
        return False

def get_user_default_address(db: Session, user_id: str) -> Optional[Address]:
    """Get user's default address."""
    try:
        address = db.query(Address).filter(
            and_(
                Address.user_id == user_id,
                Address.is_default == True,
                Address.is_deleted == False
            )
        ).first()
        
        return address
    except Exception as e:
        logger.error(f"Error getting user default address: {str(e)}")
        return None

# User statistics
def get_user_statistics(db: Session, user_id: str) -> Dict[str, Any]:
    """Get user statistics."""
    try:
        # Get total orders
        total_orders = db.query(Order).filter(Order.user_id == user_id).count()
        
        # Get completed orders
        completed_orders = db.query(Order).filter(
            and_(
                Order.user_id == user_id,
                Order.status == OrderStatus.DELIVERED
            )
        ).count()
        
        # Get total spent
        total_spent_result = db.query(func.sum(Order.total_amount)).filter(
            and_(
                Order.user_id == user_id,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.SHIPPED])
            )
        ).first()
        total_spent = total_spent_result[0] or 0
        
        # Get average order value
        avg_order_value = total_spent / completed_orders if completed_orders > 0 else 0
        
        # Get total reviews
        total_reviews = db.query(Review).filter(Review.user_id == user_id).count()
        
        # Get recent activity
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_orders = db.query(Order).filter(
            and_(
                Order.user_id == user_id,
                Order.created_at >= thirty_days_ago
            )
        ).count()
        
        recent_reviews = db.query(Review).filter(
            and_(
                Review.user_id == user_id,
                Review.created_at >= thirty_days_ago
            )
        ).count()
        
        return {
            "total_orders": total_orders,
            "completed_orders": completed_orders,
            "total_spent": float(total_spent),
            "average_order_value": float(avg_order_value),
            "total_reviews": total_reviews,
            "recent_orders_30d": recent_orders,
            "recent_reviews_30d": recent_reviews,
            "order_completion_rate": (completed_orders / total_orders * 100) if total_orders > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error getting user statistics: {str(e)}")
        return {}

# Admin functions
def get_platform_user_stats(db: Session) -> UserStats:
    """Get platform user statistics (admin only)."""
    try:
        total_users = db.query(User).count()
        merchants_count = db.query(User).filter(User.type == UserType.MERCHANT.value).count()
        customers_count = db.query(User).filter(User.type == UserType.CUSTOMER.value).count()
        admins_count = db.query(User).filter(User.type == UserType.ADMIN.value).count()
        
        # Active users in last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        active_users_30d = db.query(User).filter(
            and_(
                User.is_active == True,
                User.last_login_at >= thirty_days_ago
            )
        ).count()
        
        # New users in last 30 days
        new_users_30d = db.query(User).filter(
            User.created_at >= thirty_days_ago
        ).count()
        
        # User growth rate (compared to previous 30 days)
        sixty_days_ago = datetime.utcnow() - timedelta(days=60)
        users_previous_30d = db.query(User).filter(
            User.created_at.between(sixty_days_ago, thirty_days_ago)
        ).count()
        
        user_growth_rate = 0
        if users_previous_30d > 0:
            user_growth_rate = ((new_users_30d - users_previous_30d) / users_previous_30d) * 100
        
        return UserStats(
            total_users=total_users,
            merchants_count=merchants_count,
            customers_count=customers_count,
            admins_count=admins_count,
            active_users_30d=active_users_30d,
            new_users_30d=new_users_30d,
            user_growth_rate=user_growth_rate,
            avg_session_duration=None  # Would need session tracking
        )
    except Exception as e:
        logger.error(f"Error getting platform user stats: {str(e)}")
        return UserStats(
            total_users=0,
            merchants_count=0,
            customers_count=0,
            admins_count=0,
            active_users_30d=0,
            new_users_30d=0,
            user_growth_rate=0,
            avg_session_duration=None
        )

def search_users(db: Session, search_term: str, limit: int = 20) -> List[User]:
    """Search users by name, email, or phone number."""
    try:
        search_pattern = f"%{search_term}%"
        
        users = db.query(User).filter(
            or_(
                User.name.ilike(search_pattern),
                User.email.ilike(search_pattern),
                User.phone_number.ilike(search_pattern)
            )
        ).filter(User.is_active == True).limit(limit).all()
        
        return users
    except Exception as e:
        logger.error(f"Error searching users: {str(e)}")
        return []

def bulk_update_users(db: Session, user_ids: List[str], update_data: Dict[str, Any]) -> int:
    """Bulk update users (admin only)."""
    try:
        result = db.query(User).filter(User.id.in_(user_ids)).update(
            {**update_data, "updated_at": datetime.utcnow()},
            synchronize_session=False
        )
        
        db.commit()
        
        # Create blockchain transaction for each user
        for user_id in user_ids:
            create_blockchain_transaction(
                transaction_type="user_bulk_update",
                user_id="system",  # System user
                data={
                    "user_id": user_id,
                    "updates": update_data,
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
        
        return result
    except Exception as e:
        db.rollback()
        logger.error(f"Error bulk updating users: {str(e)}")
        return 0