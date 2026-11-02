from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app.modules.audit import service as audit
from app.modules.audit.models import AuditEvent
from app.modules.documents import service as docs
from tests.conftest import token
from tests.test_slice import API, h, make_capa_pending, scoped, team  # noqa: F401


def new_sop(client, team, number="SOP-001", roles=None):
    r = client.post(f"{API}/sops", headers=h(team["inv"]), json={
        "doc_number": number, "title": "Line clearance", "body": "v1 text", "training_roles": roles})
    assert r.status_code == 201, r.text
    return r.json()["sop_id"], r.json()["revision_id"]


def release(client, team, rid):
    """submit -> review (area owner) -> approve (QA) -> effective."""
    assert client.post(f"{API}/sop-revisions/{rid}/submit", json={"reason": "ready for review"}, headers=h(team["inv"])).status_code == 200
    r = client.post(f"{API}/sop-revisions/{rid}/sign", json={"meaning": "reviewed", "reauth_token": token(team["ao"])}, headers=h(team["ao"]))
    assert r.status_code == 200, r.text
    r = client.post(f"{API}/sop-revisions/{rid}/sign", json={"meaning": "approved", "reauth_token": token(team["qa"])}, headers=h(team["qa"]))
    assert r.status_code == 200, r.text
    assert client.post(f"{API}/sop-revisions/{rid}/approve", json={"reason": "approved"}, headers=h(team["qa"])).status_code == 200
    r = client.post(f"{API}/sop-revisions/{rid}/make-effective", headers=h(team["qa"]))
    assert r.status_code == 200, r.text
    return r.json()


def test_sop_lifecycle_training_and_ack(client, team, Session):
    sop, rid = new_sop(client, team)
    assert release(client, team, rid)["training_assigned"] == 4
    rev = client.get(f"{API}/sop-revisions/{rid}", headers=h(team["op"])).json()
    assert rev["state"] == "effective" and rev["review_due"] is not None
    assert {s["meaning"] for s in rev["signatures"]} == {"reviewed", "approved"}
    # operator sees an assignment and acknowledges with re-auth, once
    a = client.get(f"{API}/me/training", headers=h(team["op"])).json()
    assert len(a) == 1 and a[0]["status"] == "assigned"
    url = f"{API}/training/{a[0]['id']}/acknowledge"
    assert client.post(url, json={"reauth_token": token(team["op"], age=900)}, headers=h(team["op"])).status_code == 401
    ok = client.post(url, json={"reauth_token": token(team["op"])}, headers=h(team["op"]))
    assert ok.status_code == 200 and ok.json()["content_hash"]
    assert client.post(url, json={"reauth_token": token(team["op"])}, headers=h(team["op"])).status_code == 409
    # someone else's assignment is invisible
    assert client.post(url, json={"reauth_token": token(team["qa"])}, headers=h(team["qa"])).status_code == 404
    with scoped(Session, team["t"]) as db:
        assert audit.verify_chain(db, team["t"])["ok"]
        acts = {e.action for e in db.scalars(select(AuditEvent))}
        assert {"sop_revision.sign", "sop.training_assigned", "training.acknowledge"} <= acts


def test_training_limited_to_listed_roles(client, team):
    _, rid = new_sop(client, team, roles=["operator"])
    assert release(client, team, rid)["training_assigned"] == 1


def test_segregation_and_gates(client, team):
    _, rid = new_sop(client, team)
    sign = lambda who, m: client.post(f"{API}/sop-revisions/{rid}/sign", json={"meaning": m, "reauth_token": token(team[who])}, headers=h(team[who]))
    assert sign("ao", "reviewed").status_code == 409  # not in review yet
    client.post(f"{API}/sop-revisions/{rid}/submit", json={"reason": "go for review"}, headers=h(team["inv"]))
    # cannot edit once submitted (locked)
    assert client.put(f"{API}/sop-revisions/{rid}", json={"body": "sneaky", "change_summary": "sneaky"}, headers=h(team["inv"])).status_code == 409
    assert client.post(f"{API}/sop-revisions/{rid}/approve", json={"reason": "skip ahead"}, headers=h(team["qa"])).status_code == 409
    assert client.post(f"{API}/sop-revisions/{rid}/make-effective", headers=h(team["qa"])).status_code == 409
    assert sign("inv", "reviewed").status_code == 403  # investigator lacks sop.review
    assert sign("ao", "approved").status_code == 403  # area owner cannot approve
    assert sign("qa", "reviewed").status_code == 200
    assert sign("qa", "approved").status_code == 200
    r = client.post(f"{API}/sop-revisions/{rid}/approve", json={"reason": "same person twice"}, headers=h(team["qa"]))
    assert r.status_code == 409 and "different people" in r.text


