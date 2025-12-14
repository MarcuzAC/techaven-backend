import logging
from typing import List, Optional, Dict, Any
import json
import requests
import asyncio
from datetime import datetime
from supabase import create_client, Client

from config import settings

logger = logging.getLogger(__name__)

class PushNotificationService:
    """Push notification service using Supabase."""
    
    def __init__(self):
        # Initialize Supabase client
        try:
            self.supabase: Client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_KEY
            )
            
            # Check if we have service role key for admin operations
            self.supabase_admin: Optional[Client] = None
            if hasattr(settings, 'SUPABASE_SERVICE_KEY') and settings.SUPABASE_SERVICE_KEY:
                self.supabase_admin = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_SERVICE_KEY
                )
            
            logger.info("Supabase push notification service initialized")
            
        except Exception as e:
            logger.error(f"Error initializing Supabase client: {str(e)}")
            self.supabase = None
            self.supabase_admin = None
    
    def send_push_notification(
        self,
        device_tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        image_url: Optional[str] = None,
        badge: Optional[int] = None,
        sound: str = "default",
        priority: str = "high",
        collapse_key: Optional[str] = None,
        time_to_live: int = 2419200,  # 28 days in seconds
        android_channel_id: Optional[str] = None,
        category: Optional[str] = None,
        mutable_content: bool = True
    ) -> Dict[str, Any]:
        """Send push notification via Supabase Edge Functions."""
        try:
            # Remove invalid/empty tokens
            valid_tokens = [token for token in device_tokens if token and token.strip()]
            
            if not valid_tokens:
                logger.warning("No valid device tokens provided")
                return {
                    "success": False, 
                    "error": "No valid device tokens", 
                    "total": 0, 
                    "successful": 0, 
                    "failed": 0
                }
            
            # In development mode without Supabase, just log
            if not self.supabase and settings.DEBUG:
                logger.info(f"[DEV MODE] Would send push to {len(valid_tokens)} devices: {title}")
                for token in valid_tokens:
                    logger.info(f"[DEV MODE] Token: {token[:20]}..., Title: {title}, Body: {body}")
                
                return {
                    "success": True,
                    "total": len(valid_tokens),
                    "successful": len(valid_tokens),
                    "failed": 0,
                    "failed_tokens": []
                }
            
            # Try to send via Supabase Edge Function
            try:
                return self._send_via_supabase_edge(
                    device_tokens=valid_tokens,
                    title=title,
                    body=body,
                    data=data,
                    image_url=image_url,
                    badge=badge,
                    sound=sound,
                    priority=priority
                )
            except Exception as edge_error:
                logger.warning(f"Supabase Edge Function failed: {edge_error}. Falling back to database storage.")
                return self._store_in_database(
                    device_tokens=valid_tokens,
                    title=title,
                    body=body,
                    data=data
                )
            
        except Exception as e:
            logger.error(f"Error sending push notification: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "total": len(device_tokens),
                "successful": 0,
                "failed": len(device_tokens)
            }
    
    def _send_via_supabase_edge(
        self,
        device_tokens: List[str],
        title: str,
        body: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Send push notification via Supabase Edge Function."""
        try:
            # Prepare payload for Supabase Edge Function
            payload = {
                "tokens": device_tokens,
                "notification": {
                    "title": title,
                    "body": body,
                    "image": kwargs.get('image_url')
                },
                "data": kwargs.get('data') or {},
                "options": {
                    "priority": kwargs.get('priority', 'high'),
                    "ttl": kwargs.get('time_to_live', 2419200),
                    "sound": kwargs.get('sound', 'default'),
                    "badge": kwargs.get('badge'),
                    "android_channel_id": kwargs.get('android_channel_id'),
                    "category": kwargs.get('category')
                }
            }
            
            # Call Supabase Edge Function
            # Note: You need to create this Edge Function in your Supabase project
            response = self.supabase.functions.invoke(
                "send-push-notification",
                body=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Push notification sent via Supabase Edge Function: {result}")
                return {
                    "success": True,
                    "total": len(device_tokens),
                    "successful": result.get("successful", len(device_tokens)),
                    "failed": result.get("failed", 0),
                    "failed_tokens": result.get("failed_tokens", []),
                    "method": "supabase_edge"
                }
            else:
                raise Exception(f"Edge Function failed with status {response.status_code}")
                
        except Exception as e:
            logger.error(f"Supabase Edge Function error: {str(e)}")
            raise
    
    def _store_in_database(
        self,
        device_tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Store push notifications in database for later processing."""
        try:
            # Store notifications in a database table
            notifications = []
            for token in device_tokens:
                notification = {
                    "device_token": token,
                    "title": title,
                    "body": body,
                    "data": data or {},
                    "status": "pending",
                    "attempts": 0,
                    "created_at": datetime.utcnow().isoformat()
                }
                notifications.append(notification)
            
            # Insert into database (assuming you have a 'push_notifications' table)
            if self.supabase:
                response = self.supabase.table("push_notifications").insert(notifications).execute()
                
                logger.info(f"Stored {len(notifications)} push notifications in database")
                return {
                    "success": True,
                    "total": len(device_tokens),
                    "successful": len(device_tokens),
                    "failed": 0,
                    "method": "database_storage",
                    "notification_ids": [n.get("id") for n in response.data] if response.data else []
                }
            else:
                raise Exception("Supabase client not available")
                
        except Exception as e:
            logger.error(f"Database storage error: {str(e)}")
            raise
    
    async def send_push_notification_async(
        self,
        device_tokens: List[str],
        title: str,
        body: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Send push notification asynchronously."""
        try:
            # Run in thread pool to avoid blocking
            return await asyncio.get_event_loop().run_in_executor(
                None, self.send_push_notification, device_tokens, title, body, kwargs
            )
        except Exception as e:
            logger.error(f"Error sending async push notification: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "total": len(device_tokens),
                "successful": 0,
                "failed": len(device_tokens)
            }
    
    def register_device_token(
        self,
        user_id: str,
        device_token: str,
        platform: str = "unknown",
        device_id: Optional[str] = None,
        device_model: Optional[str] = None,
        app_version: Optional[str] = None,
        os_version: Optional[str] = None
    ) -> bool:
        """Register a device token for a user."""
        try:
            if not self.supabase:
                if settings.DEBUG:
                    logger.info(f"[DEV MODE] Would register device token for user {user_id}: {device_token[:20]}...")
                    return True
                return False
            
            # Check if token already exists
            response = self.supabase.table("device_tokens") \
                .select("*") \
                .eq("device_token", device_token) \
                .execute()
            
            if response.data and len(response.data) > 0:
                # Update existing token
                existing = response.data[0]
                update_data = {
                    "user_id": user_id,
                    "platform": platform,
                    "device_id": device_id,
                    "device_model": device_model,
                    "app_version": app_version,
                    "os_version": os_version,
                    "last_used_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
                
                self.supabase.table("device_tokens") \
                    .update(update_data) \
                    .eq("id", existing["id"]) \
                    .execute()
                
                logger.info(f"Updated existing device token for user {user_id}")
            else:
                # Insert new token
                token_data = {
                    "user_id": user_id,
                    "device_token": device_token,
                    "platform": platform,
                    "device_id": device_id,
                    "device_model": device_model,
                    "app_version": app_version,
                    "os_version": os_version,
                    "is_active": True,
                    "last_used_at": datetime.utcnow().isoformat(),
                    "created_at": datetime.utcnow().isoformat()
                }
                
                self.supabase.table("device_tokens") \
                    .insert(token_data) \
                    .execute()
                
                logger.info(f"Registered new device token for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error registering device token: {str(e)}")
            return False
    
    def unregister_device_token(
        self,
        user_id: str,
        device_token: str
    ) -> bool:
        """Unregister a device token."""
        try:
            if not self.supabase:
                if settings.DEBUG:
                    logger.info(f"[DEV MODE] Would unregister device token for user {user_id}: {device_token[:20]}...")
                    return True
                return False
            
            # Soft delete: mark as inactive
            self.supabase.table("device_tokens") \
                .update({
                    "is_active": False,
                    "unregistered_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }) \
                .eq("user_id", user_id) \
                .eq("device_token", device_token) \
                .execute()
            
            logger.info(f"Unregistered device token for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error unregistering device token: {str(e)}")
            return False
    
    def get_user_device_tokens(
        self,
        user_id: str,
        active_only: bool = True
    ) -> List[str]:
        """Get device tokens for a user."""
        try:
            if not self.supabase:
                if settings.DEBUG:
                    logger.info(f"[DEV MODE] Would get device tokens for user {user_id}")
                    return ["dev_token_1", "dev_token_2"]
                return []
            
            query = self.supabase.table("device_tokens") \
                .select("device_token") \
                .eq("user_id", user_id)
            
            if active_only:
                query = query.eq("is_active", True)
            
            response = query.execute()
            
            tokens = [item["device_token"] for item in response.data]
            logger.info(f"Found {len(tokens)} device tokens for user {user_id}")
            return tokens
            
        except Exception as e:
            logger.error(f"Error getting user device tokens: {str(e)}")
            return []
    
    def validate_device_token(self, token: str) -> bool:
        """Validate device token format."""
        if not token or not token.strip():
            return False
        
        # Basic validation - adjust based on your token format
        # For Expo: starts with ExponentPushToken
        # For FCM: typically long strings
        return len(token) > 10
    
    def update_notification_status(
        self,
        notification_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """Update notification status in database."""
        try:
            if not self.supabase:
                return False
            
            update_data = {
                "status": status,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if status == "sent":
                update_data["sent_at"] = datetime.utcnow().isoformat()
            elif status == "delivered":
                update_data["delivered_at"] = datetime.utcnow().isoformat()
            elif status == "failed" and error_message:
                update_data["error_message"] = error_message
                update_data["failed_at"] = datetime.utcnow().isoformat()
            
            self.supabase.table("push_notifications") \
                .update(update_data) \
                .eq("id", notification_id) \
                .execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating notification status: {str(e)}")
            return False
    
    def send_to_user(
        self,
        user_id: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send push notification to a specific user."""
        try:
            # Get user's device tokens
            device_tokens = self.get_user_device_tokens(user_id, active_only=True)
            
            if not device_tokens:
                logger.warning(f"No active device tokens found for user {user_id}")
                return {
                    "success": False,
                    "error": "No active device tokens",
                    "total": 0,
                    "successful": 0,
                    "failed": 0
                }
            
            # Add user_id to data if not present
            if data is None:
                data = {}
            if "user_id" not in data:
                data["user_id"] = user_id
            
            # Send notification
            return self.send_push_notification(
                device_tokens=device_tokens,
                title=title,
                body=body,
                data=data,
                **kwargs
            )
            
        except Exception as e:
            logger.error(f"Error sending push to user {user_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "total": 0,
                "successful": 0,
                "failed": 0
            }
    
    def send_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send push notification to a topic (group of users)."""
        try:
            if not self.supabase:
                if settings.DEBUG:
                    logger.info(f"[DEV MODE] Would send to topic {topic}: {title}")
                    return {"success": True, "total": 10, "successful": 10, "failed": 0}
                return {"success": False, "error": "Supabase not configured"}
            
            # Get device tokens for users subscribed to this topic
            # Assuming you have a 'user_topics' or similar table
            response = self.supabase.rpc(
                "get_topic_device_tokens",
                {"topic_name": topic}
            ).execute()
            
            if not response.data:
                logger.warning(f"No device tokens found for topic {topic}")
                return {
                    "success": False,
                    "error": "No device tokens for topic",
                    "total": 0,
                    "successful": 0,
                    "failed": 0
                }
            
            device_tokens = [item["device_token"] for item in response.data]
            
            # Add topic to data if not present
            if data is None:
                data = {}
            if "topic" not in data:
                data["topic"] = topic
            
            # Send notification
            return self.send_push_notification(
                device_tokens=device_tokens,
                title=title,
                body=body,
                data=data,
                **kwargs
            )
            
        except Exception as e:
            logger.error(f"Error sending push to topic {topic}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "total": 0,
                "successful": 0,
                "failed": 0
            }

# Global push service instance
_push_service = None

def get_push_service() -> PushNotificationService:
    """Get or create push notification service instance."""
    global _push_service
    
    if _push_service is None:
        _push_service = PushNotificationService()
    
    return _push_service

def send_push_notification(*args, **kwargs) -> Dict[str, Any]:
    """Send push notification (convenience function)."""
    service = get_push_service()
    return service.send_push_notification(*args, **kwargs)

async def send_push_notification_async(*args, **kwargs) -> Dict[str, Any]:
    """Send push notification asynchronously (convenience function)."""
    service = get_push_service()
    return await service.send_push_notification_async(*args, **kwargs)

def send_to_user(user_id: str, *args, **kwargs) -> Dict[str, Any]:
    """Send push notification to user (convenience function)."""
    service = get_push_service()
    return service.send_to_user(user_id, *args, **kwargs)

def send_to_topic(topic: str, *args, **kwargs) -> Dict[str, Any]:
    """Send push notification to topic (convenience function)."""
    service = get_push_service()
    return service.send_to_topic(topic, *args, **kwargs)

def register_device_token(*args, **kwargs) -> bool:
    """Register device token (convenience function)."""
    service = get_push_service()
    return service.register_device_token(*args, **kwargs)

def unregister_device_token(*args, **kwargs) -> bool:
    """Unregister device token (convenience function)."""
    service = get_push_service()
    return service.unregister_device_token(*args, **kwargs)

def get_user_device_tokens(*args, **kwargs) -> List[str]:
    """Get user device tokens (convenience function)."""
    service = get_push_service()
    return service.get_user_device_tokens(*args, **kwargs)

def validate_device_token(token: str) -> bool:
    """Validate device token (convenience function)."""
    service = get_push_service()
    return service.validate_device_token(token)

# Common push notification templates
def get_order_update_push_data(order_data: Dict[str, Any], update_type: str) -> Dict[str, Any]:
    """Get push notification data for order updates."""
    return {
        "type": "order_update",
        "order_id": order_data.get("id"),
        "order_number": order_data.get("order_number"),
        "status": order_data.get("status"),
        "update_type": update_type,
        "timestamp": datetime.utcnow().isoformat(),
        "deep_link": f"{settings.APP_URL}/orders/{order_data.get('id')}"
    }

def get_promotion_push_data(promotion_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get push notification data for promotions."""
    return {
        "type": "promotion",
        "promotion_id": promotion_data.get("id"),
        "title": promotion_data.get("title"),
        "discount": promotion_data.get("discount"),
        "expires_at": promotion_data.get("expires_at"),
        "timestamp": datetime.utcnow().isoformat(),
        "deep_link": f"{settings.APP_URL}/promotions/{promotion_data.get('id')}"
    }

def get_price_drop_push_data(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get push notification data for price drops."""
    return {
        "type": "price_drop",
        "product_id": product_data.get("id"),
        "product_name": product_data.get("name"),
        "old_price": product_data.get("old_price"),
        "new_price": product_data.get("new_price"),
        "discount_percentage": product_data.get("discount_percentage"),
        "timestamp": datetime.utcnow().isoformat(),
        "deep_link": f"{settings.APP_URL}/products/{product_data.get('id')}"
    }

def get_security_alert_push_data(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get push notification data for security alerts."""
    return {
        "type": "security_alert",
        "alert_type": alert_data.get("alert_type"),
        "severity": alert_data.get("severity"),
        "message": alert_data.get("message"),
        "timestamp": datetime.utcnow().isoformat(),
        "deep_link": f"{settings.APP_URL}/account/security"
    }

def get_new_message_push_data(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get push notification data for new messages."""
    return {
        "type": "new_message",
        "message_id": message_data.get("id"),
        "sender_id": message_data.get("sender_id"),
        "sender_name": message_data.get("sender_name"),
        "preview": message_data.get("preview"),
        "timestamp": datetime.utcnow().isoformat(),
        "deep_link": f"{settings.APP_URL}/messages/{message_data.get('id')}"
    }

def get_review_reminder_push_data(order_data: Dict[str, Any], product_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get push notification data for review reminders."""
    return {
        "type": "review_reminder",
        "order_id": order_data.get("id"),
        "order_number": order_data.get("order_number"),
        "product_id": product_data.get("id"),
        "product_name": product_data.get("name"),
        "timestamp": datetime.utcnow().isoformat(),
        "deep_link": f"{settings.APP_URL}/products/{product_data.get('id')}/review"
    }