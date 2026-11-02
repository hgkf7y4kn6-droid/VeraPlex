import uuid

import pytest
from sqlalchemy import select, text

from app.modules.audit import service as audit
from app.modules.audit.models import AuditEvent
from tests.conftest import token

API = "/api/v1"


from contextlib import contextmanager

from app.core.database import set_tenant_guc


@contextmanager
def scoped(Session, tenant_id):
    """A DB session with the RLS tenant setting applied, as the API does per request."""
    with Session() as db:
        set_tenant_guc(db, tenant_id)
        yield db

NEW = {"title": "Pressure drop on filler", "description": "x", "equipment_id": "EQ-7", "batch_id": "B1"}


@pytest.fixture()
def team(world):
    t = world.tenant("acme")
    return {
        "t": t, "op": world.user(t, "operator", "Olive"), "qa": world.user(t, "qa", "Quinn"),
        "inv": world.user(t, "investigator", "Ivan"), "ao": world.user(t, "area_owner", "Ana"),
        "ai": world.user(t, "ai_agent", "Quality Agent", kind="ai"), "admin": world.user(t, "admin", "Ada"),
    }


def h(uid, **kw):
    return {"Authorization": f"Bearer {token(uid, **kw)}"}


def make_capa_pending(client, team):
    dev = client.post(f"{API}/deviations", json=NEW, headers=h(team["op"])).json()["id"]
    r = client.post(f"{API}/deviations/{dev}/triage", headers=h(team["qa"]), json={
        "severity": 5, "occurrence": 4, "detectability": 3, "owner_id": str(team["ao"]), "due_date": "2026-12-01"})
    assert r.status_code == 200 and r.json()["classification"] == "critical"
    inv = client.post(f"{API}/deviations/{dev}/investigation", json={"reason": "start"}, headers=h(team["inv"])).json()
    capa = client.post(f"{API}/deviations/{dev}/capas", headers=h(team["inv"]), json={
        "title": "Replace gasket", "root_cause": "wear", "actions": [{"description": "replace"}]})
    assert capa.status_code == 201, capa.text
    cid = capa.json()["capa_id"]
    assert client.post(f"{API}/capas/{cid}/submit", headers=h(team["inv"])).status_code == 200
    return dev, inv["investigation_id"], cid


def test_full_flow_and_audit_chain(client, team, Session):
    dev, inv, cid = make_capa_pending(client, team)
    # author (investigator) lacks approve permission; QA signs, one signature is not enough
    s = client.post(f"{API}/capas/{cid}/sign", json={"reauth_token": token(team["qa"])}, headers=h(team["qa"]))
    assert s.status_code == 200, s.text
    sig = s.json()["signatures"][0]
    assert sig["signer"] == "Quinn" and sig["meaning"] == "approved" and sig["signed_at_utc"].endswith("Z")
    r = client.post(f"{API}/capas/{cid}/transition/approved", json={"reason": "approve"}, headers=h(team["qa"]))
    assert r.status_code == 409 and "area_owner" in r.text
    assert client.post(f"{API}/capas/{cid}/sign", json={"reauth_token": token(team["ao"])}, headers=h(team["ao"])).status_code == 200
    r = client.post(f"{API}/capas/{cid}/transition/approved", json={"reason": "both signed"}, headers=h(team["qa"]))
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/capas/{cid}", headers=h(team["qa"])).json()["effectiveness_due"] is not None
    with scoped(Session, team["t"]) as db:
        assert audit.verify_chain(db, team["t"])["ok"]
        acts = {e.action for e in db.scalars(select(AuditEvent))}
        assert {"deviation.create", "capa.sign", "capa.transition", "capa.effectiveness_scheduled"} <= acts
    assert client.get(f"{API}/audit/verify", headers=h(team["admin"])).json()["ok"] is True


def test_audit_tamper_detected_and_append_only(client, team, Session, admin_engine, dialect):
    make_capa_pending(client, team)
    for stmt in ("update audit_event set reason='x'", "delete from audit_event"):
        with Session() as db:
            with pytest.raises(Exception) as e:
                db.execute(text(stmt)); db.commit()
            if dialect == "postgres":
                assert "permission denied" in str(e.value)  # REVOKE, not a trigger
    # a DBA with raw superuser access bypasses the guard; the chain must still expose it
    with admin_engine.begin() as c:
        if dialect == "sqlite":
            c.execute(text("drop trigger audit_event_no_update"))
        c.execute(text("update audit_event set reason='tampered' where seq=2"))
    with scoped(Session, team["t"]) as db:
        res = audit.verify_chain(db, team["t"])
    assert res["ok"] is False and res["break_at_seq"] == 2 and res["reason"] == "hash mismatch"


