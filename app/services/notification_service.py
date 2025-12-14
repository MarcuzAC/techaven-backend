from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, and_, or_
import logging
import json

from model.models import Notification, NotificationTemplate, NotificationDelivery, UserNotificationPreference, DeviceToken, User
# Update import path to match your project structure
from app.model.models import (
    NotificationCreate, NotificationResponse, NotificationFilter,
    NotificationPreferenceUpdate, UserNotificationPreference as UserNotificationPreferenceSchema,
    NotificationTemplateCreate, NotificationTemplateUpdate, NotificationTemplateResponse,
    EmailNotification, SMSNotification, PushNotification, DeviceToken as DeviceTokenSchema,
    NotificationType, NotificationPriority, NotificationStatus  # Import enums from your models
)
from config import settings
from utils.email import send_email
from utils.sms import send_sms
from utils.push import send_push_notification
from services.blockchain_service import create_blockchain_transaction

logger = logging.getLogger(__name__)

# Notification creation and management
def create_notification(db: Session, notification_data: NotificationCreate) -> Notification:
    """Create a new notification."""
    try:
        notification = Notification(
            user_id=notification_data.user_id,
            title=notification_data.title,
            message=notification_data.message,
            notification_type=notification_data.notification_type.value if isinstance(notification_data.notification_type, NotificationType) else notification_data.notification_type,
            priority=notification_data.priority.value if isinstance(notification_data.priority, NotificationPriority) else notification_data.priority,
            data=json.dumps(notification_data.data) if notification_data.data else None,
            action_url=str(notification_data.action_url) if notification_data.action_url else None,
            action_text=notification_data.action_text,
            image_url=str(notification_data.image_url) if notification_data.image_url else None,
            icon=notification_data.icon,
            tags=json.dumps(notification_data.tags) if notification_data.tags else None,
            metadata=json.dumps(notification_data.metadata) if notification_data.metadata else None,
            status=NotificationStatus.PENDING.value
        )
        
        db.add(notification)
        db.commit()
        db.refresh(notification)
        
        return notification
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating notification: {str(e)}")
        raise

def create_bulk_notifications(db: Session, notifications_data: List[NotificationCreate]) -> List[Notification]:
    """Create multiple notifications at once."""
    try:
        notifications = []
        for data in notifications_data:
            notification = create_notification(db, data)
            notifications.append(notification)
        
        return notifications
    except Exception as e:
        logger.error(f"Error creating bulk notifications: {str(e)}")
        raise

def get_notifications(db: Session, filter_params: NotificationFilter) -> Tuple[List[Notification], int]:
    """Get notifications with filtering and pagination."""
    try:
        query = db.query(Notification)
        
        # Apply filters
        if filter_params.user_id:
            query = query.filter(Notification.user_id == filter_params.user_id)
        
        if filter_params.notification_type:
            query = query.filter(Notification.notification_type == filter_params.notification_type.value if isinstance(filter_params.notification_type, NotificationType) else filter_params.notification_type)
        
        if filter_params.status:
            query = query.filter(Notification.status == filter_params.status.value if isinstance(filter_params.status, NotificationStatus) else filter_params.status)
        
        if filter_params.read is not None:
            query = query.filter(Notification.read == filter_params.read)
        
        if filter_params.priority:
            query = query.filter(Notification.priority == filter_params.priority.value if isinstance(filter_params.priority, NotificationPriority) else filter_params.priority)
        
        if filter_params.start_date:
            query = query.filter(Notification.created_at >= filter_params.start_date)
        
        if filter_params.end_date:
            query = query.filter(Notification.created_at <= filter_params.end_date)
        
        if filter_params.search:
            search_term = f"%{filter_params.search}%"
            query = query.filter(
                or_(
                    Notification.title.ilike(search_term),
                    Notification.message.ilike(search_term)
                )
            )
        
        if filter_params.tags:
            # Search for tags (stored as JSON array)
            for tag in filter_params.tags:
                query = query.filter(Notification.tags.contains(tag))
        
        # Apply sorting
        if filter_params.sort_by == "priority":
            order_by = Notification.priority
        elif filter_params.sort_by == "read":
            order_by = Notification.read
        else:
            order_by = Notification.created_at
        
        if filter_params.sort_order == "asc":
            query = query.order_by(asc(order_by))
        else:
            query = query.order_by(desc(order_by))
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        query = query.offset(filter_params.offset).limit(filter_params.limit)
        
        notifications = query.all()
        return notifications, total
        
    except Exception as e:
        logger.error(f"Error getting notifications: {str(e)}")
        raise

