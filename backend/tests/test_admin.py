import uuid

import pytest
from sqlalchemy import select

from app.core import providers
from app.modules.audit import service as audit
from app.modules.audit.models import AuditEvent
from tests.test_slice import API, h, scoped, team  # noqa: F401


class FakeDirectory:
    def __init__(self):
        self.calls, self.fail = [], False

    def invite(self, email):
        if self.fail:
            raise providers.AuthError("down")
        self.calls.append(email)
        return str(uuid.uuid4())


@pytest.fixture()
def directory(monkeypatch):
    d = FakeDirectory()
    monkeypatch.setattr(providers, "user_directory", d)
    return d


def invite(client, who, email="new@x.test", role="operator"):
    return client.post(f"{API}/admin/users", headers=h(who), json={"email": email, "display_name": "New Person", "role": role})


def test_admin_invites_user_who_can_then_authenticate(client, team, directory, Session):
    r = invite(client, team["admin"])
    assert r.status_code == 201, r.text
    uid = uuid.UUID(r.json()["user_id"])
    assert directory.calls == ["new@x.test"]
    # the invited user (token subject = auth id) resolves to the right tenant and role
    assert client.post(f"{API}/deviations", headers=h(uid), json={"title": "first event", "description": "d"}).status_code == 201
    assert client.get(f"{API}/admin/users", headers=h(uid)).status_code == 403
    with scoped(Session, team["t"]) as db:
        assert "user.invite" in {e.action for e in db.scalars(select(AuditEvent))}
        assert audit.verify_chain(db, team["t"])["ok"]


def test_only_admin_and_no_ai_roles(client, team, directory):
    for who in ("op", "qa", "inv", "ao", "ai"):
        assert invite(client, team[who]).status_code == 403
    assert invite(client, team["admin"], role="ai_agent").status_code == 422
    assert invite(client, team["admin"], role="superuser").status_code == 422
    assert directory.calls == []


def test_duplicate_idp_failure_and_cross_tenant_identity(client, team, directory, world):
    assert invite(client, team["admin"]).status_code == 201
    assert invite(client, team["admin"], email="NEW@x.test").status_code == 409
    directory.fail = True
    assert invite(client, team["admin"], email="other@x.test").status_code == 502
    directory.fail = False
    # an identity already active in another tenant cannot be pulled into this one
    t2 = world.tenant("rival")
    existing = world.user(t2, "operator")
    directory.invite = lambda email: str(existing)
    assert invite(client, team["admin"], email="steal@x.test").status_code == 409


def test_role_change_deactivate_and_last_admin_protection(client, team, directory, world):
    uid = invite(client, team["admin"]).json()["user_id"]
    r = client.patch(f"{API}/admin/users/{uid}", headers=h(team["admin"]), json={"role": "qa", "reason": "promotion"})
    assert r.status_code == 200
    assert client.get(f"{API}/audit/events", headers=h(uuid.UUID(uid))).status_code == 200  # qa now
    # self-service escalation / lockout blocked
    assert client.patch(f"{API}/admin/users/{team['admin']}", headers=h(team["admin"]), json={"role": "qa", "reason": "oops"}).status_code == 403
    assert client.patch(f"{API}/admin/users/{team['admin']}", headers=h(team["admin"]), json={"active": False, "reason": "oops"}).status_code == 403
    # a second admin can demote the first only while another admin remains
    a2 = world.user(team["t"], "admin", "Ada Two")
    assert client.patch(f"{API}/admin/users/{team['admin']}", headers=h(a2), json={"role": "operator", "reason": "rotate"}).status_code == 200
    assert client.patch(f"{API}/admin/users/{a2}", headers=h(team["admin"]), json={"active": False, "reason": "x y z"}).status_code == 403  # no longer admin
    # deactivation ends access, records stay
    assert client.patch(f"{API}/admin/users/{uid}", headers=h(a2), json={"active": False, "reason": "left company"}).status_code == 200
    assert client.get(f"{API}/deviations", headers=h(uuid.UUID(uid))).status_code == 403


def test_admin_cannot_touch_other_tenants(client, team, directory, world):
    t2 = world.tenant("rival")
    victim = world.user(t2, "qa", "Victim")
    other_admin = world.user(t2, "admin", "Their Admin")
    assert client.patch(f"{API}/admin/users/{victim}", headers=h(team["admin"]), json={"active": False, "reason": "attack"}).status_code == 404
    assert client.patch(f"{API}/admin/users/{victim}", headers=h(team["admin"]), json={"role": "admin", "reason": "attack"}).status_code == 404
    emails = [u["email"] for u in client.get(f"{API}/admin/users", headers=h(other_admin)).json()]
    assert len(emails) == 2 and all(u["user_id"] != str(team["op"]) for u in client.get(f"{API}/admin/users", headers=h(other_admin)).json())
