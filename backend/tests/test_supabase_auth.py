import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.providers import AuthError, SupabaseAuthProvider

URL = "https://proj.supabase.co"
KEY = ec.generate_private_key(ec.SECP256R1())
OTHER = ec.generate_private_key(ec.SECP256R1())
PUB_PEM = KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def make(key=KEY, alg="ES256", **over):
    now = int(time.time())
    claims = {"sub": "u1", "aud": "authenticated", "iss": f"{URL}/auth/v1", "iat": now, "exp": now + 600, **over}
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm=alg, headers={"kid": "k1"})


@pytest.fixture()
def prov():
    return SupabaseAuthProvider(URL, hs256_secret=None, key_resolver=lambda t: KEY.public_key())


def test_valid_asymmetric_token(prov):
    c = prov.verify(make())
    assert c.sub == "u1" and len(c.token_id) == 64


def test_rejections(prov):
    for tok in (make(OTHER), make(aud="other"), make(iss="https://evil.example/auth/v1"), make(exp=int(time.time()) - 5)):
        with pytest.raises(AuthError):
            prov.verify(tok)


def test_alg_none_and_hs256_with_public_key_confusion(prov):
    none_tok = jwt.encode({"sub": "u1", "aud": "authenticated", "iat": int(time.time()), "exp": int(time.time()) + 60}, None, algorithm="none")
    with pytest.raises(AuthError):
        prov.verify(none_tok)
    now = int(time.time())
    import base64, hmac, json
    b = lambda d: base64.urlsafe_b64encode(d).rstrip(b"=")
    signing = b(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()) + b"." + b(
        json.dumps({"sub": "u1", "aud": "authenticated", "iat": now, "exp": now + 60}).encode())
    confused = (signing + b"." + b(hmac.new(PUB_PEM, signing, "sha256").digest())).decode()  # classic key-confusion forgery
    with pytest.raises(AuthError):  # no HS256 secret configured -> HS256 refused outright
        prov.verify(confused)


def test_hs256_only_with_configured_secret():
    p = SupabaseAuthProvider(URL, hs256_secret="s" * 40, key_resolver=lambda t: KEY.public_key())
    now = int(time.time())
    good = jwt.encode({"sub": "u1", "aud": "authenticated", "iat": now, "exp": now + 60}, "s" * 40, algorithm="HS256")
    assert p.verify(good).sub == "u1"
    bad = jwt.encode({"sub": "u1", "aud": "authenticated", "iat": now, "exp": now + 60}, "x" * 40, algorithm="HS256")
    with pytest.raises(AuthError):
        p.verify(bad)


def test_asymmetric_without_jwks_is_refused():
    with pytest.raises(AuthError):
        SupabaseAuthProvider(None, hs256_secret="s" * 40).verify(make())


def test_reauth_freshness_uses_amr_not_refresh_time(prov):
    now = int(time.time())
    c = prov.verify(make(amr=[{"method": "password", "timestamp": now - 3000}]))
    assert c.authenticated_at == now - 3000 and c.issued_at >= now - 1
    assert prov.verify(make()).authenticated_at == prov.verify(make()).issued_at


def test_production_refuses_unsafe_config():
    from app.core.config import DEV_SECRET, Settings, assert_production_safe
    with pytest.raises(RuntimeError):
        assert_production_safe(Settings(environment="production", supabase_jwt_secret=DEV_SECRET, supabase_url=URL))
    with pytest.raises(RuntimeError):
        assert_production_safe(Settings(environment="production", supabase_jwt_secret=None, supabase_url=None))
    assert_production_safe(Settings(environment="production", supabase_jwt_secret=None, supabase_url=URL))