def test_signature_requires_fresh_single_use_matching_reauth(client, team):
    _, _, cid = make_capa_pending(client, team)
    url = f"{API}/capas/{cid}/sign"
    assert client.post(url, json={"reauth_token": token(team["qa"], age=600)}, headers=h(team["qa"])).status_code == 401
    assert client.post(url, json={"reauth_token": token(team["ao"])}, headers=h(team["qa"])).status_code == 401
    assert client.post(url, json={"reauth_token": "garbage"}, headers=h(team["qa"])).status_code == 401
    t = token(team["qa"], jti="once")
    assert client.post(url, json={"reauth_token": t}, headers=h(team["qa"])).status_code == 200
    again = client.post(url, json={"reauth_token": t}, headers=h(team["ao"]))
    assert again.status_code == 401  # replay (and wrong subject)


def test_author_cannot_approve_own_record(client, team, world):
    t = team["t"]
    qa_author = world.user(t, "qa", "Selfie")
    dev = client.post(f"{API}/deviations", json=NEW, headers=h(qa_author)).json()["id"]
    client.post(f"{API}/deviations/{dev}/triage", headers=h(qa_author), json={
        "severity": 1, "occurrence": 1, "detectability": 1, "owner_id": str(qa_author), "due_date": "2026-12-01"})
    client.post(f"{API}/deviations/{dev}/investigation", json={"reason": "start investigation"}, headers=h(qa_author))
    cid = client.post(f"{API}/deviations/{dev}/capas", headers=h(qa_author), json={
        "title": "t t", "root_cause": "r", "actions": []}).json()["capa_id"]
    client.post(f"{API}/capas/{cid}/submit", headers=h(qa_author))
    r = client.post(f"{API}/capas/{cid}/sign", json={"reauth_token": token(qa_author)}, headers=h(qa_author))
    assert r.status_code == 403 and "segregation" in r.text


def test_locked_version_is_immutable(client, team, Session):
    _, _, cid = make_capa_pending(client, team)
    from app.modules.records import service as rs
    from app.modules.records.models import Record
    from app.core.security import principal_from_user
    with scoped(Session, team["t"]) as db:
        p = principal_from_user(db, team["inv"])
        r = db.get(Record, uuid.UUID(cid))
        with pytest.raises(Exception) as e:
            rs.edit_draft(db, p, r, {"title": "sneaky"}, "x")
        assert "locked" in str(e.value.detail)


def test_ai_principal_cannot_reach_regulated_actions(client, team):
    dev, inv, cid = make_capa_pending(client, team)
    ai = h(team["ai"])
    calls = [
        ("post", f"/capas/{cid}/sign", {"reauth_token": token(team["ai"])}),
        ("post", f"/capas/{cid}/transition/approved", {"reason": "please"}),
        ("post", f"/capas/{cid}/transition/closed", {"reason": "please"}),
        ("post", f"/capas/{cid}/submit", None),
        ("post", f"/deviations/{dev}/triage", {"severity": 1, "occurrence": 1, "detectability": 1,
                                               "owner_id": str(team["ao"]), "due_date": "2026-12-01"}),
        ("post", f"/investigations/{inv}/complete", {"reauth_token": token(team["ai"])}),
        ("post", f"/deviations/{dev}/capas", {"title": "abc", "root_cause": "r", "actions": []}),
    ]
    for m, path, body in calls:
        r = getattr(client, m)(API + path, headers=ai, **({"json": body} if body is not None else {}))
        assert r.status_code == 403, (path, r.status_code)
    assert client.get(f"{API}/deviations/{dev}", headers=ai).status_code == 200  # read is allowed


