from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging
import secrets
import pyotp

from model.models import User, UserSession, PasswordResetToken
from schemas import (
    UserCreate, UserResponse, Token, TokenData, PasswordChange,
    PasswordResetRequest, PasswordResetConfirm, TwoFactorSetup, TwoFactorVerify
)
from config import settings
from utils.email import send_password_reset_email, send_verification_email
from utils.security import generate_secure_token, validate_password_strength
from services.blockchain_service import create_blockchain_transaction

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Password hashing
def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

# JWT token functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != token_type:
            return None
        return payload
    except JWTError:
        return None

def refresh_access_token(refresh_token: str) -> Optional[str]:
    """Refresh an access token using a refresh token."""
    payload = verify_token(refresh_token, "refresh")
    if not payload:
        return None
    
    # Create new access token
    access_token = create_access_token(
        data={
            "sub": payload.get("sub"),
            "user_id": payload.get("user_id"),
            "user_type": payload.get("user_type")
        }
    )
    return access_token

# User authentication
def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Authenticate a user with email and password."""
    try:
        user = db.query(User).filter(
            and_(
                User.email == email,
                User.is_active == True
            )
        ).first()
        
        if not user:
            return None
        
        if not verify_password(password, user.password_hash):
            return None
        
        # Check if 2FA is required
        if user.two_factor_enabled:
            # Return special flag indicating 2FA is required
            user.requires_2fa = True
            return user
        
        return user
    except Exception as e:
        logger.error(f"Error authenticating user: {str(e)}")
        return None

def authenticate_user_with_2fa(db: Session, user_id: str, token: str) -> Optional[User]:
    """Authenticate a user with 2FA token."""
    try:
        user = db.query(User).filter(
            and_(
                User.id == user_id,
                User.is_active == True,
                User.two_factor_enabled == True
            )
        ).first()
        
        if not user:
            return None
        
        # Verify 2FA token
        if not verify_two_factor_token(user.two_factor_secret, token):
            return None
        
        return user
    except Exception as e:
        logger.error(f"Error authenticating user with 2FA: {str(e)}")
        return None

def create_user(db: Session, user_data: UserCreate) -> User:
    """Create a new user."""
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(
            or_(
                User.email == user_data.email,
                User.phone_number == user_data.phone_number
            )
        ).first()
        
        if existing_user:
            if existing_user.email == user_data.email:
                raise ValueError("Email already registered")
            else:
                raise ValueError("Phone number already registered")
        
        # Validate password strength
        if not validate_password_strength(user_data.password):
            raise ValueError("Password does not meet security requirements")
        
        # Hash password
        hashed_password = hash_password(user_data.password)
        
        # Create user
        user = User(
            name=user_data.name,
            email=user_data.email,
            phone_number=user_data.phone_number,
            profile_picture=user_data.profile_picture,
            type=user_data.type,
            password_hash=hashed_password,
            locale=user_data.locale,
            timezone=user_data.timezone,
            is_active=True,
            is_verified=False
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="user_register",
            user_id=user.id,
            data={
                "user_id": user.id,
                "email": user.email,
                "user_type": user.type.value
            }
        )
        
        # Send verification email
        send_verification_email(user.email, user.id)
        
        return user
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating user: {str(e)}")
        raise

def get_current_user(db: Session, token: str) -> Optional[User]:
    """Get current user from JWT token."""
    try:
        payload = verify_token(token)
        if not payload:
            return None
        
        user_id = payload.get("user_id")
        if not user_id:
            return None
        
        user = db.query(User).filter(
            and_(
                User.id == user_id,
                User.is_active == True
            )
        ).first()
        
        return user
    except Exception as e:
        logger.error(f"Error getting current user: {str(e)}")
        return None

def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """Get user by ID."""
    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}")
        return None

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get user by email."""
    try:
        return db.query(User).filter(User.email == email).first()
    except Exception as e:
        logger.error(f"Error getting user by email: {str(e)}")
        return None

def update_user(db: Session, user_id: str, user_data: Dict[str, Any]) -> Optional[User]:
    """Update user information."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        # Update fields
        for field, value in user_data.items():
            if value is not None and hasattr(user, field):
                setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="user_update",
            user_id=user_id,
            data={"updates": user_data}
        )
        
        return user
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user: {str(e)}")
        return None

def update_user_last_login(db: Session, user_id: str) -> None:
    """Update user's last login timestamp."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.last_login_at = datetime.utcnow()
            user.login_count = (user.login_count or 0) + 1
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating last login: {str(e)}")

