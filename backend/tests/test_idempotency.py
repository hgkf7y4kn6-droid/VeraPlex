from tests.test_slice import API, NEW, h, team  # noqa: F401


def post(client, who, key, body=NEW):
    return client.post(f"{API}/deviations", json=body, headers={**h(who), "Idempotency-Key": key})


def test_replay_returns_original_and_creates_one_record(client, team):
    a = post(client, team["op"], "offline-key-0001")
    b = post(client, team["op"], "offline-key-0001")
    assert a.status_code == 201 and b.status_code == 200 and a.json()["id"] == b.json()["id"]
    assert len(client.get(f"{API}/deviations", headers=h(team["op"])).json()) == 1


def test_same_key_different_payload_or_user_or_short_key(client, team):
    post(client, team["op"], "offline-key-0002")
    assert post(client, team["op"], "offline-key-0002", {**NEW, "title": "different"}).status_code == 422
    assert post(client, team["inv"], "offline-key-0002").status_code == 201  # keys are per-user
    assert post(client, team["op"], "short").status_code == 422


def test_client_times_are_recorded_as_claims_and_me_endpoint(client, team):
    r = client.post(f"{API}/deviations", headers=h(team["op"]), json={
        **NEW, "occurred_at": "2026-11-01T08:00:00Z", "client_captured_at": "2026-11-01T08:05:00Z"})
    c = r.json()["content"]
    assert c["occurred_at"].startswith("2026-11-01T08:00") and c["client_captured_at"]
    me = client.get(f"{API}/me", headers=h(team["op"])).json()
    assert me["role"] == "operator" and "deviation.create" in me["permissions"] and "capa.approve" not in me["permissions"]
    assert client.get(f"{API}/me").status_code == 401
