import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from typing import List, Optional, Dict, Any, Union, Tuple
from pathlib import Path
import logging
import jinja2
from datetime import datetime
import aiosmtplib
import asyncio
from contextlib import asynccontextmanager
import ssl

from config import settings
from utils.security import generate_secure_token, mask_sensitive_data

logger = logging.getLogger(__name__)

class EmailService:
    """Email service for sending transactional and marketing emails."""
    
    def __init__(self):
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.email_from = settings.EMAIL_FROM
        self.use_ssl = self.smtp_port == 465
        self.use_tls = self.smtp_port == 587
        
        # Setup Jinja2 template environment
        template_path = Path(__file__).parent.parent / "templates" / "emails"
        template_path.mkdir(parents=True, exist_ok=True)
        
        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        
        # Email templates configuration
        self.templates = {
            "welcome": {
                "subject": "Welcome to {app_name}!",
                "template": "welcome.html"
            },
            "password_reset": {
                "subject": "Reset Your Password - {app_name}",
                "template": "password_reset.html"
            },
            "order_confirmation": {
                "subject": "Order Confirmation #{order_number} - {app_name}",
                "template": "order_confirmation.html"
            },
            "order_shipped": {
                "subject": "Your Order #{order_number} Has Shipped!",
                "template": "order_shipped.html"
            },
            "order_delivered": {
                "subject": "Your Order #{order_number} Has Been Delivered",
                "template": "order_delivered.html"
            },
            "payment_receipt": {
                "subject": "Payment Receipt - Order #{order_number}",
                "template": "payment_receipt.html"
            },
            "account_verification": {
                "subject": "Verify Your Email Address - {app_name}",
                "template": "account_verification.html"
            },
            "two_factor_code": {
                "subject": "Your 2FA Code - {app_name}",
                "template": "two_factor_code.html"
            },
            "product_review_request": {
                "subject": "How was your purchase?",
                "template": "product_review_request.html"
            },
            "newsletter": {
                "subject": "{newsletter_title} - {app_name}",
                "template": "newsletter.html"
            },
            "promotion": {
                "subject": "{promotion_title} - {app_name}",
                "template": "promotion.html"
            },
            "account_deactivated": {
                "subject": "Account Deactivated - {app_name}",
                "template": "account_deactivated.html"
            },
            "security_alert": {
                "subject": "Security Alert - {app_name}",
                "template": "security_alert.html"
            }
        }
        
        # Email queue for bulk sending
        self.email_queue = []
        self.queue_processing = False
        
    async def test_connection(self) -> bool:
        """Test SMTP connection."""
        try:
            async with self._get_smtp_connection() as smtp:
                await smtp.ehlo()
                if self.use_tls:
                    await smtp.starttls()
                    await smtp.ehlo()
                await smtp.login(self.smtp_username, self.smtp_password)
                return True
        except Exception as e:
            logger.error(f"SMTP connection test failed: {str(e)}")
            return False
    
    @asynccontextmanager
    async def _get_smtp_connection(self):
        """Get SMTP connection context manager."""
        smtp = aiosmtplib.SMTP(
            hostname=self.smtp_server,
            port=self.smtp_port,
            use_tls=self.use_ssl,
            start_tls=self.use_tls,
            timeout=30
        )
        
        try:
            await smtp.connect()
            if self.use_tls and not self.use_ssl:
                await smtp.starttls()
            await smtp.login(self.smtp_username, self.smtp_password)
            yield smtp
        finally:
            try:
                await smtp.quit()
            except:
                await smtp.close()
    
    def render_template(self, template_name: str, context: Dict[str, Any]) -> Tuple[str, str]:
        """Render email template with context."""
        try:
            template_config = self.templates.get(template_name)
            if not template_config:
                raise ValueError(f"Template '{template_name}' not found")
            
            template = self.template_env.get_template(template_config["template"])
            html_content = template.render(**context)
            
            # Generate text version from HTML (simplified)
            text_content = self._html_to_text(html_content)
            
            return html_content, text_content
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {str(e)}")
            raise
    
    def _html_to_text(self, html_content: str) -> str:
        """Convert HTML to plain text (simplified version)."""
        import re
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html_content)
        
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        
        # Decode HTML entities (basic)
        html_entities = {
            '&nbsp;': ' ', '&lt;': '<', '&gt;': '>', '&amp;': '&',
            '&quot;': '"', '&apos;': "'", '&cent;': '¢', '&pound;': '£',
            '&yen;': '¥', '&euro;': '€', '&copy;': '(c)', '&reg;': '(r)'
        }
        
        for entity, replacement in html_entities.items():
            text = text.replace(entity, replacement)
        
        return text.strip()
    
    async def send_email(
        self,
        to_email: Union[str, List[str]],
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        template_name: Optional[str] = None,
        template_context: Optional[Dict[str, Any]] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """
        Send an email.
        
        Args:
            to_email: Recipient email(s)
            subject: Email subject
            html_content: HTML content (optional if using template)
            text_content: Plain text content (optional)
            template_name: Template name (optional)
            template_context: Template context variables
            from_email: Sender email
            reply_to: Reply-to email
            cc: CC recipients
            bcc: BCC recipients
            attachments: List of attachments
            headers: Custom headers
            priority: Email priority (high/normal/low)
        
        Returns:
            Dictionary with send status and details
        """
        start_time = datetime.utcnow()
        message_id = f"<{datetime.utcnow().timestamp()}.{generate_secure_token(8)}@{settings.APP_NAME.lower()}.com>"
        
        try:
            # Prepare recipients
            if isinstance(to_email, str):
                to_emails = [to_email]
            else:
                to_emails = to_email
            
            # Validate emails
            valid_emails = []
            invalid_emails = []
            
            for email in to_emails:
                if self._validate_email_format(email):
                    valid_emails.append(email)
                else:
                    invalid_emails.append(email)
            
            if not valid_emails:
                return {
                    "success": False,
                    "message": "No valid email addresses provided",
                    "invalid_emails": invalid_emails,
                    "message_id": message_id,
                    "timestamp": start_time.isoformat()
                }
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = from_email or self.email_from
            msg['To'] = ', '.join(valid_emails)
            msg['Subject'] = subject
            msg['Date'] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')
            msg['Message-ID'] = message_id
            msg['X-Priority'] = '1' if priority == 'high' else '3' if priority == 'low' else '2'
            
            if reply_to:
                msg['Reply-To'] = reply_to
            
            if cc:
                msg['Cc'] = ', '.join(cc)
                valid_emails.extend(cc)
            
            if bcc:
                valid_emails.extend(bcc)
            
            if headers:
                for key, value in headers.items():
                    msg[key] = value
            
            # Use template if provided
            if template_name and template_context:
                html_content, text_content = self.render_template(
                    template_name, 
                    template_context
                )
            
            # Add text part
            if text_content:
                text_part = MIMEText(text_content, 'plain', 'utf-8')
                msg.attach(text_part)
            
            # Add HTML part
            if html_content:
                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Add attachments
            if attachments:
                for attachment in attachments:
                    self._add_attachment(msg, attachment)
            
            # Send email
            async with self._get_smtp_connection() as smtp:
                send_result = await smtp.send_message(
                    msg,
                    sender=from_email or self.email_from,
                    recipients=valid_emails
                )
            
            end_time = datetime.utcnow()
            duration_ms = (end_time - start_time).total_seconds() * 1000
            
            result = {
                "success": True,
                "message": "Email sent successfully",
                "message_id": message_id,
                "recipients": {
                    "to": to_emails,
                    "cc": cc or [],
                    "bcc": bcc or []
                },
                "subject": subject,
                "template_used": template_name,
                "timestamp": start_time.isoformat(),
                "duration_ms": duration_ms,
                "invalid_emails": invalid_emails
            }
            
            # Log success (masked emails for privacy)
            masked_emails = [mask_sensitive_data(email) for email in to_emails]
            logger.info(f"Email sent to {masked_emails}: {subject}")
            
            return result
            
        except Exception as e:
            end_time = datetime.utcnow()
            duration_ms = (end_time - start_time).total_seconds() * 1000
            
            logger.error(f"Error sending email: {str(e)}", exc_info=True)
            
            return {
                "success": False,
                "message": f"Failed to send email: {str(e)}",
                "error": str(e),
                "message_id": message_id,
                "timestamp": start_time.isoformat(),
                "duration_ms": duration_ms,
                "recipients": {
                    "to": to_emails if 'to_emails' in locals() else [],
                    "cc": cc or [],
                    "bcc": bcc or []
                }
            }
    
    def _validate_email_format(self, email: str) -> bool:
        """Validate email format."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict[str, Any]) -> None:
        """Add attachment to email."""
        try:
            content = attachment.get('content')
            filename = attachment.get('filename', 'attachment')
            content_type = attachment.get('content_type', 'application/octet-stream')
            
            if isinstance(content, bytes):
                file_data = content
            elif isinstance(content, str):
                file_data = content.encode('utf-8')
            elif hasattr(content, 'read'):
                file_data = content.read()
            else:
                raise ValueError("Invalid attachment content")
            
            # Create attachment
            if content_type.startswith('image/'):
                attachment_part = MIMEImage(file_data)
            else:
                attachment_part = MIMEApplication(file_data)
            
            attachment_part.add_header(
                'Content-Disposition',
                'attachment',
                filename=filename
            )
            attachment_part.add_header('Content-Type', content_type)
            
            msg.attach(attachment_part)
            
        except Exception as e:
            logger.error(f"Error adding attachment: {str(e)}")
            raise
    
    async def send_bulk_emails(
        self,
        emails: List[Dict[str, Any]],
        batch_size: int = 50,
        delay_between_batches: float = 1.0
    ) -> Dict[str, Any]:
        """Send emails in bulk with rate limiting."""
        start_time = datetime.utcnow()
        total_emails = len(emails)
        successful = 0
        failed = 0
        results = []
        
        logger.info(f"Starting bulk email send for {total_emails} emails")
        
        # Process in batches
        for i in range(0, total_emails, batch_size):
            batch = emails[i:i + batch_size]
            batch_number = (i // batch_size) + 1
            
            logger.info(f"Processing batch {batch_number} ({len(batch)} emails)")
            
            # Send emails in current batch concurrently
            tasks = []
            for email_data in batch:
                task = self.send_email(**email_data)
                tasks.append(task)
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for j, result in enumerate(batch_results):
                email_index = i + j
                if isinstance(result, Exception):
                    failed += 1
                    results.append({
                        "index": email_index,
                        "success": False,
                        "error": str(result)
                    })
                    logger.error(f"Failed to send email {email_index}: {str(result)}")
                else:
                    if result.get("success"):
                        successful += 1
                    else:
                        failed += 1
                    results.append(result)
            
            # Delay between batches to avoid rate limiting
            if i + batch_size < total_emails:
                await asyncio.sleep(delay_between_batches)
        
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        return {
            "total": total_emails,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total_emails * 100) if total_emails > 0 else 0,
            "duration_ms": duration_ms,
            "results": results,
            "timestamp": start_time.isoformat()
        }
    
    # Predefined email functions
    async def send_welcome_email(self, user_email: str, user_name: str) -> Dict[str, Any]:
        """Send welcome email to new user."""
        context = {
            "app_name": settings.APP_NAME,
            "user_name": user_name,
            "user_email": user_email,
            "current_year": datetime.utcnow().year,
            "support_email": settings.EMAIL_FROM
        }
        
        subject = self.templates["welcome"]["subject"].format(app_name=settings.APP_NAME)
        
        return await self.send_email(
            to_email=user_email,
            subject=subject,
            template_name="welcome",
            template_context=context
        )
    
    async def send_password_reset_email(self, user_email: str, reset_token: str) -> Dict[str, Any]:
        """Send password reset email."""
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        
        context = {
            "app_name": settings.APP_NAME,
            "reset_url": reset_url,
            "reset_token": reset_token,
            "expiry_hours": 24,
            "current_year": datetime.utcnow().year,
            "support_email": settings.EMAIL_FROM
        }
        
        subject = self.templates["password_reset"]["subject"].format(app_name=settings.APP_NAME)
        
        return await self.send_email(
            to_email=user_email,
            subject=subject,
            template_name="password_reset",
            template_context=context
        )
    
    async def send_verification_email(self, user_email: str, verification_token: str) -> Dict[str, Any]:
        """Send email verification email."""
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        
        context = {
            "app_name": settings.APP_NAME,
            "verification_url": verification_url,
            "verification_token": verification_token,
            "expiry_hours": 24,
            "current_year": datetime.utcnow().year,
            "support_email": settings.EMAIL_FROM
        }
        
        subject = self.templates["account_verification"]["subject"].format(app_name=settings.APP_NAME)
        
        return await self.send_email(
            to_email=user_email,
            subject=subject,
            template_name="account_verification",
            template_context=context
        )
    
    async def send_order_confirmation_email(
        self, 
        user_email: str, 
        order_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send order confirmation email."""
        context = {
            "app_name": settings.APP_NAME,
            "order_number": order_data.get("order_number"),
            "order_date": order_data.get("order_date"),
            "total_amount": order_data.get("total_amount"),
            "items": order_data.get("items", []),
            "shipping_address": order_data.get("shipping_address"),
            "billing_address": order_data.get("billing_address"),
            "estimated_delivery": order_data.get("estimated_delivery"),
            "tracking_number": order_data.get("tracking_number"),
            "tracking_url": order_data.get("tracking_url"),
            "current_year": datetime.utcnow().year,
            "support_email": settings.EMAIL_FROM
        }
        
        subject = self.templates["order_confirmation"]["subject"].format(
            app_name=settings.APP_NAME,
            order_number=order_data.get("order_number")
        )
        
        return await self.send_email(
            to_email=user_email,
            subject=subject,
            template_name="order_confirmation",
            template_context=context
        )
    
    async def send_payment_receipt_email(
        self,
        user_email: str,
        payment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send payment receipt email."""
        context = {
            "app_name": settings.APP_NAME,
            "order_number": payment_data.get("order_number"),
            "payment_date": payment_data.get("payment_date"),
            "amount": payment_data.get("amount"),
            "currency": payment_data.get("currency", "USD"),
            "payment_method": payment_data.get("payment_method"),
            "transaction_id": payment_data.get("transaction_id"),
            "items": payment_data.get("items", []),
            "current_year": datetime.utcnow().year,
            "support_email": settings.EMAIL_FROM
        }
        
        subject = self.templates["payment_receipt"]["subject"].format(
            order_number=payment_data.get("order_number")
        )
        
        return await self.send_email(
            to_email=user_email,
            subject=subject,
            template_name="payment_receipt",
            template_context=context
        )
    
    async def send_two_factor_email(self, user_email: str, code: str) -> Dict[str, Any]:
        """Send 2FA code email."""
        context = {
            "app_name": settings.APP_NAME,
            "code": code,
            "expiry_minutes": 10,
            "current_year": datetime.utcnow().year,
            "support_email": settings.EMAIL_FROM
        }
        
        subject = self.templates["two_factor_code"]["subject"].format(app_name=settings.APP_NAME)
        
        return await self.send_email(
            to_email=user_email,
            subject=subject,
            template_name="two_factor_code",
            template_context=context
        )
    
    async def send_product_review_request(
        self,
        user_email: str,
        user_name: str,
        product_data: Dict[str, Any],
        order_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send product review request email."""
        review_url = f"{settings.FRONTEND_URL}/products/{product_data.get('id')}/review"
        
        context = {
            "app_name": settings.APP_NAME,
            "user_name": user_name,
            "product_name": product_data.get("name"),
            "product_image": product_data.get("image"),
            "order_number": order_data.get("order_number"),
            "review_url": review_url,
            "current_year": datetime.utcnow().year,
            "support_email": settings.EMAIL_FROM
        }
        
        subject = self.templates["product_review_request"]["subject"]
        
        return await self.send_email(
            to_email=user_email,
            subject=subject,
            template_name="product_review_request",
            template_context=context
        )
    
    async def send_security_alert(
        self,
        user_email: str,
        alert_type: str,
        details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send security alert email."""
        context = {
            "app_name": settings.APP_NAME,
            "alert_type": alert_type,
            "alert_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "ip_address": details.get("ip_address"),
            "device": details.get("device"),
            "location": details.get("location"),
            "action": details.get("action"),
            "current_year": datetime.utcnow().year,
            "support_email": settings.EMAIL_FROM,
            "security_url": f"{settings.FRONTEND_URL}/security"
        }
        
        subject = self.templates["security_alert"]["subject"].format(app_name=settings.APP_NAME)
        
        return await self.send_email(
            to_email=user_email,
            subject=subject,
            template_name="security_alert",
            template_context=context,
            priority="high"
        )
    
    # Queue management
    def add_to_queue(self, email_data: Dict[str, Any]) -> None:
        """Add email to queue for later sending."""
        self.email_queue.append({
            **email_data,
            "queued_at": datetime.utcnow().isoformat()
        })
        logger.info(f"Email added to queue. Queue size: {len(self.email_queue)}")
    
    async def process_queue(self, batch_size: int = 20) -> Dict[str, Any]:
        """Process queued emails."""
        if self.queue_processing:
            return {"status": "already_processing", "message": "Queue is already being processed"}
        
        self.queue_processing = True
        start_time = datetime.utcnow()
        
        try:
            # Take emails from queue
            emails_to_send = self.email_queue[:batch_size]
            remaining_queue = self.email_queue[batch_size:]
            
            if not emails_to_send:
                return {
                    "status": "empty",
                    "message": "No emails in queue",
                    "processed": 0,
                    "duration_ms": 0
                }
            
            logger.info(f"Processing {len(emails_to_send)} emails from queue")
            
            # Send emails
            results = await self.send_bulk_emails(emails_to_send)
            
            # Update queue
            self.email_queue = remaining_queue
            
            end_time = datetime.utcnow()
            duration_ms = (end_time - start_time).total_seconds() * 1000
            
            return {
                "status": "completed",
                "processed": len(emails_to_send),
                "results": results,
                "queue_remaining": len(self.email_queue),
                "duration_ms": duration_ms
            }
            
        finally:
            self.queue_processing = False
    
    # Statistics and monitoring
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get email queue statistics."""
        return {
            "queue_size": len(self.email_queue),
            "is_processing": self.queue_processing,
            "oldest_email": self.email_queue[0].get("queued_at") if self.email_queue else None,
            "newest_email": self.email_queue[-1].get("queued_at") if self.email_queue else None
        }
    
    def clear_queue(self) -> Dict[str, Any]:
        """Clear email queue."""
        cleared_count = len(self.email_queue)
        self.email_queue.clear()
        
        return {
            "cleared_count": cleared_count,
            "message": f"Cleared {cleared_count} emails from queue"
        }

# Global email service instance
email_service = EmailService()

# Utility functions for backward compatibility
async def send_email(**kwargs) -> Dict[str, Any]:
    """Send email (compatibility function)."""
    return await email_service.send_email(**kwargs)

async def send_welcome_email(user_email: str, user_name: str) -> Dict[str, Any]:
    """Send welcome email (compatibility function)."""
    return await email_service.send_welcome_email(user_email, user_name)

async def send_password_reset_email(user_email: str, reset_token: str) -> Dict[str, Any]:
    """Send password reset email (compatibility function)."""
    return await email_service.send_password_reset_email(user_email, reset_token)

async def send_verification_email(user_email: str, verification_token: str) -> Dict[str, Any]:
    """Send verification email (compatibility function)."""
    return await email_service.send_verification_email(user_email, verification_token)