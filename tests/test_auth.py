from app.auth import (
    create_access_token,
    decode_access_token,
    generate_verification_token,
    hash_password,
    verify_email_token,
    verify_password,
)


# ── Password hashing ───────────────────────────────────────────────────────────


def test_hash_and_verify_roundtrip():
    hashed = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", hashed) is True


def test_wrong_password_rejected():
    hashed = hash_password("correct-horse-battery")
    assert verify_password("wrong-password", hashed) is False


def test_hashes_are_unique():
    assert hash_password("same") != hash_password("same")


# ── JWT tokens ─────────────────────────────────────────────────────────────────


def test_access_token_roundtrip():
    token = create_access_token(42)
    assert decode_access_token(token) == 42


def test_invalid_token_returns_none():
    assert decode_access_token("not-a-token") is None


def test_empty_token_returns_none():
    assert decode_access_token("") is None


def test_tampered_token_returns_none():
    token = create_access_token(1)
    tampered = token[:-4] + "xxxx"
    assert decode_access_token(tampered) is None


# ── Email verification tokens ──────────────────────────────────────────────────


def test_verification_token_roundtrip():
    token = generate_verification_token("user@example.com")
    assert verify_email_token(token) == "user@example.com"


def test_invalid_verification_token_returns_none():
    assert verify_email_token("invalid-token") is None


def test_verification_token_is_email_specific():
    token_a = generate_verification_token("a@example.com")
    token_b = generate_verification_token("b@example.com")
    assert verify_email_token(token_a) != verify_email_token(token_b)