def get_notification_by_id(db: Session, notification_id: str) -> Optional[Notification]:
    """Get notification by ID."""
    try:
        notification = db.query(Notification).filter(Notification.id == notification_id).first()
        return notification
    except Exception as e:
        logger.error(f"Error getting notification by ID: {str(e)}")
        return None

def update_notification_status(db: Session, notification_id: str, 
                              status: NotificationStatus, read: bool = None) -> Optional[Notification]:
    """Update notification status."""
    try:
        notification = get_notification_by_id(db, notification_id)
        if not notification:
            return None
        
        notification.status = status.value if isinstance(status, NotificationStatus) else status
        
        if read is not None:
            notification.read = read
            if read and not notification.read_at:
                notification.read_at = datetime.utcnow()
        
        notification.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(notification)
        
        return notification
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating notification status: {str(e)}")
        return None

def mark_notification_as_read(db: Session, notification_id: str) -> Optional[Notification]:
    """Mark notification as read."""
    return update_notification_status(db, notification_id, NotificationStatus.READ, read=True)

def mark_notification_as_unread(db: Session, notification_id: str) -> Optional[Notification]:
    """Mark notification as unread."""
    return update_notification_status(db, notification_id, NotificationStatus.DELIVERED, read=False)

def delete_notification(db: Session, notification_id: str) -> bool:
    """Delete a notification."""
    try:
        notification = get_notification_by_id(db, notification_id)
        if not notification:
            return False
        
        db.delete(notification)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting notification: {str(e)}")
        return False

def get_unread_count(db: Session, user_id: str) -> int:
    """Get count of unread notifications for user."""
    try:
        count = db.query(Notification).filter(
            and_(
                Notification.user_id == user_id,
                Notification.read == False,
                Notification.status == NotificationStatus.DELIVERED.value
            )
        ).count()
        
        return count
    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        return 0

# Notification delivery
def send_notification_now(db: Session, notification_id: str) -> bool:
    """Send notification immediately."""
    try:
        notification = get_notification_by_id(db, notification_id)
        if not notification:
            return False
        
        # Get user preferences
        preferences = get_user_preferences(db, notification.user_id)
        
        # Determine channels based on preferences
        channels = []
        
        # Check if user has preferences for this notification type
        notification_type_key = notification.notification_type.lower()
        if notification_type_key in preferences.categories:
            if preferences.categories[notification_type_key]:
                # Use default channels or notification-specific channels
                if notification.channels:
                    channels = json.loads(notification.channels)
                else:
                    channels = ["in_app"]  # Default channel
        
        # Update notification status
        notification.status = NotificationStatus.SENT.value
        notification.sent_at = datetime.utcnow()
        
        # Create delivery records
        for channel in channels:
            delivery = NotificationDelivery(
                notification_id=notification.id,
                channel=channel,
                status="pending",
                created_at=datetime.utcnow()
            )
            db.add(delivery)
            
            # Send via appropriate channel
            if channel == "email":
                send_notification_email(db, notification, delivery)
            elif channel == "sms":
                send_notification_sms(db, notification, delivery)
            elif channel == "push":
                send_notification_push(db, notification, delivery)
            elif channel == "in_app":
                # In-app notifications are already delivered
                delivery.status = "delivered"
                delivery.delivered_at = datetime.utcnow()
        
        # Mark as delivered for in-app
        notification.status = NotificationStatus.DELIVERED.value
        notification.delivered_at = datetime.utcnow()
        
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="notification_send",
            user_id=notification.user_id,
            data={
                "notification_id": notification.id,
                "channels": channels,
                "sent_at": datetime.utcnow().isoformat()
            }
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error sending notification: {str(e)}")
        return False

def schedule_notification(db: Session, notification_id: str, schedule_for: datetime) -> bool:
    """Schedule notification for later delivery."""
    try:
        notification = get_notification_by_id(db, notification_id)
        if not notification:
            return False
        
        notification.schedule_for = schedule_for
        notification.status = NotificationStatus.PENDING.value
        db.commit()
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error scheduling notification: {str(e)}")
        return False

