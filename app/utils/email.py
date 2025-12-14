import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Dict, Any
from pathlib import Path
import jinja2
from datetime import datetime
import aiosmtplib
import asyncio
from contextlib import asynccontextmanager

from config import settings

logger = logging.getLogger(__name__)

class EmailService:
    """Email service for sending notifications."""
    
    def __init__(self):
        self.smtp_server = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT or 587
        self.smtp_username = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.EMAILS_FROM_EMAIL
        self.from_name = settings.EMAILS_FROM_NAME
        self.use_ssl = settings.SMTP_SSL
        self.use_tls = settings.SMTP_TLS
        
        # Initialize Jinja2 template engine
        template_path = Path(settings.EMAIL_TEMPLATES_DIR)
        template_path.mkdir(parents=True, exist_ok=True)
        
        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=True
        )
        
        logger.info(f"Email service initialized with server: {self.smtp_server}:{self.smtp_port}")
    
    def _get_smtp_connection(self):
        """Get SMTP connection."""
        if not self.smtp_server:
            logger.warning("SMTP server not configured")
            return None
        
        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            
            if self.use_tls:
                server.starttls()
            
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)
            
            return server
        except Exception as e:
            logger.error(f"Error connecting to SMTP server: {str(e)}")
            return None
    
    async def _get_async_smtp_connection(self):
        """Get async SMTP connection."""
        if not self.smtp_server:
            logger.warning("SMTP server not configured")
            return None
        
        try:
            if self.use_ssl:
                server = aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    use_tls=self.use_tls
                )
            else:
                server = aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    start_tls=self.use_tls
                )
            
            await server.connect()
            
            if self.smtp_username and self.smtp_password:
                await server.login(self.smtp_username, self.smtp_password)
            
            return server
        except Exception as e:
            logger.error(f"Error connecting to async SMTP server: {str(e)}")
            return None
    
    def _prepare_message(
        self,
        to: List[str],
        subject: str,
        body: str,
        body_type: str = "html",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> MIMEMultipart:
        """Prepare email message."""
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{self.from_name} <{self.from_email}>"
        msg['To'] = ', '.join(to)
        msg['Subject'] = subject
        msg['Date'] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        if cc:
            msg['Cc'] = ', '.join(cc)
        if bcc:
            msg['Bcc'] = ', '.join(bcc)
        if reply_to:
            msg['Reply-To'] = reply_to
        else:
            msg['Reply-To'] = settings.SUPPORT_EMAIL
        
        # Add headers
        if headers:
            for key, value in headers.items():
                msg[key] = value
        
        # Add body
        if body_type == "html":
            part = MIMEText(body, 'html')
        else:
            part = MIMEText(body, 'plain')
        msg.attach(part)
        
        # Add attachments
        if attachments:
            for attachment in attachments:
                self._add_attachment(msg, attachment)
        
        return msg
    
    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict[str, Any]) -> None:
        """Add attachment to email."""
        try:
            filename = attachment.get('filename')
            content = attachment.get('content')
            content_type = attachment.get('content_type', 'application/octet-stream')
            
            if not filename or not content:
                logger.warning("Attachment missing filename or content")
                return
            
            part = MIMEBase(*content_type.split('/', 1))
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{filename}"'
            )
            msg.attach(part)
        except Exception as e:
            logger.error(f"Error adding attachment: {str(e)}")
    
    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render email template."""
        try:
            # Add default context
            default_context = {
                "app_name": settings.APP_NAME,
                "app_url": settings.APP_URL,
                "support_email": settings.SUPPORT_EMAIL,
                "year": datetime.now().year,
                "current_date": datetime.now().strftime(settings.DATE_FORMAT),
                "environment": settings.ENVIRONMENT
            }
            context = {**default_context, **context}
            
            template = self.template_env.get_template(template_name)
            return template.render(**context)
        except jinja2.TemplateNotFound:
            logger.warning(f"Template {template_name} not found")
            return ""
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {str(e)}")
            return ""
    
    def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        body_type: str = "html",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send email synchronously."""
        try:
            # If SMTP not configured, log and return success in development
            if not self.smtp_server and settings.DEBUG:
                logger.info(f"[DEV MODE] Email would be sent to {to}: {subject}")
                logger.info(f"[DEV MODE] Body preview: {body[:200]}...")
                return True
            
            # Render template if provided
            if template_id and template_data:
                body = self._render_template(f"{template_id}.html", template_data)
                if not body and template_data.get('fallback_text'):
                    body = template_data['fallback_text']
                    body_type = "plain"
            
            # Prepare message
            msg = self._prepare_message(
                to=to,
                subject=subject,
                body=body,
                body_type=body_type,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
                attachments=attachments,
                headers=headers
            )
            
            # Get SMTP connection
            server = self._get_smtp_connection()
            if not server:
                logger.error("Failed to establish SMTP connection")
                return False
            
            # Send message
            recipients = to.copy()
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email sent to {', '.join(to)} with subject: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False
    
    async def send_email_async(
        self,
        to: List[str],
        subject: str,
        body: str,
        body_type: str = "html",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send email asynchronously."""
        try:
            # If SMTP not configured, log and return success in development
            if not self.smtp_server and settings.DEBUG:
                logger.info(f"[DEV MODE] Async email would be sent to {to}: {subject}")
                return True
            
            # Render template if provided
            if template_id and template_data:
                body = self._render_template(f"{template_id}.html", template_data)
                if not body and template_data.get('fallback_text'):
                    body = template_data['fallback_text']
                    body_type = "plain"
            
            # Prepare message
            msg = self._prepare_message(
                to=to,
                subject=subject,
                body=body,
                body_type=body_type,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
                attachments=attachments,
                headers=headers
            )
            
            # Get async SMTP connection
            server = await self._get_async_smtp_connection()
            if not server:
                logger.error("Failed to establish async SMTP connection")
                return False
            
            # Send message
            recipients = to.copy()
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            await server.send_message(
                msg,
                sender=self.from_email,
                recipients=recipients
            )
            await server.quit()
            
            logger.info(f"Email sent asynchronously to {', '.join(to)} with subject: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending async email: {str(e)}")
            return False
    
    def send_bulk_emails(
        self,
        emails: List[Dict[str, Any]],
        batch_size: int = 50
    ) -> Dict[str, Any]:
        """Send bulk emails."""
        results = {
            "total": len(emails),
            "successful": 0,
            "failed": 0,
            "failed_details": []
        }
        
        # If SMTP not configured, simulate success in development
        if not self.smtp_server and settings.DEBUG:
            logger.info(f"[DEV MODE] Would send {len(emails)} bulk emails")
            results["successful"] = len(emails)
            return results
        
        for i in range(0, len(emails), batch_size):
            batch = emails[i:i + batch_size]
            for email_data in batch:
                try:
                    success = self.send_email(**email_data)
                    if success:
                        results["successful"] += 1
                    else:
                        results["failed"] += 1
                        results["failed_details"].append({
                            "to": email_data.get("to"),
                            "subject": email_data.get("subject"),
                            "error": "Failed to send"
                        })
                except Exception as e:
                    results["failed"] += 1
                    results["failed_details"].append({
                        "to": email_data.get("to"),
                        "subject": email_data.get("subject"),
                        "error": str(e)
                    })
            
            # Small delay between batches to avoid rate limiting
            if i + batch_size < len(emails):
                import time
                time.sleep(1)
        
        logger.info(f"Bulk email sending completed: {results['successful']} successful, {results['failed']} failed")
        return results

# Global email service instance
_email_service = None

def get_email_service() -> EmailService:
    """Get or create email service instance."""
    global _email_service
    
    if _email_service is None:
        _email_service = EmailService()
    
    return _email_service

def send_email(*args, **kwargs) -> bool:
    """Send email (convenience function)."""
    service = get_email_service()
    return service.send_email(*args, **kwargs)

async def send_email_async(*args, **kwargs) -> bool:
    """Send email asynchronously (convenience function)."""
    service = get_email_service()
    return await service.send_email_async(*args, **kwargs)

def send_bulk_emails(*args, **kwargs) -> Dict[str, Any]:
    """Send bulk emails (convenience function)."""
    service = get_email_service()
    return service.send_bulk_emails(*args, **kwargs)

# Template helper functions
def get_email_template(template_name: str, context: Dict[str, Any]) -> str:
    """Get rendered email template."""
    service = get_email_service()
    return service._render_template(f"{template_name}.html", context)

# Common email templates context
def get_order_confirmation_context(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get context for order confirmation email."""
    return {
        "order": order_data,
        "customer_name": order_data.get("customer_name", "Customer"),
        "order_number": order_data.get("order_number", ""),
        "order_date": order_data.get("order_date", datetime.utcnow().strftime(settings.DATE_FORMAT)),
        "total_amount": order_data.get("total_amount", 0),
        "currency": order_data.get("currency", settings.DEFAULT_CURRENCY),
        "items": order_data.get("items", []),
        "shipping_address": order_data.get("shipping_address", {}),
        "billing_address": order_data.get("billing_address", {}),
        "shipping_cost": order_data.get("shipping_cost", settings.DEFAULT_SHIPPING_COST),
        "free_shipping_threshold": settings.FREE_SHIPPING_THRESHOLD
    }

def get_password_reset_context(user_data: Dict[str, Any], reset_link: str) -> Dict[str, Any]:
    """Get context for password reset email."""
    return {
        "user_name": user_data.get("name", "User"),
        "user_email": user_data.get("email", ""),
        "reset_link": reset_link,
        "expiration_hours": 24
    }

def get_welcome_email_context(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get context for welcome email."""
    return {
        "user_name": user_data.get("name", "User"),
        "user_email": user_data.get("email", ""),
        "dashboard_url": f"{settings.APP_URL}/dashboard",
        "getting_started_guide": f"{settings.APP_URL}/help/getting-started"
    }

def get_account_verification_context(user_data: Dict[str, Any], verification_link: str) -> Dict[str, Any]:
    """Get context for account verification email."""
    return {
        "user_name": user_data.get("name", "User"),
        "verification_link": verification_link,
        "expiration_hours": 48
    }

def get_order_shipped_context(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get context for order shipped email."""
    return {
        "order": order_data,
        "customer_name": order_data.get("customer_name", "Customer"),
        "order_number": order_data.get("order_number", ""),
        "tracking_number": order_data.get("tracking_number", ""),
        "tracking_url": order_data.get("tracking_url", ""),
        "estimated_delivery": order_data.get("estimated_delivery", ""),
        "shipping_carrier": order_data.get("shipping_carrier", "")
    }

def get_review_reminder_context(order_data: Dict[str, Any], product_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get context for review reminder email."""
    return {
        "order": order_data,
        "customer_name": order_data.get("customer_name", "Customer"),
        "order_number": order_data.get("order_number", ""),
        "product_name": product_data.get("name", "Product"),
        "product_image": product_data.get("image_url", ""),
        "review_link": f"{settings.APP_URL}/products/{product_data.get('id')}/review"
    }