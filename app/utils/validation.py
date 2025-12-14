import re
import uuid
from typing import Optional, Any
from datetime import datetime
import email_validator
from email_validator import validate_email, EmailNotValidError

def validate_uuid(uuid_str: str) -> bool:
    """Validate if string is a valid UUID."""
    try:
        uuid.UUID(uuid_str)
        return True
    except (ValueError, AttributeError):
        return False

def validate_email_address(email: str) -> bool:
    """Validate email address format."""
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False

def validate_phone_number(phone: str) -> bool:
    """Validate phone number format (E.164)."""
    pattern = r'^\+?[1-9]\d{1,14}$'
    return bool(re.match(pattern, phone))

def validate_password_strength(password: str) -> bool:
    """Validate password strength."""
    if len(password) < 8:
        return False
    
    # Check for at least one uppercase letter
    if not re.search(r'[A-Z]', password):
        return False
    
    # Check for at least one lowercase letter
    if not re.search(r'[a-z]', password):
        return False
    
    # Check for at least one digit
    if not re.search(r'\d', password):
        return False
    
    # Check for at least one special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    
    return True

def validate_rating(rating: float, min_value: float = 0, max_value: float = 5) -> bool:
    """Validate rating value."""
    return min_value <= rating <= max_value

def validate_date_string(date_str: str, format: str = "%Y-%m-%d") -> bool:
    """Validate date string format."""
    try:
        datetime.strptime(date_str, format)
        return True
    except ValueError:
        return False

def sanitize_input(input_str: str, max_length: int = 500) -> str:
    """Sanitize user input to prevent XSS and injection."""
    if not input_str:
        return ""
    
    # Trim to max length
    input_str = input_str[:max_length]
    
    # Remove potentially dangerous characters
    # This is a basic sanitization - use a proper HTML sanitizer for production
    dangerous_patterns = [
        r'<script.*?>.*?</script>',
        r'javascript:',
        r'on\w+=',
        r'data:',
        r'vbscript:'
    ]
    
    for pattern in dangerous_patterns:
        input_str = re.sub(pattern, '', input_str, flags=re.IGNORECASE)
    
    # Escape HTML entities
    input_str = input_str.replace('&', '&amp;')
    input_str = input_str.replace('<', '&lt;')
    input_str = input_str.replace('>', '&gt;')
    input_str = input_str.replace('"', '&quot;')
    input_str = input_str.replace("'", '&#x27;')
    input_str = input_str.replace('/', '&#x2F;')
    
    return input_str.strip()

def validate_url(url: str) -> bool:
    """Validate URL format."""
    pattern = r'^(https?|ftp)://[^\s/$.?#].[^\s]*$'
    return bool(re.match(pattern, url))

def validate_credit_card(card_number: str) -> bool:
    """Validate credit card number using Luhn algorithm."""
    # Remove non-digit characters
    card_number = re.sub(r'\D', '', card_number)
    
    if not card_number:
        return False
    
    # Check length
    if len(card_number) < 13 or len(card_number) > 19:
        return False
    
    # Luhn algorithm
    total = 0
    reverse_digits = card_number[::-1]
    
    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    
    return total % 10 == 0

def validate_postal_code(postal_code: str, country_code: str = "US") -> bool:
    """Validate postal code based on country."""
    patterns = {
        "US": r'^\d{5}(-\d{4})?$',
        "CA": r'^[A-Z]\d[A-Z] \d[A-Z]\d$',
        "UK": r'^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$',
        "AU": r'^\d{4}$',
        "DE": r'^\d{5}$',
        "FR": r'^\d{5}$',
        "JP": r'^\d{3}-\d{4}$',
        "IN": r'^\d{6}$',
    }
    
    pattern = patterns.get(country_code.upper(), r'^\d{5,10}$')
    return bool(re.match(pattern, postal_code.upper()))

def validate_currency_code(currency_code: str) -> bool:
    """Validate ISO 4217 currency code."""
    pattern = r'^[A-Z]{3}$'
    return bool(re.match(pattern, currency_code))

def validate_language_code(language_code: str) -> bool:
    """Validate ISO 639-1 language code."""
    pattern = r'^[a-z]{2}(-[A-Z]{2})?$'
    return bool(re.match(pattern, language_code))

def validate_hex_color(color: str) -> bool:
    """Validate hex color code."""
    pattern = r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$'
    return bool(re.match(pattern, color))

def validate_slug(slug: str) -> bool:
    """Validate URL slug."""
    pattern = r'^[a-z0-9]+(?:-[a-z0-9]+)*$'
    return bool(re.match(pattern, slug))