def cancel_scheduled_notification(db: Session, notification_id: str) -> bool:
    """Cancel a scheduled notification."""
    try:
        notification = get_notification_by_id(db, notification_id)
        if not notification or notification.status != NotificationStatus.PENDING.value:
            return False
        
        notification.status = NotificationStatus.CANCELLED.value
        notification.updated_at = datetime.utcnow()
        db.commit()
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error cancelling scheduled notification: {str(e)}")
        return False

# User preferences
def get_user_preferences(db: Session, user_id: str) -> UserNotificationPreferenceSchema:
    """Get user notification preferences."""
    try:
        preferences = db.query(UserNotificationPreference).filter(
            UserNotificationPreference.user_id == user_id
        ).first()
        
        if not preferences:
            # Create default preferences
            preferences = UserNotificationPreference(
                user_id=user_id,
                email_enabled=True,
                sms_enabled=False,
                push_enabled=True,
                in_app_enabled=True,
                digest_enabled=True,
                digest_frequency="daily",
                categories={
                    "order": True,
                    "product": True,
                    "payment": True,
                    "shipment": True,
                    "account": True,
                    "security": True,
                    "promotion": False,
                    "system": True,
                    "review": True,
                    "support": True
                }
            )
            db.add(preferences)
            db.commit()
            db.refresh(preferences)
        
        return UserNotificationPreferenceSchema(
            user_id=preferences.user_id,
            email_enabled=preferences.email_enabled,
            sms_enabled=preferences.sms_enabled,
            push_enabled=preferences.push_enabled,
            in_app_enabled=preferences.in_app_enabled,
            digest_enabled=preferences.digest_enabled,
            digest_frequency=preferences.digest_frequency,
            quiet_hours_start=preferences.quiet_hours_start,
            quiet_hours_end=preferences.quiet_hours_end,
            categories=preferences.categories,
            created_at=preferences.created_at,
            updated_at=preferences.updated_at
        )
    except Exception as e:
        logger.error(f"Error getting user preferences: {str(e)}")
        # Return default preferences on error
        return UserNotificationPreferenceSchema(
            user_id=user_id,
            email_enabled=True,
            sms_enabled=False,
            push_enabled=True,
            in_app_enabled=True,
            digest_enabled=True,
            digest_frequency="daily",
            categories={
                "order": True,
                "product": True,
                "payment": True,
                "shipment": True,
                "account": True,
                "security": True,
                "promotion": False,
                "system": True,
                "review": True,
                "support": True
            }
        )

