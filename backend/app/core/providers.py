"""Provider interfaces. Each starts with exactly one implementation so vendors can be swapped."""
import hashlib
from dataclasses import dataclass
from typing import Protocol

import jwt

from app.core.config import settings


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    token_id: str  # jti if present, else a hash of the token; used to make re-auth single-use
    issued_at: int
    authenticated_at: int  # last time the user actually proved identity (Supabase `amr`), else iat


class AuthenticationProvider(Protocol):
    def verify(self, token: str) -> TokenClaims: ...


ASYMMETRIC_ALGS = ["ES256", "RS256", "EdDSA"]


class SupabaseAuthProvider:
    """Verifies Supabase access tokens.

    * Asymmetric signing keys (ES256/RS256/EdDSA) are verified against the project's JWKS and the
      issuer `{supabase_url}/auth/v1`.
    * Legacy HS256 tokens are accepted only when a shared secret is configured.
    The algorithm is decided by the *key source*, never by the token header alone, which blocks
    `alg=none` and HS256-signed-with-the-public-key confusion attacks.
    """

    def __init__(self, supabase_url: str | None = None, hs256_secret: str | None = None,
                 audience: str = "authenticated", key_resolver=None):
        self.url = supabase_url.rstrip("/") if supabase_url else None
        self.secret = hs256_secret
        self.audience = audience
        self._resolver = key_resolver
        self._jwks = jwt.PyJWKClient(f"{self.url}/auth/v1/.well-known/jwks.json", cache_keys=True) if self.url and not key_resolver else None

    def _asymmetric_key(self, token: str):
        if self._resolver:
            return self._resolver(token)
        if self._jwks:
            return self._jwks.get_signing_key_from_jwt(token).key
        raise AuthError("asymmetric tokens are not accepted: no JWKS configured")

    def verify(self, token: str) -> TokenClaims:
        try:
            alg = jwt.get_unverified_header(token).get("alg")
            opts = {"require": ["sub", "exp", "iat"]}
            if alg == "HS256":
                if not self.secret:
                    raise AuthError("HS256 tokens are not accepted")
                data = jwt.decode(token, self.secret, algorithms=["HS256"], audience=self.audience, options=opts)
            elif alg in ASYMMETRIC_ALGS:
                kwargs = {"issuer": f"{self.url}/auth/v1"} if self.url else {}
                data = jwt.decode(token, self._asymmetric_key(token), algorithms=[alg], audience=self.audience,
                                  options=opts, **kwargs)
            else:
                raise AuthError(f"unsupported token algorithm: {alg}")
        except jwt.PyJWTError as exc:
            raise AuthError(str(exc)) from exc
        stamps = [a.get("timestamp") for a in data.get("amr", []) if isinstance(a, dict) and isinstance(a.get("timestamp"), int)]
        return TokenClaims(
            sub=data["sub"], token_id=data.get("jti") or hashlib.sha256(token.encode()).hexdigest(),
            issued_at=data["iat"], authenticated_at=max(stamps) if stamps else data["iat"],
        )


class AIModelProvider(Protocol):
    def draft(self, task: str, context: dict) -> dict: ...


class StubModelProvider:
    """Deterministic placeholder so the pipeline, audit and governance are testable without an LLM.
    A real provider implements the same interface behind the model gateway."""

    name = "stub"
    version = "0"

    def draft(self, task: str, context: dict) -> dict:
        deviation = context["deviation"]
        related = context["related"]
        return {
            "five_whys": [
                {"why": i + 1, "question": "Why?", "answer": "TO BE COMPLETED BY INVESTIGATOR"} for i in range(5)
            ],
            "fishbone_categories": ["Man", "Machine", "Method", "Material", "Measurement", "Environment"],
            "summary": f"Draft for: {deviation['title']}. {len(related)} related prior event(s) found.",
        }


auth_provider: AuthenticationProvider = SupabaseAuthProvider(
    settings.supabase_url, settings.supabase_jwt_secret, settings.jwt_audience
)
model_provider: AIModelProvider = StubModelProvider()
