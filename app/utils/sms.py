import logging
from typing import List, Optional, Dict, Any
import requests
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import africastalking
import asyncio
from datetime import datetime

from config import settings

logger = logging.getLogger(__name__)

class SMSService:
    """SMS service for sending notifications."""
    
    def __init__(self):
        self.provider = "twilio" if settings.TWILIO_ACCOUNT_SID else "log"
        self.sender_id = settings.TWILIO_PHONE_NUMBER or "ElectroBazaar"
        self.api_key = None  # Not used with Twilio
        self.api_secret = None  # Not used with Twilio
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        
        # Initialize provider client
        self.client = None
        if self.provider == "twilio" and self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
            logger.info("SMS service initialized with Twilio")
        elif self.provider == "africastalking" and settings.SMS_API_KEY:
            africastalking.initialize(settings.SMS_API_KEY, settings.SMS_API_SECRET)
            self.client = africastalking.SMS
            logger.info("SMS service initialized with Africa's Talking")
        else:
            logger.info("SMS service running in log mode (no real SMS sent)")
    
    def validate_phone_number(self, phone_number: str) -> str:
        """Validate and format phone number."""
        if not phone_number:
            return ""
        
        # Remove all non-numeric characters except +
        cleaned = ''.join(filter(lambda x: x.isdigit() or x == '+', phone_number))
        
        # If no country code, add based on settings or default to +1
        if not cleaned.startswith('+'):
            if cleaned.startswith('0'):
                # Remove leading 0 and add +1 (US/Canada)
                cleaned = "+1" + cleaned[1:]
            else:
                # Add default country code
                cleaned = "+1" + cleaned
        
        return cleaned
    
    def send_sms(
        self,
        to: str,
        message: str,
        sender_id: Optional[str] = None,
        priority: str = "normal"
    ) -> bool:
        """Send SMS synchronously."""
        try:
            # Validate and format phone number
            to = self.validate_phone_number(to)
            if not to:
                logger.error("Invalid phone number")
                return False
            
            # Use provided sender_id or default
            sender = sender_id or self.sender_id
            
            # If Twilio is not configured, log and return success in development
            if not self.client and settings.DEBUG:
                logger.info(f"[DEV MODE] SMS would be sent to {to}: {message[:50]}...")
                return True
            
            # Send based on provider
            if self.provider == "twilio" and self.client:
                return self._send_via_twilio(to, message, sender)
            elif self.provider == "africastalking" and self.client:
                return self._send_via_africastalking(to, message, sender)
            elif self.provider == "custom" and settings.SMS_API_URL:
                return self._send_via_custom_api(to, message, sender)
            else:
                return self._send_via_log(to, message, sender)
            
        except Exception as e:
            logger.error(f"Error sending SMS: {str(e)}")
            return False
    
    async def send_sms_async(
        self,
        to: str,
        message: str,
        sender_id: Optional[str] = None,
        priority: str = "normal"
    ) -> bool:
        """Send SMS asynchronously."""
        try:
            # Run in thread pool to avoid blocking
            return await asyncio.get_event_loop().run_in_executor(
                None, self.send_sms, to, message, sender_id, priority
            )
        except Exception as e:
            logger.error(f"Error sending async SMS: {str(e)}")
            return False
    
    def send_bulk_sms(
        self,
        recipients: List[Dict[str, str]],
        message: str,
        sender_id: Optional[str] = None,
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """Send bulk SMS."""
        results = {
            "total": len(recipients),
            "successful": 0,
            "failed": 0,
            "failed_details": []
        }
        
        # If no SMS provider configured, simulate success in development
        if not self.client and settings.DEBUG:
            logger.info(f"[DEV MODE] Would send {len(recipients)} bulk SMS messages")
            results["successful"] = len(recipients)
            return results
        
        for i in range(0, len(recipients), batch_size):
            batch = recipients[i:i + batch_size]
            for recipient in batch:
                try:
                    success = self.send_sms(
                        to=recipient.get("phone"),
                        message=message,
                        sender_id=sender_id
                    )
                    if success:
                        results["successful"] += 1
                    else:
                        results["failed"] += 1
                        results["failed_details"].append({
                            "phone": recipient.get("phone"),
                            "error": "Failed to send"
                        })
                except Exception as e:
                    results["failed"] += 1
                    results["failed_details"].append({
                        "phone": recipient.get("phone"),
                        "error": str(e)
                    })
            
            # Delay between batches to avoid rate limiting
            if i + batch_size < len(recipients):
                import time
                time.sleep(2)
        
        logger.info(f"Bulk SMS sending completed: {results['successful']} successful, {results['failed']} failed")
        return results
    
    def _send_via_twilio(self, to: str, message: str, sender_id: str) -> bool:
        """Send SMS via Twilio."""
        try:
            # For Twilio, sender_id must be a verified phone number or Messaging Service SID
            if sender_id.startswith('MG'):  # Messaging Service SID
                twilio_message = self.client.messages.create(
                    body=message,
                    messaging_service_sid=sender_id,
                    to=to
                )
            else:  # Phone number
                twilio_message = self.client.messages.create(
                    body=message,
                    from_=sender_id,
                    to=to
                )
            
            logger.info(f"SMS sent via Twilio to {to}, SID: {twilio_message.sid}")
            return True
            
        except TwilioRestException as e:
            logger.error(f"Twilio error: {str(e)}")
            return False
    
    def _send_via_africastalking(self, to: str, message: str, sender_id: str) -> bool:
        """Send SMS via Africa's Talking."""
        try:
            response = self.client.send(
                message=message,
                recipients=[to],
                sender_id=sender_id
            )
            
            if response['SMSMessageData']['Recipients'][0]['status'] == 'Success':
                logger.info(f"SMS sent via Africa's Talking to {to}")
                return True
            else:
                logger.error(f"Africa's Talking error: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Africa's Talking error: {str(e)}")
            return False
    
    def _send_via_custom_api(self, to: str, message: str, sender_id: str) -> bool:
        """Send SMS via custom API endpoint."""
        try:
            # Example implementation for custom SMS gateway
            api_url = settings.SMS_API_URL
            api_params = {
                "api_key": settings.SMS_API_KEY,
                "api_secret": settings.SMS_API_SECRET,
                "to": to,
                "from": sender_id,
                "message": message,
                "type": "text"
            }
            
            response = requests.post(api_url, json=api_params, timeout=30)
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("status") == "success":
                    logger.info(f"SMS sent via custom API to {to}")
                    return True
                else:
                    logger.error(f"Custom API error: {response_data}")
                    return False
            else:
                logger.error(f"Custom API HTTP error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Custom API error: {str(e)}")
            return False
    
    def _send_via_log(self, to: str, message: str, sender_id: str) -> bool:
        """Log SMS instead of sending (for development)."""
        logger.info(f"[SMS LOG] From: {sender_id}, To: {to}, Message: {message}")
        return True
    
    def get_sms_status(self, message_id: str) -> Dict[str, Any]:
        """Get SMS delivery status (Twilio only)."""
        try:
            if self.provider == "twilio" and self.client:
                message = self.client.messages(message_id).fetch()
                return {
                    "status": message.status,
                    "error_code": message.error_code,
                    "error_message": message.error_message,
                    "date_sent": message.date_sent,
                    "price": message.price,
                    "price_unit": message.price_unit
                }
            else:
                logger.warning("SMS status checking only available for Twilio")
                return {"status": "unknown"}
        except Exception as e:
            logger.error(f"Error getting SMS status: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    def estimate_sms_cost(self, to: str, message: str) -> Dict[str, Any]:
        """Estimate SMS cost."""
        try:
            # Simple estimation based on message length
            message_length = len(message)
            segments = (message_length // 160) + 1
            
            # Very basic cost estimation
            # In production, you'd need actual pricing from your provider
            estimated_cost = segments * 0.01  # $0.01 per segment
            
            return {
                "segments": segments,
                "characters": message_length,
                "estimated_cost": estimated_cost,
                "currency": "USD"
            }
        except Exception as e:
            logger.error(f"Error estimating SMS cost: {str(e)}")
            return {"error": str(e)}

# Global SMS service instance
_sms_service = None

def get_sms_service() -> SMSService:
    """Get or create SMS service instance."""
    global _sms_service
    
    if _sms_service is None:
        _sms_service = SMSService()
    
    return _sms_service

def send_sms(*args, **kwargs) -> bool:
    """Send SMS (convenience function)."""
    service = get_sms_service()
    return service.send_sms(*args, **kwargs)

async def send_sms_async(*args, **kwargs) -> bool:
    """Send SMS asynchronously (convenience function)."""
    service = get_sms_service()
    return await service.send_sms_async(*args, **kwargs)

def send_bulk_sms(*args, **kwargs) -> Dict[str, Any]:
    """Send bulk SMS (convenience function)."""
    service = get_sms_service()
    return service.send_bulk_sms(*args, **kwargs)

def validate_phone_number(phone_number: str) -> str:
    """Validate phone number (convenience function)."""
    service = get_sms_service()
    return service.validate_phone_number(phone_number)

# Common SMS templates
def get_order_confirmation_sms(order_data: Dict[str, Any]) -> str:
    """Get SMS message for order confirmation."""
    order_number = order_data.get("order_number", "")
    total_amount = order_data.get("total_amount", 0)
    currency = order_data.get("currency", settings.DEFAULT_CURRENCY)
    
    return f"Thank you for your order #{order_number}. Your order has been confirmed. Total: {currency} {total_amount:.2f}. We'll notify you when it ships."

def get_shipping_update_sms(order_data: Dict[str, Any]) -> str:
    """Get SMS message for shipping update."""
    order_number = order_data.get("order_number", "")
    tracking_number = order_data.get("tracking_number", "")
    
    return f"Your order #{order_number} has been shipped! Tracking: {tracking_number}. Track at {settings.APP_URL}/track."

def get_delivery_confirmation_sms(order_data: Dict[str, Any]) -> str:
    """Get SMS message for delivery confirmation."""
    order_number = order_data.get("order_number", "")
    
    return f"Your order #{order_number} has been delivered! Hope you enjoy. Please leave a review at {settings.APP_URL}/review."

def get_password_reset_sms(reset_code: str, expiration_minutes: int = 10) -> str:
    """Get SMS message for password reset."""
    return f"{settings.APP_NAME}: Your password reset code is {reset_code}. Valid for {expiration_minutes} minutes."

def get_login_verification_sms(verification_code: str) -> str:
    """Get SMS message for login verification."""
    return f"{settings.APP_NAME}: Your login code is {verification_code}. Don't share this code."

def get_payment_confirmation_sms(order_data: Dict[str, Any]) -> str:
    """Get SMS message for payment confirmation."""
    order_number = order_data.get("order_number", "")
    amount = order_data.get("total_amount", 0)
    currency = order_data.get("currency", settings.DEFAULT_CURRENCY)
    
    return f"Payment confirmed for order #{order_number}. Amount: {currency} {amount:.2f}. Thank you for shopping with {settings.APP_NAME}!"

def get_account_verification_sms(verification_code: str) -> str:
    """Get SMS message for account verification."""
    return f"{settings.APP_NAME}: Your verification code is {verification_code}. Enter this code to verify your account."