def test_author_cannot_review_own_sop(client, team, world):
    qa2 = world.user(team["t"], "qa", "Quentin")
    r = client.post(f"{API}/sops", headers=h(qa2), json={"doc_number": "SOP-9", "title": "Self made", "body": "x"})
    rid = r.json()["revision_id"]
    client.post(f"{API}/sop-revisions/{rid}/submit", json={"reason": "go for review"}, headers=h(qa2))
    assert client.post(f"{API}/sop-revisions/{rid}/sign", json={"meaning": "approved", "reauth_token": token(qa2)}, headers=h(qa2)).status_code == 403
    client.post(f"{API}/sop-revisions/{rid}/sign", json={"meaning": "reviewed", "reauth_token": token(qa2)}, headers=h(qa2))
    client.post(f"{API}/sop-revisions/{rid}/sign", json={"meaning": "approved", "reauth_token": token(team["qa"])}, headers=h(team["qa"]))
    assert client.post(f"{API}/sop-revisions/{rid}/approve", json={"reason": "check"}, headers=h(team["qa"])).status_code == 409  # reviewer == author


def test_capa_change_control_supersedes_and_retrains(client, team, Session):
    sop, rid1 = new_sop(client, team, number="SOP-100")
    release(client, team, rid1)
    _, _, cid = make_capa_pending(client, team)
    # not allowed before the CAPA is approved
    cc_body = {"sop_id": sop, "rationale": "gasket check step added", "new_body": "v2 text with gasket check"}
    assert client.post(f"{API}/capas/{cid}/change-controls", json=cc_body, headers=h(team["inv"])).status_code == 409
    for who in ("qa", "ao"):
        client.post(f"{API}/capas/{cid}/sign", json={"reauth_token": token(team[who])}, headers=h(team[who]))
    assert client.post(f"{API}/capas/{cid}/transition/approved", json={"reason": "both signed"}, headers=h(team["qa"])).status_code == 200
    cc = client.post(f"{API}/capas/{cid}/change-controls", json=cc_body, headers=h(team["inv"]))
    assert cc.status_code == 201, cc.text
    rid2, ccid = cc.json()["sop_revision_id"], cc.json()["change_control_id"]
    # only one revision in flight at a time
    assert client.post(f"{API}/sops/{sop}/revisions", json={"body": "x", "change_summary": "dup"}, headers=h(team["inv"])).status_code == 409
    assert client.get(f"{API}/sop-revisions/{rid2}", headers=h(team["op"])).json()["content"]["body"].startswith("v2")
    release(client, team, rid2)
    # v1 superseded and its unacknowledged training cancelled; v2 training assigned; CC implemented
    assert client.get(f"{API}/sop-revisions/{rid1}", headers=h(team["op"])).json()["state"] == "superseded"
    assert client.get(f"{API}/sop-revisions/{rid2}", headers=h(team["op"])).json()["state"] == "effective"
    mine = {t["revision_id"]: t["status"] for t in client.get(f"{API}/me/training", headers=h(team["op"])).json()}
    assert mine == {rid1: "superseded", rid2: "assigned"}
    old = [t for t in client.get(f"{API}/me/training", headers=h(team["op"])).json() if t["revision_id"] == rid1][0]
    assert client.post(f"{API}/training/{old['id']}/acknowledge", json={"reauth_token": token(team["op"])}, headers=h(team["op"])).status_code == 409
    assert client.get(f"{API}/change-controls/{ccid}", headers=h(team["qa"])).json()["state"] == "implemented"
    assert client.post(f"{API}/change-controls/{ccid}/close", json={"reason": "verified"}, headers=h(team["inv"])).status_code == 403
    assert client.post(f"{API}/change-controls/{ccid}/close", json={"reason": "verified"}, headers=h(team["qa"])).status_code == 200
    with scoped(Session, team["t"]) as db:
        assert audit.verify_chain(db, team["t"])["ok"]


