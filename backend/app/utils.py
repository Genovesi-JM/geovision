"""Utility helpers shared across the application.

This module uses passlib's CryptContext (bcrypt) for new hashes while
retaining compatibility with legacy SHA256 hashes previously used by the
project. `hash_password` will produce a bcrypt hash. `verify_password`
will detect the hash format and verify accordingly.
"""

# --- bcrypt / passlib compatibility shim ---
# passlib 1.7.4 reads bcrypt.__about__.__version__ which was removed in
# bcrypt ≥ 4.1.  Patch it before passlib is imported.
import bcrypt as _bcrypt
if not hasattr(_bcrypt, "__about__"):
    class _About:
        __version__ = getattr(_bcrypt, "__version__", "4.0.0")
    _bcrypt.__about__ = _About

from passlib.context import CryptContext
import hashlib

# Use bcrypt for new password hashes. passlib is listed in requirements.
# Keep PBKDF2-SHA256 for legacy hashes created before bcrypt was enabled.
pwd_context = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    """Create a password hash using bcrypt (passlib).

    Returns the encoded bcrypt hash string.
    """
    # bcrypt has a 72-byte input limit. Truncate by bytes (not characters)
    # to handle multi-byte UTF-8 properly.
    if password is None:
        password = ""
    pw_truncated = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(pw_truncated)


def _is_legacy_sha256(s: str) -> bool:
    """Rudimentary check whether a stored hash looks like a SHA256 hex digest."""
    if not s or not isinstance(s, str):
        return False
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s.lower())


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against either a bcrypt or legacy SHA256 hash.

    - If `hashed_password` looks like a bcrypt hash, use passlib to verify.
    - If it looks like a 64-char hex string assume legacy SHA256 and compare.
    """
    if not hashed_password:
        return False
    try:
        # bcrypt hashes produced by passlib start with $2b$ or $2a$
        if hashed_password.startswith("$2"):
            return pwd_context.verify(plain_password, hashed_password)
        # support legacy SHA256 hex digests
        if _is_legacy_sha256(hashed_password):
            sha = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
            return sha == hashed_password
        # Fallback: try passlib verify (covers other schemes if present)
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False
