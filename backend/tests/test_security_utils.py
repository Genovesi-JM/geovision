import hashlib

from app.utils import hash_password, verify_password


def test_bcrypt_hash_and_verify_round_trip():
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith("$2")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_bcrypt_preserves_historical_72_byte_handling():
    password = "á" * 50
    encoded = hash_password(password)

    assert verify_password(password, encoded)


def test_legacy_sha256_hash_remains_supported():
    encoded = hashlib.sha256(b"legacy-password").hexdigest()

    assert verify_password("legacy-password", encoded)
    assert not verify_password("wrong password", encoded)


def test_passlib_pbkdf2_hash_remains_supported():
    encoded = "$pbkdf2-sha256$29000$bGVnYWN5U2FsdA$xVJxcH08rC8Y8F70izYoLynptEav.jQ5kO2wMaH3m6M"

    assert verify_password("legacy-password", encoded)
    assert not verify_password("wrong password", encoded)
