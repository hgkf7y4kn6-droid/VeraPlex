"""Provider interfaces. Each starts with exactly one implementation so vendors stay swappable."""
from typing import Protocol

from app.modules.identity.principal import Principal


class AuthenticationProvider(Protocol):
    def verify_token(self, token: str) -> Principal: ...

    def verify_reauth(self, user_id: str, credential: str) -> str:
        """Re-authenticate at the moment of signing. Returns a re-auth event id; raises on failure."""


class StorageProvider(Protocol):
    def put(self, key: str, data: bytes) -> str: ...
    def signed_url(self, key: str, ttl_seconds: int = 300) -> str: ...


class AIModelProvider(Protocol):
    def complete(self, prompt: str, *, model: str) -> str: ...


class WorkflowProvider(Protocol):
    def start(self, name: str, payload: dict) -> str: ...


class NotificationProvider(Protocol):
    def send(self, user_id: str, message: str) -> None: ...


class BillingProvider(Protocol):
    def has_feature(self, tenant_id: str, feature: str) -> bool: ...

