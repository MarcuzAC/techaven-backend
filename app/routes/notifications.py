from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta
import uuid
from app.database import supabase
from app.dependencies import get_current_user, get_current_admin
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType
import json

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)

# ========== CORE ENDPOINTS ==========

@router.get("/")
async def get_user_notifications(
    current_user: dict = Depends(get_current_user),
    read: Optional[bool] = Query(None, description="Filter by read status"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get notifications for the current user with filtering and pagination.
    """
    try:
        # Build query
        query = supabase.table("notifications").select(
            "id, user_id, title, message, notification_type, priority, "
            "data, action_url, action_text, image_url, icon, tags, "
            "metadata, read, read_at, sent_at, delivered_at, failed_at, "
            "created_at, updated_at, blockchain_tx_id",
            count="exact"
        ).eq("user_id", current_user["id"])
        
        # Apply filters
        if read is not None:
            query = query.eq("read", read)
        if notification_type:
            query = query.eq("notification_type", notification_type)
        if priority:
            query = query.eq("priority", priority)
        
        # Apply pagination and sorting
        query = query.order("created_at", desc=True)
        query = query.range(offset, offset + limit - 1)
        
        # Execute query
        result = query.execute()
        
        # Transform response
        notifications_data = []
        for notification in result.data:
            notifications_data.append({
                "id": notification["id"],
                "user_id": notification["user_id"],
                "title": notification["title"],
                "message": notification["message"],
                "notification_type": notification["notification_type"],
                "priority": notification["priority"],
                "data": notification.get("data") or {},
                "action_url": notification.get("action_url"),
                "action_text": notification.get("action_text"),
                "image_url": notification.get("image_url"),
                "icon": notification.get("icon"),
                "tags": notification.get("tags") or [],
                "metadata": notification.get("metadata") or {},
                "read": notification["read"],
                "read_at": notification.get("read_at"),
                "sent_at": notification.get("sent_at"),
                "delivered_at": notification.get("delivered_at"),
                "failed_at": notification.get("failed_at"),
                "created_at": notification["created_at"],
                "updated_at": notification.get("updated_at"),
                "blockchain_tx_id": notification.get("blockchain_tx_id")
            })
        
        return {
            "data": notifications_data,
            "pagination": {
                "total": result.count,
                "skip": offset,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch notifications"
        )

@router.get("/unread/count")
async def get_unread_notification_count(
    current_user: dict = Depends(get_current_user)
):
    """
    Get count of unread notifications for the current user.
    """
    try:
        result = supabase.table("notifications").select(
            "id", count="exact"
        ).eq("user_id", current_user["id"]).eq("read", False).execute()
        
        return {
            "user_id": current_user["id"],
            "unread_count": result.count or 0,
            "has_unread": result.count > 0 if result.count else False
        }
        
    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unread count"
        )

@router.get("/{notification_id}")
async def get_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific notification by ID.
    """
    try:
        result = supabase.table("notifications").select("*").eq("id", notification_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        notification = result.data[0]
        
        # Check if user owns this notification
        if notification["user_id"] != current_user["id"] and current_user.get("type") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this notification"
            )
        
        return {
            "id": notification["id"],
            "user_id": notification["user_id"],
            "title": notification["title"],
            "message": notification["message"],
            "notification_type": notification["notification_type"],
            "priority": notification["priority"],
            "data": notification.get("data") or {},
            "action_url": notification.get("action_url"),
            "action_text": notification.get("action_text"),
            "image_url": notification.get("image_url"),
            "icon": notification.get("icon"),
            "tags": notification.get("tags") or [],
            "metadata": notification.get("metadata") or {},
            "read": notification["read"],
            "read_at": notification.get("read_at"),
            "sent_at": notification.get("sent_at"),
            "delivered_at": notification.get("delivered_at"),
            "failed_at": notification.get("failed_at"),
            "created_at": notification["created_at"],
            "updated_at": notification.get("updated_at"),
            "blockchain_tx_id": notification.get("blockchain_tx_id")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch notification"
        )

@router.post("/")
async def create_user_notification(
    notification_data: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new notification (admin/merchant only).
    """
    try:
        # Check permissions
        if current_user.get("type") not in ["admin", "merchant"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins and merchants can create notifications"
            )
        
        # Validate required fields
        required_fields = ["title", "message", "notification_type", "priority"]
        for field in required_fields:
            if field not in notification_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required field: {field}"
                )
        
        # Validate user exists if specified
        if notification_data.get("user_id"):
            user_result = supabase.table("users").select("id").eq("id", notification_data["user_id"]).execute()
            if not user_result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target user not found"
                )
        
        # Create notification payload
        notification_id = str(uuid.uuid4())
        notification_payload = {
            "id": notification_id,
            "user_id": notification_data.get("user_id"),
            "title": notification_data["title"],
            "message": notification_data["message"],
            "notification_type": notification_data["notification_type"],
            "priority": notification_data["priority"],
            "data": notification_data.get("data") or {},
            "action_url": notification_data.get("action_url"),
            "action_text": notification_data.get("action_text"),
            "image_url": notification_data.get("image_url"),
            "icon": notification_data.get("icon"),
            "tags": notification_data.get("tags") or [],
            "metadata": notification_data.get("metadata") or {},
            "read": False,
            "created_at": datetime.utcnow().isoformat(),
            "sent_at": datetime.utcnow().isoformat()  # Mark as sent immediately
        }
        
        # Create notification on blockchain
        notification_transaction = None
        try:
            notification_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.NOTIFICATION_CREATE,
                user_id=current_user["id"],
                data={
                    "action": "notification_creation",
                    "notification_id": notification_id,
                    "title": notification_data["title"],
                    "notification_type": notification_data["notification_type"],
                    "priority": notification_data["priority"],
                    "target_user_id": notification_data.get("user_id"),
                    "sender_type": current_user.get("type")
                },
                metadata={
                    "source": "notifications_route",
                    "has_action": bool(notification_data.get("action_url")),
                    "has_image": bool(notification_data.get("image_url"))
                }
            )
            
            blockchain_service.add_transaction(notification_transaction)
            
            # Add blockchain transaction ID to notification
            notification_payload["blockchain_tx_id"] = notification_transaction.transaction_id
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Notification creation transaction failed: {e}")
        
        # Create notification in database
        result = supabase.table("notifications").insert(notification_payload).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create notification"
            )
        
        created_notification = result.data[0]
        
        return {
            "message": "Notification created successfully",
            "notification": {
                "id": created_notification["id"],
                "user_id": created_notification["user_id"],
                "title": created_notification["title"],
                "message": created_notification["message"],
                "notification_type": created_notification["notification_type"],
                "priority": created_notification["priority"],
                "data": created_notification.get("data") or {},
                "action_url": created_notification.get("action_url"),
                "action_text": created_notification.get("action_text"),
                "image_url": created_notification.get("image_url"),
                "icon": created_notification.get("icon"),
                "tags": created_notification.get("tags") or [],
                "metadata": created_notification.get("metadata") or {},
                "read": created_notification["read"],
                "read_at": created_notification.get("read_at"),
                "sent_at": created_notification.get("sent_at"),
                "delivered_at": created_notification.get("delivered_at"),
                "failed_at": created_notification.get("failed_at"),
                "created_at": created_notification["created_at"],
                "updated_at": created_notification.get("updated_at"),
                "blockchain_tx_id": created_notification.get("blockchain_tx_id")
            },
            "blockchain_tx_id": notification_transaction.transaction_id if notification_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create notification"
        )

@router.put("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Mark a notification as read.
    """
    try:
        # Get notification
        result = supabase.table("notifications").select("*").eq("id", notification_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        notification = result.data[0]
        
        # Check if user owns this notification
        if notification["user_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this notification"
            )
        
        # Record read action on blockchain
        read_transaction = None
        try:
            read_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.NOTIFICATION_READ,
                user_id=current_user["id"],
                data={
                    "action": "notification_read",
                    "notification_id": notification_id,
                    "notification_title": notification["title"],
                    "notification_type": notification["notification_type"],
                    "was_read_before": notification.get("read", False),
                    "user_action": True
                },
                metadata={
                    "source": "notifications_route",
                    "delivery_time": (
                        datetime.utcnow() - datetime.fromisoformat(notification["created_at"].replace("Z", "+00:00"))
                    ).total_seconds() if notification.get("created_at") else None
                }
            )
            
            blockchain_service.add_transaction(read_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Notification read transaction failed: {e}")
        
        # Update notification
        update_result = supabase.table("notifications").update({
            "read": True,
            "read_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", notification_id).execute()
        
        if not update_result.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to mark notification as read"
            )
        
        updated_notification = update_result.data[0]
        
        return {
            "message": "Notification marked as read",
            "notification_id": notification_id,
            "user_id": current_user["id"],
            "read_at": updated_notification["read_at"],
            "blockchain_tx_id": read_transaction.transaction_id if read_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notification as read"
        )

@router.put("/read/all")
async def mark_all_as_read(
    current_user: dict = Depends(get_current_user)
):
    """
    Mark all notifications as read for the current user.
    """
    try:
        # Get unread notifications count
        result = supabase.table("notifications").select(
            "id", count="exact"
        ).eq("user_id", current_user["id"]).eq("read", False).execute()
        
        unread_count = result.count or 0
        
        if unread_count == 0:
            return {
                "message": "No unread notifications found",
                "user_id": current_user["id"],
                "marked_count": 0
            }
        
        # Mark all as read
        update_result = supabase.table("notifications").update({
            "read": True,
            "read_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }).eq("user_id", current_user["id"]).eq("read", False).execute()
        
        # Record bulk read action on blockchain
        bulk_read_transaction = None
        try:
            bulk_read_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.NOTIFICATION_READ,
                user_id=current_user["id"],
                data={
                    "action": "bulk_notification_read",
                    "notification_count": unread_count,
                    "user_action": True
                },
                metadata={
                    "source": "notifications_route",
                    "bulk_operation": True
                }
            )
            
            blockchain_service.add_transaction(bulk_read_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Bulk read transaction failed: {e}")
        
        return {
            "message": f"Marked {unread_count} notifications as read",
            "user_id": current_user["id"],
            "marked_count": unread_count,
            "timestamp": datetime.utcnow().isoformat(),
            "blockchain_tx_id": bulk_read_transaction.transaction_id if bulk_read_transaction else None
        }
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notifications as read"
        )

@router.delete("/{notification_id}")
async def delete_user_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a notification.
    """
    try:
        # Get notification
        result = supabase.table("notifications").select("*").eq("id", notification_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        notification = result.data[0]
        
        # Check if user owns this notification
        if notification["user_id"] != current_user["id"] and current_user.get("type") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this notification"
            )
        
        # Record deletion on blockchain
        delete_transaction = None
        try:
            delete_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.NOTIFICATION_DELETE,
                user_id=current_user["id"],
                data={
                    "action": "notification_deletion",
                    "notification_id": notification_id,
                    "notification_title": notification["title"],
                    "notification_type": notification["notification_type"],
                    "was_read": notification.get("read", False),
                    "user_action": current_user["id"] == notification["user_id"]
                },
                metadata={
                    "source": "notifications_route",
                    "admin_action": current_user.get("type") == "admin",
                    "age_seconds": (
                        datetime.utcnow() - datetime.fromisoformat(notification["created_at"].replace("Z", "+00:00"))
                    ).total_seconds() if notification.get("created_at") else None
                }
            )
            
            blockchain_service.add_transaction(delete_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Notification deletion transaction failed: {e}")
        
        # Delete notification
        supabase.table("notifications").delete().eq("id", notification_id).execute()
        
        return {
            "message": "Notification deleted successfully",
            "notification_id": notification_id,
            "deleted_by": current_user["id"],
            "timestamp": datetime.utcnow().isoformat(),
            "blockchain_tx_id": delete_transaction.transaction_id if delete_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete notification"
        )

# ========== BULK OPERATIONS ==========

@router.post("/bulk/read")
async def bulk_mark_as_read(
    notification_ids: List[str],
    current_user: dict = Depends(get_current_user)
):
    """
    Mark multiple notifications as read.
    """
    try:
        if not notification_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Notification IDs list cannot be empty"
            )
        
        # Get notifications that belong to user
        result = supabase.table("notifications").select(
            "id"
        ).eq("user_id", current_user["id"]).in_("id", notification_ids).execute()
        
        valid_ids = [notification["id"] for notification in result.data]
        
        if not valid_ids:
            return {
                "message": "No valid notifications found to mark as read",
                "user_id": current_user["id"],
                "marked_count": 0
            }
        
        # Mark as read
        update_result = supabase.table("notifications").update({
            "read": True,
            "read_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }).in_("id", valid_ids).execute()
        
        # Record bulk read action on blockchain
        bulk_read_transaction = None
        try:
            bulk_read_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.NOTIFICATION_READ,
                user_id=current_user["id"],
                data={
                    "action": "bulk_notification_read",
                    "notification_ids": valid_ids,
                    "notification_count": len(valid_ids),
                    "user_action": True
                },
                metadata={
                    "source": "notifications_route",
                    "bulk_operation": True,
                    "specific_ids": True
                }
            )
            
            blockchain_service.add_transaction(bulk_read_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Bulk read transaction failed: {e}")
        
        return {
            "message": f"Marked {len(valid_ids)} notifications as read",
            "user_id": current_user["id"],
            "marked_count": len(valid_ids),
            "marked_ids": valid_ids,
            "timestamp": datetime.utcnow().isoformat(),
            "blockchain_tx_id": bulk_read_transaction.transaction_id if bulk_read_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk mark as read: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notifications as read"
        )

@router.post("/bulk/delete")
async def bulk_delete_notifications(
    notification_ids: List[str],
    current_user: dict = Depends(get_current_user)
):
    """
    Delete multiple notifications.
    """
    try:
        if not notification_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Notification IDs list cannot be empty"
            )
        
        # Get notifications that belong to user
        result = supabase.table("notifications").select(
            "id"
        ).eq("user_id", current_user["id"]).in_("id", notification_ids).execute()
        
        valid_ids = [notification["id"] for notification in result.data]
        
        if not valid_ids:
            return {
                "message": "No valid notifications found to delete",
                "user_id": current_user["id"],
                "deleted_count": 0
            }
        
        # Record bulk deletion on blockchain
        bulk_delete_transaction = None
        try:
            bulk_delete_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.NOTIFICATION_DELETE,
                user_id=current_user["id"],
                data={
                    "action": "bulk_notification_delete",
                    "notification_ids": valid_ids,
                    "notification_count": len(valid_ids),
                    "user_action": True
                },
                metadata={
                    "source": "notifications_route",
                    "bulk_operation": True,
                    "specific_ids": True
                }
            )
            
            blockchain_service.add_transaction(bulk_delete_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Bulk delete transaction failed: {e}")
        
        # Delete notifications
        supabase.table("notifications").delete().in_("id", valid_ids).execute()
        
        return {
            "message": f"Deleted {len(valid_ids)} notifications",
            "user_id": current_user["id"],
            "deleted_count": len(valid_ids),
            "deleted_ids": valid_ids,
            "timestamp": datetime.utcnow().isoformat(),
            "blockchain_tx_id": bulk_delete_transaction.transaction_id if bulk_delete_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk delete: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete notifications"
        )

# ========== ADMIN ENDPOINTS ==========

@router.get("/admin/all")
async def get_all_notifications_admin(
    current_user: dict = Depends(get_current_admin),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    read: Optional[bool] = Query(None, description="Filter by read status"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """
    Get all notifications (admin only).
    """
    try:
        # Build query
        query = supabase.table("notifications").select(
            "id, user_id, title, message, notification_type, priority, "
            "data, action_url, action_text, image_url, icon, tags, "
            "metadata, read, read_at, sent_at, delivered_at, failed_at, "
            "created_at, updated_at, blockchain_tx_id",
            count="exact"
        )
        
        # Apply filters
        if user_id:
            query = query.eq("user_id", user_id)
        if read is not None:
            query = query.eq("read", read)
        if notification_type:
            query = query.eq("notification_type", notification_type)
        if priority:
            query = query.eq("priority", priority)
        
        # Apply pagination and sorting
        query = query.order("created_at", desc=True)
        query = query.range(offset, offset + limit - 1)
        
        # Execute query
        result = query.execute()
        
        # Get user info for each notification
        notifications_data = []
        for notification in result.data:
            # Get user info
            user_info = None
            if notification["user_id"]:
                user_result = supabase.table("users").select(
                    "id, name, email, type, profile_picture"
                ).eq("id", notification["user_id"]).execute()
                
                if user_result.data:
                    user = user_result.data[0]
                    user_info = {
                        "id": user["id"],
                        "name": user["name"],
                        "email": user["email"],
                        "type": user["type"],
                        "profile_picture": user.get("profile_picture")
                    }
            
            notifications_data.append({
                "id": notification["id"],
                "user_id": notification["user_id"],
                "title": notification["title"],
                "message": notification["message"],
                "notification_type": notification["notification_type"],
                "priority": notification["priority"],
                "data": notification.get("data") or {},
                "action_url": notification.get("action_url"),
                "action_text": notification.get("action_text"),
                "image_url": notification.get("image_url"),
                "icon": notification.get("icon"),
                "tags": notification.get("tags") or [],
                "metadata": notification.get("metadata") or {},
                "read": notification["read"],
                "read_at": notification.get("read_at"),
                "sent_at": notification.get("sent_at"),
                "delivered_at": notification.get("delivered_at"),
                "failed_at": notification.get("failed_at"),
                "created_at": notification["created_at"],
                "updated_at": notification.get("updated_at"),
                "blockchain_tx_id": notification.get("blockchain_tx_id"),
                "user": user_info
            })
        
        return {
            "data": notifications_data,
            "pagination": {
                "total": result.count,
                "skip": offset,
                "limit": limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching all notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch notifications"
        )

@router.post("/admin/broadcast")
async def broadcast_notification(
    broadcast_data: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_admin)
):
    """
    Send broadcast notification to all users (admin only).
    """
    try:
        # Validate required fields
        required_fields = ["title", "message", "notification_type", "priority"]
        for field in required_fields:
            if field not in broadcast_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required field: {field}"
                )
        
        # Get all active users
        users_result = supabase.table("users").select(
            "id, name, email"
        ).eq("is_active", True).execute()
        
        users = users_result.data
        created_count = 0
        errors = []
        
        # Record broadcast action on blockchain
        broadcast_transaction = None
        try:
            broadcast_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.NOTIFICATION_BROADCAST,
                user_id=current_user["id"],
                data={
                    "action": "notification_broadcast",
                    "title": broadcast_data["title"],
                    "notification_type": broadcast_data["notification_type"],
                    "priority": broadcast_data["priority"],
                    "target_user_count": len(users),
                    "admin_id": current_user["id"]
                },
                metadata={
                    "source": "notifications_route",
                    "broadcast_operation": True,
                    "has_action": bool(broadcast_data.get("action_url"))
                }
            )
            
            blockchain_service.add_transaction(broadcast_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Broadcast transaction failed: {e}")
        
        # Create notifications for each user
        for user in users:
            try:
                notification_id = str(uuid.uuid4())
                notification_payload = {
                    "id": notification_id,
                    "user_id": user["id"],
                    "title": broadcast_data["title"],
                    "message": broadcast_data["message"],
                    "notification_type": broadcast_data["notification_type"],
                    "priority": broadcast_data["priority"],
                    "data": broadcast_data.get("data") or {},
                    "action_url": broadcast_data.get("action_url"),
                    "action_text": broadcast_data.get("action_text"),
                    "image_url": broadcast_data.get("image_url"),
                    "icon": broadcast_data.get("icon"),
                    "tags": broadcast_data.get("tags") or [],
                    "metadata": broadcast_data.get("metadata") or {},
                    "read": False,
                    "created_at": datetime.utcnow().isoformat(),
                    "sent_at": datetime.utcnow().isoformat(),
                    "blockchain_tx_id": broadcast_transaction.transaction_id if broadcast_transaction else None
                }
                
                supabase.table("notifications").insert(notification_payload).execute()
                created_count += 1
                
            except Exception as e:
                errors.append({
                    "user_id": user["id"],
                    "error": str(e)
                })
                logger.error(f"Error creating notification for user {user['id']}: {str(e)}")
        
        return {
            "message": f"Broadcast notification sent to {created_count} users",
            "admin_id": current_user["id"],
            "total_users": len(users),
            "successful_sends": created_count,
            "failed_sends": len(errors),
            "errors": errors if errors else None,
            "timestamp": datetime.utcnow().isoformat(),
            "blockchain_tx_id": broadcast_transaction.transaction_id if broadcast_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending broadcast notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send broadcast notification"
        )

@router.get("/admin/stats")
async def get_notification_stats_admin(
    current_user: dict = Depends(get_current_admin),
    days: int = Query(30, ge=1, le=365)
):
    """
    Get notification statistics (admin only).
    """
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Get total notifications in period
        total_result = supabase.table("notifications").select(
            "id", count="exact"
        ).gte("created_at", cutoff_date).execute()
        
        total_notifications = total_result.count or 0
        
        # Get read vs unread
        read_result = supabase.table("notifications").select(
            "id", count="exact"
        ).gte("created_at", cutoff_date).eq("read", True).execute()
        
        read_notifications = read_result.count or 0
        unread_notifications = total_notifications - read_notifications
        
        # Get by type
        type_result = supabase.table("notifications").select(
            "notification_type"
        ).gte("created_at", cutoff_date).execute()
        
        by_type = {}
        for notification in type_result.data:
            ntype = notification["notification_type"]
            by_type[ntype] = by_type.get(ntype, 0) + 1
        
        # Get by priority
        priority_result = supabase.table("notifications").select(
            "priority"
        ).gte("created_at", cutoff_date).execute()
        
        by_priority = {}
        for notification in priority_result.data:
            priority = notification["priority"]
            by_priority[priority] = by_priority.get(priority, 0) + 1
        
        # Get top users
        # Note: Supabase doesn't have easy GROUP BY with COUNT like SQLAlchemy
        # We'll do this differently - get all notifications and count manually
        all_notifications = supabase.table("notifications").select(
            "user_id"
        ).gte("created_at", cutoff_date).execute()
        
        user_counts = {}
        for notification in all_notifications.data:
            user_id = notification["user_id"]
            user_counts[user_id] = user_counts.get(user_id, 0) + 1
        
        # Sort users by notification count
        sorted_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        top_users_list = []
        for user_id, count in sorted_users:
            user_result = supabase.table("users").select(
                "id, name, email, type"
            ).eq("id", user_id).execute()
            
            if user_result.data:
                user = user_result.data[0]
                top_users_list.append({
                    "user_id": user["id"],
                    "name": user["name"],
                    "email": user["email"],
                    "type": user["type"],
                    "notification_count": count
                })
        
        return {
            "time_period_days": days,
            "cutoff_date": cutoff_date,
            "total_notifications": total_notifications,
            "read_notifications": read_notifications,
            "unread_notifications": unread_notifications,
            "read_rate": (read_notifications / total_notifications * 100) if total_notifications > 0 else 0,
            "by_type": by_type,
            "by_priority": by_priority,
            "top_users": top_users_list,
            "average_per_user": total_notifications / max(len(user_counts), 1) if user_counts else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting notification stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get notification stats"
        )

# ========== USER PREFERENCES ==========

@router.get("/preferences")
async def get_notification_preferences(
    current_user: dict = Depends(get_current_user)
):
    """
    Get notification preferences for the current user.
    """
    try:
        # Check if preferences exist
        result = supabase.table("notification_preferences").select("*").eq(
            "user_id", current_user["id"]
        ).execute()
        
        if result.data:
            # Return existing preferences
            preferences = result.data[0]
            return {
                "user_id": preferences["user_id"],
                "email_notifications": preferences.get("email_notifications", True),
                "push_notifications": preferences.get("push_notifications", True),
                "sms_notifications": preferences.get("sms_notifications", False),
                "marketing_emails": preferences.get("marketing_emails", True),
                "order_updates": preferences.get("order_updates", True),
                "promotional_offers": preferences.get("promotional_offers", True),
                "security_alerts": preferences.get("security_alerts", True),
                "weekly_digest": preferences.get("weekly_digest", True),
                "quiet_hours_start": preferences.get("quiet_hours_start", "22:00"),
                "quiet_hours_end": preferences.get("quiet_hours_end", "07:00"),
                "preferred_language": preferences.get("preferred_language", "en"),
                "created_at": preferences.get("created_at"),
                "updated_at": preferences.get("updated_at")
            }
        else:
            # Return default preferences
            return {
                "user_id": current_user["id"],
                "email_notifications": True,
                "push_notifications": True,
                "sms_notifications": False,
                "marketing_emails": True,
                "order_updates": True,
                "promotional_offers": True,
                "security_alerts": True,
                "weekly_digest": True,
                "quiet_hours_start": "22:00",
                "quiet_hours_end": "07:00",
                "preferred_language": "en",
                "is_default": True
            }
        
    except Exception as e:
        logger.error(f"Error getting notification preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get notification preferences"
        )

@router.put("/preferences")
async def update_notification_preferences(
    preferences: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Update notification preferences for the current user.
    """
    try:
        allowed_keys = [
            "email_notifications", "push_notifications", "sms_notifications",
            "marketing_emails", "order_updates", "promotional_offers",
            "security_alerts", "weekly_digest", "quiet_hours_start",
            "quiet_hours_end", "preferred_language"
        ]
        
        # Filter only allowed keys
        filtered_preferences = {k: v for k, v in preferences.items() if k in allowed_keys}
        
        if not filtered_preferences:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid preference fields provided"
            )
        
        # Check if preferences exist
        existing_result = supabase.table("notification_preferences").select("*").eq(
            "user_id", current_user["id"]
        ).execute()
        
        filtered_preferences["updated_at"] = datetime.utcnow().isoformat()
        
        if existing_result.data:
            # Update existing preferences
            result = supabase.table("notification_preferences").update(
                filtered_preferences
            ).eq("user_id", current_user["id"]).execute()
        else:
            # Create new preferences
            filtered_preferences["user_id"] = current_user["id"]
            filtered_preferences["created_at"] = datetime.utcnow().isoformat()
            result = supabase.table("notification_preferences").insert(
                filtered_preferences
            ).execute()
        
        # Record preference update on blockchain
        preference_transaction = None
        try:
            preference_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.USER_UPDATE,
                user_id=current_user["id"],
                data={
                    "action": "notification_preferences_update",
                    "updated_fields": list(filtered_preferences.keys()),
                    "user_id": current_user["id"]
                },
                metadata={
                    "source": "notifications_route",
                    "preference_update": True
                }
            )
            
            blockchain_service.add_transaction(preference_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Preference update transaction failed: {e}")
        
        return {
            "message": "Notification preferences updated successfully",
            "user_id": current_user["id"],
            "updated_fields": list(filtered_preferences.keys()),
            "timestamp": datetime.utcnow().isoformat(),
            "blockchain_tx_id": preference_transaction.transaction_id if preference_transaction else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating notification preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update notification preferences"
        )

# ========== HELPER FUNCTIONS ==========

async def create_system_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "system",
    priority: str = "medium",
    data: Optional[Dict[str, Any]] = None,
    action_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Helper function to create system notifications.
    """
    try:
        notification_id = str(uuid.uuid4())
        notification_payload = {
            "id": notification_id,
            "user_id": user_id,
            "title": title,
            "message": message,
            "notification_type": notification_type,
            "priority": priority,
            "data": data or {},
            "action_url": action_url,
            "read": False,
            "created_at": datetime.utcnow().isoformat(),
            "sent_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("notifications").insert(notification_payload).execute()
        
        if result.data:
            return result.data[0]
        return None
        
    except Exception as e:
        logger.error(f"Error creating system notification: {str(e)}")
        return None

async def notify_user_about_order(
    user_id: str,
    order_id: str,
    order_status: str,
    order_number: str,
    amount: float
) -> Dict[str, Any]:
    """
    Create notification for order updates.
    """
    title = f"Order #{order_number} Update"
    
    status_messages = {
        "pending": "Your order has been received and is being processed.",
        "confirmed": "Your order has been confirmed.",
        "processing": "Your order is being prepared for shipment.",
        "shipped": "Your order has been shipped.",
        "delivered": "Your order has been delivered.",
        "cancelled": "Your order has been cancelled.",
        "refunded": "Your order has been refunded."
    }
    
    message = status_messages.get(
        order_status,
        f"Your order status has been updated to {order_status}."
    )
    
    return await create_system_notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type="order",
        priority="medium",
        data={
            "order_id": order_id,
            "order_number": order_number,
            "order_status": order_status,
            "amount": amount
        }
    )

async def notify_user_about_payment(
    user_id: str,
    payment_id: str,
    payment_status: str,
    amount: float,
    order_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create notification for payment updates.
    """
    title = "Payment Update"
    
    status_messages = {
        "pending": "Your payment is pending confirmation.",
        "processing": "Your payment is being processed.",
        "completed": "Your payment has been completed successfully.",
        "failed": "Your payment has failed. Please try again.",
        "refunded": "Your payment has been refunded."
    }
    
    message = status_messages.get(
        payment_status,
        f"Your payment status has been updated to {payment_status}."
    )
    
    priority = "high" if payment_status in ["failed", "refunded"] else "medium"
    
    return await create_system_notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type="payment",
        priority=priority,
        data={
            "payment_id": payment_id,
            "payment_status": payment_status,
            "amount": amount,
            "order_id": order_id
        }
    )

async def cleanup_old_notifications(older_than_days: int = 90):
    """
    Clean up old notifications from the database.
    """
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=older_than_days)).isoformat()
        
        # Delete old read notifications
        result = supabase.table("notifications").delete().lt(
            "created_at", cutoff_date
        ).eq("read", True).execute()
        
        # Record cleanup on blockchain
        cleanup_transaction = None
        try:
            cleanup_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.SYSTEM_MAINTENANCE,
                data={
                    "action": "notification_cleanup",
                    "older_than_days": older_than_days,
                    "cutoff_date": cutoff_date
                },
                metadata={
                    "source": "system_cleanup",
                    "maintenance_operation": True
                }
            )
            
            blockchain_service.add_transaction(cleanup_transaction)
            
        except Exception as e:
            print(f"[BLOCKCHAIN] Cleanup transaction failed: {e}")
        
        logger.info(f"Cleaned up old notifications before {cutoff_date}")
        
        return {
            "message": "Old notifications cleaned up",
            "cutoff_date": cutoff_date,
            "blockchain_tx_id": cleanup_transaction.transaction_id if cleanup_transaction else None
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up old notifications: {str(e)}")
        return None