def update_user_preferences(db: Session, user_id: str, 
                           update_data: NotificationPreferenceUpdate) -> UserNotificationPreferenceSchema:
    """Update user notification preferences."""
    try:
        preferences = db.query(UserNotificationPreference).filter(
            UserNotificationPreference.user_id == user_id
        ).first()
        
        if not preferences:
            # Create new preferences
            preferences = UserNotificationPreference(user_id=user_id)
            db.add(preferences)
        
        # Update fields
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(preferences, field) and value is not None:
                setattr(preferences, field, value)
        
        preferences.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(preferences)
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="notification_preferences_update",
            user_id=user_id,
            data={"updates": update_dict}
        )
        
        return UserNotificationPreferenceSchema(
            user_id=preferences.user_id,
            email_enabled=preferences.email_enabled,
            sms_enabled=preferences.sms_enabled,
            push_enabled=preferences.push_enabled,
            in_app_enabled=preferences.in_app_enabled,
            digest_enabled=preferences.digest_enabled,
            digest_frequency=preferences.digest_frequency,
            quiet_hours_start=preferences.quiet_hours_start,
            quiet_hours_end=preferences.quiet_hours_end,
            categories=preferences.categories,
            created_at=preferences.created_at,
            updated_at=preferences.updated_at
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user preferences: {str(e)}")
        raise

# Template management
def create_notification_template(db: Session, template_data: NotificationTemplateCreate, 
                                created_by: str) -> NotificationTemplate:
    """Create a notification template."""
    try:
        # Check if template with same slug exists
        existing = db.query(NotificationTemplate).filter(
            NotificationTemplate.slug == template_data.slug
        ).first()
        
        if existing:
            raise ValueError(f"Template with slug '{template_data.slug}' already exists")
        
        template = NotificationTemplate(
            name=template_data.name,
            slug=template_data.slug,
            title_template=template_data.title_template,
            message_template=template_data.message_template,
            notification_type=template_data.notification_type.value if isinstance(template_data.notification_type, NotificationType) else template_data.notification_type,
            category=template_data.category,
            priority=template_data.priority.value if isinstance(template_data.priority, NotificationPriority) else template_data.priority,
            default_channels=json.dumps(template_data.default_channels) if template_data.default_channels else None,
            variables=json.dumps(template_data.variables) if template_data.variables else None,
            is_active=template_data.is_active,
            description=template_data.description,
            created_by=created_by
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="notification_template_create",
            user_id=created_by,
            data={
                "template_id": template.id,
                "template_name": template.name,
                "slug": template.slug
            }
        )
        
        return template
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating notification template: {str(e)}")
        raise

def get_notification_templates(db: Session, is_active: bool = None, 
                              category: str = None) -> List[NotificationTemplate]:
    """Get notification templates."""
    try:
        query = db.query(NotificationTemplate)
        
        if is_active is not None:
            query = query.filter(NotificationTemplate.is_active == is_active)
        
        if category:
            query = query.filter(NotificationTemplate.category == category)
        
        templates = query.order_by(desc(NotificationTemplate.created_at)).all()
        return templates
    except Exception as e:
        logger.error(f"Error getting notification templates: {str(e)}")
        return []

def get_notification_template_by_id(db: Session, template_id: str) -> Optional[NotificationTemplate]:
    """Get notification template by ID."""
    try:
        template = db.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
        return template
    except Exception as e:
        logger.error(f"Error getting notification template by ID: {str(e)}")
        return None

def get_notification_template_by_slug(db: Session, slug: str) -> Optional[NotificationTemplate]:
    """Get notification template by slug."""
    try:
        template = db.query(NotificationTemplate).filter(NotificationTemplate.slug == slug).first()
        return template
    except Exception as e:
        logger.error(f"Error getting notification template by slug: {str(e)}")
        return None

def update_notification_template(db: Session, template_id: str, 
                                update_data: NotificationTemplateUpdate) -> Optional[NotificationTemplate]:
    """Update notification template."""
    try:
        template = get_notification_template_by_id(db, template_id)
        if not template:
            return None
        
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(template, field) and value is not None:
                setattr(template, field, value)
        
        template.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(template)
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="notification_template_update",
            user_id=template.created_by,
            data={"template_id": template_id, "updates": update_dict}
        )
        
        return template
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating notification template: {str(e)}")
        return None

def delete_notification_template(db: Session, template_id: str) -> bool:
    """Delete notification template."""
    try:
        template = get_notification_template_by_id(db, template_id)
        if not template:
            return False
        
        db.delete(template)
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="notification_template_delete",
            user_id="system",
            data={"template_id": template_id}
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting notification template: {str(e)}")
        return False

# Channel-specific notification sending
def send_email_notification(db: Session, email_data: EmailNotification) -> bool:
    """Send email notification."""
    try:
        # Prepare email data
        email_payload = {
            "to": email_data.to,
            "subject": email_data.subject,
            "body": email_data.body_html or email_data.body_text,
            "body_type": "html" if email_data.body_html else "text",
            "template_id": email_data.template_id,
            "template_data": email_data.template_data,
            "reply_to": email_data.reply_to,
            "attachments": email_data.attachments,
            "headers": email_data.headers
        }
        
        # Send email
        success = send_email(**email_payload)
        
        return success
    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")
        return False

def send_sms_notification(db: Session, sms_data: SMSNotification) -> bool:
    """Send SMS notification."""
    try:
        # Send SMS
        success = send_sms(
            to=sms_data.to,
            message=sms_data.message,
            sender_id=sms_data.sender_id
        )
        
        return success
    except Exception as e:
        logger.error(f"Error sending SMS notification: {str(e)}")
        return False

