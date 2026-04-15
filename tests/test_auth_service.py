import pytest
from app.services.auth import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.services.auth import generate_ntrp_label
from jose import jwt as jose_jwt
from app.config import settings
import time


def test_hash_and_verify_password():
    password = "securePass123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongPass", hashed) is False


def test_create_and_decode_access_token():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = create_access_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = create_refresh_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_decode_invalid_token():
    payload = decode_token("invalid.token.here")
    assert payload is None


def test_decode_token_expired():
    """Expired token should return None."""
    payload = {"sub": "user123", "type": "access", "exp": int(time.time()) - 10}
    token = jose_jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    assert decode_token(token) is None


def test_decode_token_tampered():
    """Token signed with wrong key should return None."""
    payload = {"sub": "user123", "type": "access", "exp": int(time.time()) + 3600}
    token = jose_jwt.encode(payload, "wrong-secret-key", algorithm=settings.jwt_algorithm)
    assert decode_token(token) is None


def test_decode_token_malformed():
    assert decode_token("not.a.jwt") is None
    assert decode_token("") is None
    assert decode_token("abc") is None


def test_generate_ntrp_label_all_levels():
    """All standard levels should return a label with Chinese text."""
    for level in ["1.0", "1.5", "2.0", "2.5", "3.0", "3.5", "4.0", "4.5", "5.0", "5.5", "6.0", "6.5", "7.0"]:
        label = generate_ntrp_label(level)
        assert level.rstrip("+-") in label


def test_generate_ntrp_label_with_modifiers():
    label_plus = generate_ntrp_label("3.5+")
    assert label_plus.endswith("+")
    assert "3.5" in label_plus

    label_minus = generate_ntrp_label("4.0-")
    assert label_minus.endswith("-")
    assert "4.0" in label_minus


def test_generate_ntrp_label_unknown():
    """Unknown level should return itself."""
    assert generate_ntrp_label("9.9") == "9.9"