def test_ai_cannot_touch_sops_but_can_read(client, team):
    sop, rid = new_sop(client, team)
    ai = h(team["ai"])
    assert client.get(f"{API}/sops", headers=ai).status_code == 200
    assert client.post(f"{API}/sops", headers=ai, json={"doc_number": "SOP-AI", "title": "nope nope", "body": "x"}).status_code == 403
    client.post(f"{API}/sop-revisions/{rid}/submit", json={"reason": "ready for review"}, headers=h(team["inv"]))
    for path, body in ((f"/sop-revisions/{rid}/sign", {"meaning": "reviewed", "reauth_token": token(team["ai"])}),
                       (f"/sop-revisions/{rid}/approve", {"reason": "please"}), (f"/sop-revisions/{rid}/make-effective", None)):
        r = client.post(API + path, headers=ai, **({"json": body} if body else {}))
        assert r.status_code == 403, path


def test_sop_tenant_isolation(client, team, world):
    sop, rid = new_sop(client, team)
    rival = world.user(world.tenant("rival"), "qa", "Rex")
    assert client.get(f"{API}/sops", headers=h(rival)).json() == []
    assert client.get(f"{API}/sop-revisions/{rid}", headers=h(rival)).status_code == 404
    assert client.post(f"{API}/sop-revisions/{rid}/submit", json={"reason": "steal it"}, headers=h(rival)).status_code == 404
    assert client.get(f"{API}/sops/{sop}/revisions", headers=h(rival)).status_code == 404
    # same doc number is allowed in another tenant, not twice in one
    assert client.post(f"{API}/sops", headers=h(rival), json={"doc_number": "SOP-001", "title": "Theirs", "body": "x"}).status_code == 201
    assert client.post(f"{API}/sops", headers=h(team["inv"]), json={"doc_number": "SOP-001", "title": "Dup dup", "body": "x"}).status_code == 409


def test_reminders_and_month_math(client, team, Session):
    _, rid = new_sop(client, team)
    release(client, team, rid)
    with scoped(Session, team["t"]) as db:
        today = date.today()
        none = docs.reminders(db, team["t"], today)
        assert none["reviews_due"] == [] and none["overdue_training"] == []
        late = docs.reminders(db, team["t"], today + timedelta(days=25 * 31))
        assert len(late["reviews_due"]) == 1 and late["reviews_due"][0]["overdue"] is True
        assert len(docs.reminders(db, team["t"], today + timedelta(days=15))["overdue_training"]) == 4
    assert client.get(f"{API}/sops/reminders", headers=h(team["qa"])).status_code == 200
    assert client.get(f"{API}/sops/reminders", headers=h(team["op"])).status_code == 403
    assert docs._add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert docs._add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert docs._add_months(date(2026, 12, 15), 24) == date(2028, 12, 15)


def test_every_tenant_table_has_rls_and_acknowledgments_are_append_only(client, team, Session, dialect, admin_engine):
    if dialect != "postgres":
        pytest.skip("Postgres only")
    with admin_engine.connect() as c:
        missing = [r[0] for r in c.execute(text(
            "select c.relname from pg_class c join pg_attribute a on a.attrelid=c.oid and a.attname='tenant_id' "
            "where c.relkind='r' and c.relnamespace='public'::regnamespace and not c.relrowsecurity "
            "and c.relname not in ('membership')"))]
    assert missing == [], f"tenant tables without RLS: {missing}"
    with Session() as db:
        with pytest.raises(Exception) as e:
            db.execute(text("update acknowledgment set user_name='x'")); db.commit()
        assert "permission denied" in str(e.value)