def send_push_notification_service(db: Session, push_data: PushNotification) -> bool:
    """Send push notification."""
    try:
        # Get device tokens for users
        device_tokens = db.query(DeviceToken).filter(
            and_(
                DeviceToken.user_id.in_([user_id for user_id in push_data.device_tokens]),
                DeviceToken.is_active == True
            )
        ).all()
        
        if not device_tokens:
            return False
        
        # Prepare push data
        push_payload = {
            "device_tokens": [token.token for token in device_tokens],
            "title": push_data.title,
            "body": push_data.body,
            "data": push_data.data,
            "image_url": str(push_data.image_url) if push_data.image_url else None,
            "badge": push_data.badge,
            "sound": push_data.sound,
            "priority": push_data.priority,
            "collapse_key": push_data.collapse_key,
            "time_to_live": push_data.time_to_live
        }
        
        # Send push notification
        success = send_push_notification(**push_payload)
        
        return success
    except Exception as e:
        logger.error(f"Error sending push notification: {str(e)}")
        return False

# Device token management
def register_device_token(db: Session, user_id: str, device_data: DeviceTokenSchema) -> bool:
    """Register a device token for push notifications."""
    try:
        # Check if token already exists
        existing_token = db.query(DeviceToken).filter(
            DeviceToken.token == device_data.token
        ).first()
        
        if existing_token:
            # Update existing token
            existing_token.user_id = user_id
            existing_token.platform = device_data.platform
            existing_token.device_id = device_data.device_id
            existing_token.device_model = device_data.device_model
            existing_token.app_version = device_data.app_version
            existing_token.os_version = device_data.os_version
            existing_token.is_active = device_data.is_active
            existing_token.last_used_at = datetime.utcnow()
            existing_token.updated_at = datetime.utcnow()
        else:
            # Create new token
            device_token = DeviceToken(
                user_id=user_id,
                token=device_data.token,
                platform=device_data.platform,
                device_id=device_data.device_id,
                device_model=device_data.device_model,
                app_version=device_data.app_version,
                os_version=device_data.os_version,
                is_active=device_data.is_active,
                last_used_at=datetime.utcnow()
            )
            db.add(device_token)
        
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error registering device token: {str(e)}")
        return False

def unregister_device_token(db: Session, user_id: str, device_token: str) -> bool:
    """Unregister a device token."""
    try:
        token = db.query(DeviceToken).filter(
            and_(
                DeviceToken.user_id == user_id,
                DeviceToken.token == device_token
            )
        ).first()
        
        if not token:
            return False
        
        db.delete(token)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error unregistering device token: {str(e)}")
        return False

# Statistics and analytics
def get_notification_stats(db: Session, user_id: str = None, 
                          start_date: datetime = None, end_date: datetime = None) -> Dict[str, Any]:
    """Get notification statistics."""
    try:
        query = db.query(Notification)
        
        if user_id:
            query = query.filter(Notification.user_id == user_id)
        
        if start_date:
            query = query.filter(Notification.created_at >= start_date)
        
        if end_date:
            query = query.filter(Notification.created_at <= end_date)
        
        # Total notifications
        total = query.count()
        
        # Unread notifications
        unread = query.filter(Notification.read == False).count()
        
        # Sent today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = query.filter(
            and_(
                Notification.sent_at >= today_start,
                Notification.status == NotificationStatus.SENT.value
            )
        ).count()
        
        # Failed today
        failed_today = query.filter(
            and_(
                Notification.created_at >= today_start,
                Notification.status == NotificationStatus.FAILED.value
            )
        ).count()
        
        # By category
        by_category = {}
        by_type = {}
        
        notifications = query.all()
        for notification in notifications:
            category = notification.notification_type
            ntype = notification.notification_type
            
            by_category[category] = by_category.get(category, 0) + 1
            by_type[ntype] = by_type.get(ntype, 0) + 1
        
        return {
            "total": total,
            "unread": unread,
            "read": total - unread,
            "sent_today": sent_today,
            "failed_today": failed_today,
            "by_category": by_category,
            "by_type": by_type,
            "avg_delivery_time": None  # Would need delivery timestamps
        }
    except Exception as e:
        logger.error(f"Error getting notification stats: {str(e)}")
        return {}

