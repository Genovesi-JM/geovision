# app/security.py
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import JWT_SECRET, JWT_ALG, JWT_EXPIRE_MIN

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt.
    
    bcrypt has a 72-byte limit, so we truncate to avoid errors.
    """
    if password is None:
        password = ""
    # Truncate to 72 bytes (not characters) for bcrypt compatibility
    pw_bytes = password.encode('utf-8')[:72]
    return pwd_context.hash(pw_bytes.decode('utf-8', errors='ignore'))

def verify_password(plain_password: str, password_hash: str) -> bool:
    """Validate a plain-text password against a stored hash."""
    return pwd_context.verify(plain_password, password_hash)

def create_access_token(payload: dict) -> str:
    exp = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MIN)
    to_encode = {**payload, "exp": exp}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