def test_ai_draft_labeled_cited_and_adoption_audited(client, team, Session):
    dev = client.post(f"{API}/deviations", json=NEW, headers=h(team["op"])).json()["id"]
    prior = client.post(f"{API}/deviations", json={**NEW, "title": "Earlier event"}, headers=h(team["op"])).json()["id"]
    client.post(f"{API}/deviations/{dev}/triage", headers=h(team["qa"]), json={
        "severity": 2, "occurrence": 2, "detectability": 2, "owner_id": str(team["ao"]), "due_date": "2026-12-01"})
    inv = client.post(f"{API}/deviations/{dev}/investigation", json={"reason": "start investigation"}, headers=h(team["inv"])).json()["investigation_id"]
    d = client.post(f"{API}/deviations/{dev}/ai-draft", json={"investigation_id": inv}, headers=h(team["inv"]))
    assert d.status_code == 201, d.text
    body = d.json()["content"]
    assert "AI-GENERATED DRAFT" in body["label"] and f"dev:{prior}" in body["sources"] and f"dev:{dev}" in body["sources"]
    # AI cannot adopt its own draft; a human can
    assert client.post(f"{API}/ai-drafts/{d.json()['id']}/adopt", json={"reason": "ok ok"}, headers=h(team["ai"])).status_code == 403
    assert client.post(f"{API}/ai-drafts/{d.json()['id']}/adopt", json={"reason": "reviewed"}, headers=h(team["inv"])).status_code == 200
    with scoped(Session, team["t"]) as db:
        kinds = {(e.action, e.actor_kind) for e in db.scalars(select(AuditEvent))}
        assert ("ai_draft.create", "ai") in kinds and ("ai_draft.adopt", "human") in kinds
        assert audit.verify_chain(db, team["t"])["ok"]


def test_recurring_deviation_rule(client, team):
    flags = [client.post(f"{API}/deviations", json=NEW, headers=h(team["op"])).json()["recurring"] for _ in range(3)]
    assert flags == [False, False, True]
    other = client.post(f"{API}/deviations", json={**NEW, "equipment_id": "EQ-9"}, headers=h(team["op"])).json()
    assert other["recurring"] is False


def test_tenant_isolation(client, world, team):
    other_t = world.tenant("rival")
    rival_qa = world.user(other_t, "qa", "Rex")
    dev = client.post(f"{API}/deviations", json=NEW, headers=h(team["op"])).json()["id"]
    assert client.get(f"{API}/deviations/{dev}", headers=h(rival_qa)).status_code == 404
    assert client.get(f"{API}/deviations", headers=h(rival_qa)).json() == []
    assert client.post(f"{API}/deviations/{dev}/triage", headers=h(rival_qa), json={
        "severity": 1, "occurrence": 1, "detectability": 1, "owner_id": str(rival_qa), "due_date": "2026-12-01"}).status_code == 404
    assert client.get(f"{API}/audit/events", headers=h(rival_qa)).json() == []
    # tenant cannot be chosen by the caller
    assert client.get(f"{API}/deviations?tenant_id={team['t']}", headers=h(rival_qa)).json() == []


def test_auth_required(client):
    assert client.get(f"{API}/deviations").status_code == 401
    assert client.get(f"{API}/deviations", headers={"Authorization": "Bearer nope"}).status_code == 401


@pytest.mark.parametrize("_", [0])
def test_rls_backstop_blocks_cross_tenant_even_without_app_filters(client, team, world, Session, dialect, _):
    """Postgres only: bypass FastAPI/service filters entirely and query tables directly."""
    if dialect != "postgres":
        pytest.skip("RLS is Postgres-specific")
    other = world.tenant("rival")
    client.post(f"{API}/deviations", json=NEW, headers=h(team["op"]))
    with Session() as db:  # no tenant GUC set at all -> sees nothing
        assert db.execute(text("select count(*) from record")).scalar() == 0
        assert db.execute(text("select count(*) from audit_event")).scalar() == 0
    with Session() as db:
        db.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(other)})
        assert db.execute(text("select count(*) from record")).scalar() == 0
        assert db.execute(text("select count(*) from deviation")).scalar() == 0
        with pytest.raises(Exception):  # WITH CHECK: cannot write a row into another tenant
            db.execute(text("insert into record (id, tenant_id, type, state, current_version_no, created_by, created_at) "
                            "values (gen_random_uuid(), :t, 'x', 'x', 1, gen_random_uuid(), now())"), {"t": str(team["t"])})
    with Session() as db:
        db.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(team["t"])})
        assert db.execute(text("select count(*) from record")).scalar() == 1
