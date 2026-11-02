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


class UserDirectoryProvider(Protocol):
    def invite(self, email: str) -> str:
        """Create/invite the identity in the auth system and return its subject (UUID string)."""


class SupabaseUserDirectory:
    """Supabase Admin API invite (service-role key, server-side only). Untested against a live project."""

    def __init__(self, url: str | None, service_key: str | None):
        self.url, self.key = (url or "").rstrip("/"), service_key

    def invite(self, email: str) -> str:
        import httpx
        if not (self.url and self.key):
            raise AuthError("Supabase Admin API is not configured")
        r = httpx.post(f"{self.url}/auth/v1/invite", json={"email": email}, timeout=15,
                       headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"})
        if r.status_code >= 400:
            raise AuthError(f"invite failed: {r.status_code}")
        return r.json()["id"]


@dataclass(frozen=True)
class DraftResult:
    output: dict
    input_tokens: int
    output_tokens: int
    model: str
    version: str


class AIModelProvider(Protocol):
    name: str
    external: bool  # True when content leaves our infrastructure

    def draft(self, task: str, context: dict) -> DraftResult: ...


user_directory: UserDirectoryProvider = SupabaseUserDirectory(settings.supabase_url, settings.supabase_service_key)
auth_provider: AuthenticationProvider = SupabaseAuthProvider(
    settings.supabase_url, settings.supabase_jwt_secret, settings.jwt_audience
)


# ---------------------------------------------------------------- embeddings / retrieval
import math
import re
import zlib

_STOP = set("a an and are as at be by for from has have in is it its of on or that the this to was were will with not no if then than but when which who".split())


def _tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in _STOP or len(w) < 2:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if len(w) > len(suf) + 3 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


class EmbeddingProvider(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Deterministic, offline, lexical (unigram+bigram feature hashing). Not semantic: it is the dev/test
    default and a floor for the eval; production should set VERAPLEX_EMBEDDING_URL to a TEI server."""

    name = "hashing-v1-512"
    dim = 512

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        toks = _tokens(text)
        v = [0.0] * self.dim
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        for f in feats:
            h = zlib.crc32(f.encode())
            v[h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        # sublinear scaling then L2 normalise
        v = [math.copysign(math.log1p(abs(x)), x) for x in v]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


class TEIEmbedder:
    """Hugging Face text-embeddings-inference (`POST /embed`). Untested against a live server."""

    def __init__(self, url: str, model: str):
        self.url, self.name = url.rstrip("/"), f"tei:{model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        r = httpx.post(f"{self.url}/embed", json={"inputs": texts, "normalize": True, "truncate": True}, timeout=30)
        r.raise_for_status()
        return r.json()


embedder: EmbeddingProvider = (
    TEIEmbedder(settings.embedding_url, settings.embedding_model) if settings.embedding_url else HashingEmbedder()
)