def get_notification_analytics(db: Session, start_date: datetime = None, 
                              end_date: datetime = None, interval: str = "day") -> Dict[str, Any]:
    """Get detailed notification analytics."""
    try:
        # Set default date range
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        # This would require more complex queries and potentially
        # a separate analytics database or caching system
        # For now, return basic stats
        
        query = db.query(Notification).filter(
            Notification.created_at.between(start_date, end_date)
        )
        
        total_sent = query.filter(Notification.status == NotificationStatus.SENT.value).count()
        total_delivered = query.filter(Notification.status == NotificationStatus.DELIVERED.value).count()
        total_read = query.filter(Notification.read == True).count()
        total_failed = query.filter(Notification.status == NotificationStatus.FAILED.value).count()
        
        delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0
        read_rate = (total_read / total_delivered * 100) if total_delivered > 0 else 0
        
        return {
            "total_sent": total_sent,
            "total_delivered": total_delivered,
            "total_read": total_read,
            "total_failed": total_failed,
            "delivery_rate": delivery_rate,
            "read_rate": read_rate,
            "click_rate": None,  # Would need click tracking
            "avg_delivery_time": None,
            "by_channel": {},  # Would need channel data
            "by_category": {},  # Would need aggregation
            "by_hour": {},  # Would need time-based aggregation
            "top_templates": [],  # Would need template usage tracking
            "date_range": {"start_date": start_date, "end_date": end_date}
        }
    except Exception as e:
        logger.error(f"Error getting notification analytics: {str(e)}")
        return {}

# Helper functions
def send_notification_email(db: Session, notification: Notification, delivery: NotificationDelivery) -> None:
    """Send notification via email."""
    try:
        # Get user email
        user = db.query(User).filter(User.id == notification.user_id).first()
        if not user or not user.email:
            delivery.status = "failed"
            delivery.failure_reason = "User email not found"
            return
        
        # Prepare email
        email_data = EmailNotification(
            to=[user.email],
            subject=notification.title,
            body_html=notification.message,  # Could use template
            body_text=notification.message
        )
        
        # Send email
        success = send_email_notification(db, email_data)
        
        if success:
            delivery.status = "delivered"
            delivery.delivered_at = datetime.utcnow()
        else:
            delivery.status = "failed"
            delivery.failure_reason = "Email sending failed"
    except Exception as e:
        logger.error(f"Error sending notification email: {str(e)}")
        delivery.status = "failed"
        delivery.failure_reason = str(e)

def send_notification_sms(db: Session, notification: Notification, delivery: NotificationDelivery) -> None:
    """Send notification via SMS."""
    try:
        # Get user phone number
        user = db.query(User).filter(User.id == notification.user_id).first()
        if not user or not user.phone_number:
            delivery.status = "failed"
            delivery.failure_reason = "User phone number not found"
            return
        
        # Prepare SMS
        sms_data = SMSNotification(
            to=user.phone_number,
            message=notification.message[:160],  # SMS length limit
            sender_id=settings.SMS_SENDER_ID
        )
        
        # Send SMS
        success = send_sms_notification(db, sms_data)
        
        if success:
            delivery.status = "delivered"
            delivery.delivered_at = datetime.utcnow()
        else:
            delivery.status = "failed"
            delivery.failure_reason = "SMS sending failed"
    except Exception as e:
        logger.error(f"Error sending notification SMS: {str(e)}")
        delivery.status = "failed"
        delivery.failure_reason = str(e)

def send_notification_push(db: Session, notification: Notification, delivery: NotificationDelivery) -> None:
    """Send notification via push."""
    try:
        # Get user device tokens
        device_tokens = db.query(DeviceToken).filter(
            and_(
                DeviceToken.user_id == notification.user_id,
                DeviceToken.is_active == True
            )
        ).all()
        
        if not device_tokens:
            delivery.status = "failed"
            delivery.failure_reason = "No active device tokens found"
            return
        
        # Prepare push notification
        push_data = PushNotification(
            device_tokens=[token.token for token in device_tokens],
            title=notification.title,
            body=notification.message,
            data=json.loads(notification.data) if notification.data else {},
            image_url=notification.image_url,
            badge=1  # Increment badge count
        )
        
        # Send push notification
        success = send_push_notification_service(db, push_data)
        
        if success:
            delivery.status = "delivered"
            delivery.delivered_at = datetime.utcnow()
        else:
            delivery.status = "failed"
            delivery.failure_reason = "Push notification sending failed"
    except Exception as e:
        logger.error(f"Error sending notification push: {str(e)}")
        delivery.status = "failed"
        delivery.failure_reason = str(e)