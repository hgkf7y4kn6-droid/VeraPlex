"""Provider interfaces. Each starts with exactly one implementation so vendors can be swapped."""
from dataclasses import dataclass
from typing import Protocol

import jwt

from app.core.config import settings


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    jti: str | None
    iat: int | None


class AuthenticationProvider(Protocol):
    def verify(self, token: str) -> TokenClaims: ...


class SupabaseAuthProvider:
    """Verifies a Supabase-issued HS256 JWT. Swap for a JWKS/SAML-backed provider later."""

    def verify(self, token: str) -> TokenClaims:
        try:
            data = jwt.decode(
                token, settings.supabase_jwt_secret, algorithms=["HS256"], audience=settings.jwt_audience,
                options={"require": ["sub", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(str(exc)) from exc
        return TokenClaims(sub=data["sub"], jti=data.get("jti"), iat=data.get("iat"))


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


auth_provider: AuthenticationProvider = SupabaseAuthProvider()
model_provider: AIModelProvider = StubModelProvider()
