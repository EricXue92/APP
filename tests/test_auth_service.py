import pytest
from app.services.auth import hash_password, verify_password, create_access_token, create_refresh_token, decode_token


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
