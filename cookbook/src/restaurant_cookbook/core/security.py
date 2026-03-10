from datetime import datetime, timedelta
from typing import Optional, Union, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from zoneinfo import ZoneInfo

from restaurant_cookbook.core.config import settings

_ET = ZoneInfo("America/New_York")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_now():
    return datetime.now(_ET)


def verify_token(token: str) -> Optional[dict]:
    """Verify JWT token — supports both Portal and local tokens."""
    # Try Portal secret first, then local secret
    for secret in [settings.PORTAL_SECRET_KEY, settings.SECRET_KEY]:
        if not secret:
            continue
        try:
            payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
            sub = payload.get("sub")
            if sub is None:
                continue
            try:
                int(sub)
                return {"id": str(sub)}
            except (ValueError, TypeError):
                return {"username": sub}
        except JWTError:
            continue
    return None


def create_access_token(
    subject: Union[str, Any], expires_delta: timedelta = None
) -> str:
    expire = get_now() + (expires_delta or timedelta(minutes=30))
    to_encode = {"exp": expire, "sub": str(subject)}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
