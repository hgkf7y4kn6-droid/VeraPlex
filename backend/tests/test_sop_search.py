import pytest

from tests.conftest import token
from tests.test_slice import API, h, team  # noqa: F401
from tests.test_sop_control import release

CORPUS = {
    "SOP-CLN-001": ("Line clearance before batch start", "Before each batch the operator performs line clearance. Remove all labels, packaging components and "
                    "product residues from the filling line. A second person verifies and signs the line clearance checklist before the line is released for filling."),
    "SOP-CAL-014": ("Calibration of balances and pressure gauges", "All weighing balances and pressure gauges are calibrated at defined intervals against traceable "
                    "standards. Instruments found out of tolerance trigger an impact assessment of batches processed since the last successful calibration."),
    "SOP-ENV-007": ("Environmental monitoring of cleanrooms", "Viable and non-viable particle counts are monitored in grade A and grade B cleanrooms. Settle plates and "
                    "contact plates are incubated; excursions above alert levels require investigation and trend review."),
    "SOP-CLD-003": ("Cold chain storage and temperature excursions", "Refrigerated materials are stored between 2 and 8 degrees Celsius. A temperature excursion "
                    "recorded by the data logger must be reported immediately, product quarantined, and a stability assessment performed before disposition."),
    "SOP-CLE-022": ("Cleaning and sanitisation of filling equipment", "Product contact parts of the filler, including seals and gaskets, are cleaned and sanitised after each "
                    "campaign. Worn gaskets or seals showing leakage are replaced and the cleaning is verified by swab."),
    "SOP-TRN-005": ("Personnel gowning and training qualification", "Operators entering grade B areas complete gowning qualification annually. "
                    "Gowning technique is assessed by microbiological finger dabs and visual observation."),
}
QUERIES = [  # (deviation-like text, expected doc)
    ("operator found labels left on the filling line at batch start", "SOP-CLN-001"),
    ("pressure gauge reading out of tolerance during calibration check", "SOP-CAL-014"),
    ("viable particle count above alert level in grade B cleanroom", "SOP-ENV-007"),
    ("refrigerator data logger recorded a temperature excursion above 8 degrees", "SOP-CLD-003"),
    ("seal on the filler is leaking, gasket worn", "SOP-CLE-022"),
    ("operator failed gowning qualification finger dab", "SOP-TRN-005"),
    ("labels residue on line before start of batch", "SOP-CLN-001"),
    ("cold storage excursion product quarantined", "SOP-CLD-003"),
]


def make_effective_sop(client, team, number, title, body, **kw):
    r = client.post(f"{API}/sops", headers=h(team["inv"]), json={"doc_number": number, "title": title, "body": body, **kw})
    assert r.status_code == 201, r.text
    release(client, team, r.json()["revision_id"])
    return r.json()


def search(client, who, q, k=5):
    r = client.get(f"{API}/sops/search", params={"q": q, "k": k}, headers=h(who))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def corpus(client, team):
    for n, (t, b) in CORPUS.items():
        make_effective_sop(client, team, n, t, b)
    return team


def test_retrieval_eval_recall_at_3_floor(client, corpus):
    """Fixed eval set scored in CI: the offline embedder must keep a recall@3 floor on this corpus."""
    hits = 0
    for q, expected in QUERIES:
        got = [r["doc_number"] for r in search(client, corpus["inv"], q, k=3)]
        hits += expected in got
    assert hits / len(QUERIES) >= 0.85, f"recall@3 {hits}/{len(QUERIES)}"
    top1 = sum(search(client, corpus["inv"], q, k=1)[0]["doc_number"] == e for q, e in QUERIES)
    assert top1 / len(QUERIES) >= 0.6, f"top-1 {top1}/{len(QUERIES)}"


def test_unanswerable_query_returns_nothing(client, corpus):
    assert search(client, corpus["inv"], "quarterly marketing budget for the cafeteria") == []
    assert search(client, corpus["inv"], "   ") == []


def test_only_effective_text_is_searchable_and_superseded_disappears(client, team):
    s = make_effective_sop(client, team, "SOP-X-1", "Widget handling", "Widgets must be handled with blue gloves only.")
    assert search(client, team["op"], "blue gloves widgets")[0]["doc_number"] == "SOP-X-1"
    rev2 = client.post(f"{API}/sops/{s['sop_id']}/revisions", headers=h(team["inv"]),
                       json={"body": "Widgets must be handled with green gloves only.", "change_summary": "glove colour"}).json()["id"]
    # a draft revision is not searchable
    assert "green" not in " ".join(r["text"] for r in search(client, team["op"], "green gloves widgets"))
    release(client, team, rev2)
    res = search(client, team["op"], "gloves widgets")
    assert res[0]["revision_no"] == 2 and "green" in res[0]["text"]
    assert all("blue" not in r["text"] for r in res)  # superseded revision is gone


def test_search_is_tenant_scoped_permissioned_and_ai_readable(client, team, world):
    make_effective_sop(client, team, "SOP-S-1", "Secret formulation handling", "Handle the confidential formulation vault procedure carefully.")
    rival = world.user(world.tenant("rival"), "qa", "Rex")
    assert search(client, rival, "confidential formulation vault") == []
    assert len(search(client, team["ai"], "confidential formulation vault")) == 1  # AI principal may read
    assert client.get(f"{API}/sops/search", params={"q": "x"}).status_code == 401


def test_chunking_and_chunk_citation_ids(client, team):
    long_body = "\n\n".join(f"Step {i}: " + ("inspect the autoclave door seal and record pressure. " * 12) for i in range(8))
    make_effective_sop(client, team, "SOP-L-1", "Autoclave operation", long_body)
    res = search(client, team["inv"], "autoclave door seal pressure", k=10)
    assert len(res) >= 3 and all(len(r["text"]) <= 900 for r in res)
    assert len({r["source_id"] for r in res}) == len(res)
    assert all(r["source_id"] == f"sop:{r['revision_id']}#{r['chunk_no']}" for r in res)


def test_reindex_is_admin_only_and_idempotent(client, team):
    make_effective_sop(client, team, "SOP-R-1", "Reindex me", "Unique zebra crossing procedure text.")
    assert client.post(f"{API}/sops/reindex", headers=h(team["op"])).status_code == 403
    assert client.post(f"{API}/sops/reindex", headers=h(team["qa"])).json()["chunks"] == 1
    assert len(search(client, team["op"], "zebra crossing")) == 1


def test_chunks_from_a_different_embedder_are_ignored(client, team, monkeypatch):
    from app.core import providers
    make_effective_sop(client, team, "SOP-E-1", "Embedder switch", "Unique platypus handling procedure text.")
    class Other(providers.HashingEmbedder):
        name = "other-embedder"
    monkeypatch.setattr(providers, "embedder", Other())
    assert search(client, team["op"], "platypus handling") == []  # needs reindex under the new embedder
    assert client.post(f"{API}/sops/reindex", headers=h(team["qa"])).status_code == 200
    assert len(search(client, team["op"], "platypus handling")) == 1
