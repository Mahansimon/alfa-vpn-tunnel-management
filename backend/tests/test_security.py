"""تست‌های امنیتی: پسورد، رمزنگاری، RBAC و امضای درخواست."""
from __future__ import annotations

from app.core.crypto import decrypt, encrypt, hash_token, mask, sign_payload, verify_signature, verify_token
from app.core.rbac import has_permission, permissions_for
from app.core.security import generate_password, hash_password, password_problems, verify_password


def test_generated_password_is_strong():
    for _ in range(20):
        password = generate_password(24)
        assert len(password) == 24
        assert not password_problems(password)


def test_password_policy_rejects_weak():
    assert password_problems("short")
    assert password_problems("alllowercase123!")
    assert password_problems("NOLOWERCASE123!")
    assert password_problems("NoDigitsHere!!!")
    assert password_problems("NoSpecial12345")


def test_password_hash_roundtrip():
    hashed = hash_password("Str0ng-Passw0rd!x")
    assert hashed != "Str0ng-Passw0rd!x"
    assert verify_password("Str0ng-Passw0rd!x", hashed)
    assert not verify_password("wrong", hashed)


def test_secret_encryption_roundtrip():
    cipher = encrypt("super-secret-token")
    assert cipher.startswith("enc:v1:")
    assert "super-secret-token" not in cipher
    assert decrypt(cipher) == "super-secret-token"


def test_token_hashing_and_masking():
    token = "abcd1234efgh5678"
    assert verify_token(token, hash_token(token))
    assert not verify_token("other", hash_token(token))
    assert mask(token).startswith("abcd")
    assert mask(token).count("*") == len(token) - 4


def test_request_signing():
    signature = sign_payload("shared-secret", '{"a":1}')
    assert verify_signature("shared-secret", '{"a":1}', signature)
    assert not verify_signature("shared-secret", '{"a":2}', signature)


def test_rbac_matrix():
    assert has_permission("viewer", "servers.read")
    assert not has_permission("viewer", "servers.write")
    assert has_permission("operator", "tunnels.create")
    assert not has_permission("operator", "users.manage")
    assert has_permission("admin", "users.manage")
    assert has_permission("owner", "settings.write")
    assert permissions_for("owner") >= permissions_for("admin") >= permissions_for("operator")
