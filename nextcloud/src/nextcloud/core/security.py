"""
Security utilities for authentication and encryption
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from nextcloud.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Encryption cipher for storing sensitive credentials
cipher_suite = Fernet(settings.ENCRYPTION_KEY.encode() if settings.ENCRYPTION_KEY else Fernet.generate_key())


def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    """
    Create JWT access token

    Args:
        subject: Subject (typically user ID)
        expires_delta: Optional expiration time delta

    Returns:
        Encoded JWT token
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[str]:
    """
    Verify JWT token and return subject (user_id)

    Args:
        token: JWT token to verify

    Returns:
        User ID if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return user_id
    except JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash

    Args:
        plain_password: Plain text password
        hashed_password: Bcrypt hashed password

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Generate bcrypt password hash

    Args:
        password: Plain text password

    Returns:
        Bcrypt hashed password
    """
    return pwd_context.hash(password)


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypt sensitive credentials (Nextcloud passwords) for storage

    Args:
        plaintext: Plain text credential

    Returns:
        Encrypted credential (base64 encoded)
    """
    return cipher_suite.encrypt(plaintext.encode()).decode()


def decrypt_credential(encrypted: str) -> str:
    """
    Decrypt stored credentials

    Args:
        encrypted: Encrypted credential (base64 encoded)

    Returns:
        Decrypted plain text credential
    """
    return cipher_suite.decrypt(encrypted.encode()).decode()
