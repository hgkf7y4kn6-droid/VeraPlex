import jwt
from fastapi import Header, HTTPException

from app.config import settings
from app.modules.identity.principal import Principal


class SupabaseAuthProvider:
    def verify_token(self, token: str) -> Principal:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], audience=settings.jwt_audience
        )
        meta = claims.get("app_metadata", {})
        return Principal(
            user_id=claims["sub"],
            tenant_id=meta["tenant_id"],
            kind=meta.get("principal_kind", "human"),
            roles=frozenset(meta.get("roles", [])),
        )

    def verify_reauth(self, user_id: str, credential: str) -> str:
        # Phase 2 stub: wire to Supabase password/MFA re-verification before any pilot.
        raise NotImplementedError("re-authentication is not wired to Supabase yet")


auth_provider = SupabaseAuthProvider()


def current_principal(authorization: str = Header(default="")) -> Principal:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "missing bearer token")
    try:
        return auth_provider.verify_token(token)
    except Exception:
        raise HTTPException(401, "invalid token") from None


def get_auth_provider():
    return auth_provider