def change_password(db: Session, user_id: str, password_data: PasswordChange) -> bool:
    """Change user password."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        # Verify current password
        if not verify_password(password_data.current_password, user.password_hash):
            return False
        
        # Validate new password strength
        if not validate_password_strength(password_data.new_password):
            return False
        
        # Hash new password
        user.password_hash = hash_password(password_data.new_password)
        user.updated_at = datetime.utcnow()
        
        # Invalidate all existing sessions
        db.query(UserSession).filter(UserSession.user_id == user_id).update(
            {"is_active": False, "logged_out_at": datetime.utcnow()}
        )
        
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="password_change",
            user_id=user_id,
            data={"changed_at": datetime.utcnow().isoformat()}
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error changing password: {str(e)}")
        return False

def request_password_reset(db: Session, email: str) -> bool:
    """Request password reset."""
    try:
        user = db.query(User).filter(
            and_(
                User.email == email,
                User.is_active == True
            )
        ).first()
        
        if not user:
            # Return True even if user doesn't exist for security
            return True
        
        # Generate reset token
        reset_token = generate_secure_token()
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Create or update reset token
        existing_token = db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id
        ).first()
        
        if existing_token:
            existing_token.token = reset_token
            existing_token.expires_at = expires_at
            existing_token.used = False
        else:
            reset_token_obj = PasswordResetToken(
                user_id=user.id,
                token=reset_token,
                expires_at=expires_at
            )
            db.add(reset_token_obj)
        
        db.commit()
        
        # Send password reset email
        send_password_reset_email(user.email, reset_token)
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error requesting password reset: {str(e)}")
        return False

def reset_password(db: Session, token: str, password_data: PasswordResetConfirm) -> bool:
    """Reset password using token."""
    try:
        # Find valid reset token
        reset_token = db.query(PasswordResetToken).filter(
            and_(
                PasswordResetToken.token == token,
                PasswordResetToken.expires_at > datetime.utcnow(),
                PasswordResetToken.used == False
            )
        ).first()
        
        if not reset_token:
            return False
        
        # Validate new password strength
        if not validate_password_strength(password_data.new_password):
            return False
        
        # Update user password
        user = db.query(User).filter(User.id == reset_token.user_id).first()
        if not user:
            return False
        
        user.password_hash = hash_password(password_data.new_password)
        user.updated_at = datetime.utcnow()
        
        # Mark token as used
        reset_token.used = True
        reset_token.used_at = datetime.utcnow()
        
        # Invalidate all existing sessions
        db.query(UserSession).filter(UserSession.user_id == user.id).update(
            {"is_active": False, "logged_out_at": datetime.utcnow()}
        )
        
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="password_reset",
            user_id=user.id,
            data={"reset_at": datetime.utcnow().isoformat()}
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error resetting password: {str(e)}")
        return False

# Two-factor authentication
def setup_two_factor(db: Session, user_id: str) -> TwoFactorSetup:
    """Setup two-factor authentication for user."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        
        # Generate secret
        secret = pyotp.random_base32()
        
        # Store secret (temporarily, will be saved after verification)
        user.two_factor_secret = secret
        db.commit()
        
        # Generate QR code URL
        issuer = settings.APP_NAME
        account_name = user.email
        totp = pyotp.TOTP(secret)
        qr_code_url = totp.provisioning_uri(name=account_name, issuer_name=issuer)
        
        return TwoFactorSetup(
            secret=secret,
            qr_code_url=qr_code_url
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting up 2FA: {str(e)}")
        raise

def verify_two_factor_token(secret: str, token: str) -> bool:
    """Verify a 2FA token."""
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(token)
    except Exception as e:
        logger.error(f"Error verifying 2FA token: {str(e)}")
        return False

def enable_two_factor(db: Session, user_id: str, token: str) -> bool:
    """Enable 2FA after verification."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.two_factor_secret:
            return False
        
        # Verify token
        if not verify_two_factor_token(user.two_factor_secret, token):
            return False
        
        # Enable 2FA
        user.two_factor_enabled = True
        user.updated_at = datetime.utcnow()
        
        # Generate backup codes
        backup_codes = [generate_secure_token(8) for _ in range(10)]
        user.two_factor_backup_codes = backup_codes
        
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="2fa_enable",
            user_id=user_id,
            data={"enabled_at": datetime.utcnow().isoformat()}
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error enabling 2FA: {str(e)}")
        return False

def disable_two_factor(db: Session, user_id: str) -> bool:
    """Disable 2FA for user."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        # Disable 2FA
        user.two_factor_enabled = False
        user.two_factor_secret = None
        user.two_factor_backup_codes = None
        user.updated_at = datetime.utcnow()
        
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="2fa_disable",
            user_id=user_id,
            data={"disabled_at": datetime.utcnow().isoformat()}
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error disabling 2FA: {str(e)}")
        return False

def verify_backup_code(db: Session, user_id: str, backup_code: str) -> bool:
    """Verify a 2FA backup code."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.two_factor_backup_codes:
            return False
        
        # Check if backup code is valid
        if backup_code not in user.two_factor_backup_codes:
            return False
        
        # Remove used backup code
        user.two_factor_backup_codes.remove(backup_code)
        db.commit()
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error verifying backup code: {str(e)}")
        return False

# Session management
def create_user_session(db: Session, user_id: str, ip_address: str, user_agent: str) -> UserSession:
    """Create a new user session."""
    try:
        # Invalidate old sessions if needed
        if settings.MAX_CONCURRENT_SESSIONS > 0:
            sessions = db.query(UserSession).filter(
                and_(
                    UserSession.user_id == user_id,
                    UserSession.is_active == True
                )
            ).order_by(UserSession.created_at.desc()).all()
            
            if len(sessions) >= settings.MAX_CONCURRENT_SESSIONS:
                for session in sessions[settings.MAX_CONCURRENT_SESSIONS - 1:]:
                    session.is_active = False
                    session.logged_out_at = datetime.utcnow()
        
        # Create new session
        session = UserSession(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            is_active=True
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        
        return session
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating user session: {str(e)}")
        raise

def invalidate_session(db: Session, session_id: str, user_id: str) -> bool:
    """Invalidate a user session."""
    try:
        session = db.query(UserSession).filter(
            and_(
                UserSession.id == session_id,
                UserSession.user_id == user_id,
                UserSession.is_active == True
            )
        ).first()
        
        if not session:
            return False
        
        session.is_active = False
        session.logged_out_at = datetime.utcnow()
        db.commit()
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error invalidating session: {str(e)}")
        return False

def invalidate_all_sessions(db: Session, user_id: str) -> int:
    """Invalidate all sessions for a user."""
    try:
        result = db.query(UserSession).filter(
            and_(
                UserSession.user_id == user_id,
                UserSession.is_active == True
            )
        ).update({
            "is_active": False,
            "logged_out_at": datetime.utcnow()
        })
        
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        logger.error(f"Error invalidating all sessions: {str(e)}")
        return 0

# User verification
def verify_user_email(db: Session, user_id: str) -> bool:
    """Verify user email."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.is_verified = True
        user.verified_at = datetime.utcnow()
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="user_verify",
            user_id=user_id,
            data={"verified_at": datetime.utcnow().isoformat()}
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error verifying user email: {str(e)}")
        return False

def send_verification_email_service(db: Session, email: str) -> bool:
    """Send verification email."""
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return False
        
        # Generate verification token
        verification_token = generate_secure_token()
        user.verification_token = verification_token
        user.verification_token_expires = datetime.utcnow() + timedelta(hours=24)
        db.commit()
        
        # Send verification email
        send_verification_email(user.email, verification_token)
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error sending verification email: {str(e)}")
        return False

# Admin functions
def deactivate_user(db: Session, user_id: str, admin_id: str, reason: str = None) -> bool:
    """Deactivate a user (admin only)."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.is_active = False
        user.deactivated_at = datetime.utcnow()
        user.deactivation_reason = reason
        user.deactivated_by = admin_id
        
        # Invalidate all sessions
        invalidate_all_sessions(db, user_id)
        
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="user_deactivate",
            user_id=admin_id,
            data={
                "target_user_id": user_id,
                "reason": reason,
                "deactivated_at": datetime.utcnow().isoformat()
            }
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deactivating user: {str(e)}")
        return False

def activate_user(db: Session, user_id: str, admin_id: str) -> bool:
    """Activate a deactivated user (admin only)."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.is_active = True
        user.deactivated_at = None
        user.deactivation_reason = None
        user.deactivated_by = None
        user.updated_at = datetime.utcnow()
        
        db.commit()
        
        # Create blockchain transaction
        create_blockchain_transaction(
            transaction_type="user_activate",
            user_id=admin_id,
            data={
                "target_user_id": user_id,
                "activated_at": datetime.utcnow().isoformat()
            }
        )
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error activating user: {str(e)}")
        return False

# Token blacklisting
def blacklist_token(db: Session, token: str, expires_at: datetime) -> bool:
    """Blacklist a token (for logout)."""
    try:
        # Check if token already blacklisted
        existing = db.query(BlacklistedToken).filter(BlacklistedToken.token == token).first()
        if existing:
            return True
        
        blacklisted_token = BlacklistedToken(
            token=token,
            expires_at=expires_at
        )
        
        db.add(blacklisted_token)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error blacklisting token: {str(e)}")
        return False

def is_token_blacklisted(db: Session, token: str) -> bool:
    """Check if a token is blacklisted."""
    try:
        blacklisted = db.query(BlacklistedToken).filter(
            and_(
                BlacklistedToken.token == token,
                BlacklistedToken.expires_at > datetime.utcnow()
            )
        ).first()
        
        return blacklisted is not None
    except Exception as e:
        logger.error(f"Error checking token blacklist: {str(e)}")
        return False