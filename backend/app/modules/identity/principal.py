from dataclasses import dataclass, field
from typing import Literal


class PermissionDenied(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    kind: Literal["human", "ai"] = "human"
    roles: frozenset[str] = field(default_factory=frozenset)

    def require_role(self, role: str) -> None:
        if role not in self.roles:
            raise PermissionDenied(f"role '{role}' required")

    def forbid_ai(self, action: str) -> None:
        """Backend allowlist: the AI principal can never approve, release or sign."""
        if self.kind == "ai":
            raise PermissionDenied(f"AI principal may not {action}")
