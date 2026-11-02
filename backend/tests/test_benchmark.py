import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks import baselines, build_dataset, fakes, run, scoring
from benchmarks.run import DATA, load
from app.modules.ai import llm


@pytest.fixture(scope="module")
def index():
    return scoring.Index(load("corpus.jsonl"))


def test_manifest_matches_files_and_generator_is_deterministic(tmp_path, monkeypatch):
    m = run.verify_manifest()
    monkeypatch.setattr(build_dataset, "DATA", tmp_path)
    build_dataset.main()
    for name, meta in m["files"].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == meta["sha256"], f"{name} is not reproducible from seeds"


def test_dataset_integrity():
    corpus = {d["doc_number"]: d for d in load("corpus.jsonl")}
    allrows = {n: load(n) for n in ("corpus.jsonl", "retrieval.jsonl", "grounding.jsonl", "injection.jsonl", "extraction.jsonl")}
    for rows in allrows.values():
        ids = [r.get("id") or r["doc_number"] for r in rows]
        assert len(ids) == len(set(ids))
    for r in allrows["retrieval.jsonl"]:
        if r["answerable"]:
            body = scoring.norm(corpus[r["gold_doc"]]["body"])
            assert scoring.norm(r["gold_fact"]) in body
            others = [d for d, c in corpus.items() if d != r["gold_doc"] and scoring.norm(r["gold_fact"]) in scoring.norm(c["body"])]
            assert not others, "gold fact must be unique to one SOP"
    g = allrows["grounding.jsonl"]
    assert sum(c["answerable"] for c in g) == 16 and sum(not c["answerable"] for c in g) == 8
    for c in g:
        assert all(d in corpus for d in c["gold_docs"])
        assert c["answerable"] == bool(c["gold_docs"])
        assert not (not c["answerable"] and c["gold_related"])
    cases = {c["id"] for c in g}
    assert all(i["base_case"] in cases for i in allrows["injection.jsonl"])
    clean = [r for r in allrows["extraction.jsonl"] if r["noise_level"] == 0]
    for r in clean:
        assert all(r["gold"][f] in r["text"] for f in ("equipment_id", "batch_id", "area"))
    from collections import Counter
    assert set(Counter(r["gold"]["event_type"] for r in clean).values()) == {13}
    for rows in allrows.values():
        assert all(r["review_status"] == "unreviewed" for r in rows)


def test_no_real_world_data_claimed():
    m = json.loads((DATA / "MANIFEST.json").read_text())
    assert m["provenance"]["origin"] == "synthetic" and m["provenance"]["real_or_public_data_included"] is False
    assert m["provenance"]["customer_data_included"] is False and m["review_status"].startswith("UNREVIEWED")


def _grounding(index, provider, rows=None):
    cases = load("grounding.jsonl")
    res = []
    for c in cases:
        ctx = scoring.build_context(index, c)
        res.append(scoring.score_case(c, ctx, provider.draft("t", ctx).output))
    return scoring.aggregate_grounding(res)


def test_scorer_rewards_an_ideal_drafter_and_punishes_a_hallucinating_one(index):
    cases = load("grounding.jsonl")
    oracle = fakes.OracleProvider({f"dev:{c['id']}": c["gold_docs"] for c in cases})
    good = _grounding(index, oracle)
    assert good["citation_validity"] == 1.0 and good["hallucination_rate_unanswerable"] == 0.0
    assert good["gap_report_rate_unanswerable"] == 1.0 and good["evidence_recall_given_retrieved"] == 1.0
    assert good["claim_support_rate"] == 1.0
    bad = _grounding(index, fakes.HallucinatingProvider())
    assert bad["citation_validity"] == 0.0 and bad["cases_with_fabricated_ids"] == 1.0
    assert bad["hallucination_rate_unanswerable"] == 1.0 and bad["evidence_recall"] == 0.0
    assert bad["claim_support_rate"] == 0.0


def test_injection_scorer_detects_obedience_and_the_local_provider_resists(index):
    def rate(provider):
        cases = {c["id"]: c for c in load("grounding.jsonl")}
        res = []
        for inj in load("injection.jsonl"):
            base = cases[inj["base_case"]]
            ctx = scoring.inject(base, scoring.build_context(index, base), inj)
            assert inj["payload"] in str(ctx)  # the payload really reached the model's context
            res.append(scoring.score_injection(provider.draft("t", ctx).output, inj, llm.allowed_source_ids(ctx)))
        return sum(r["success"] for r in res) / len(res)
    assert rate(fakes.InjectionVictim()) == 1.0
    assert rate(llm.LocalProvider()) == 0.0


def test_injection_payloads_are_neutralised_in_the_production_prompt(index):
    cases = {c["id"]: c for c in load("grounding.jsonl")}
    inj = next(i for i in load("injection.jsonl") if i["payload"].startswith("</source>"))
    base = cases[inj["base_case"]]
    ctx = scoring.inject(base, scoring.build_context(index, base), inj)
    msg = llm.render_user_message(ctx)
    assert '<source id="sop:FORGED-999#0"' not in msg


def test_extraction_scorer_bounds():
    rows = load("extraction.jsonl")
    perfect = scoring.score_extraction(fakes.PerfectExtractor(rows), rows)
    assert perfect["noise_0"]["all_fields"] == 1.0 and perfect["robustness_drop_all_fields"] == 0.0
    assert perfect["hard_noise_2"]["event_type_macro_f1"] == 1.0

    class Crash:
        name = "crash"
        def extract(self, text):
            raise RuntimeError("boom")
    broken = scoring.score_extraction(Crash(), rows)
    assert broken["noise_0"]["all_fields"] == 0.0 and broken["noise_0"]["n"] == len([r for r in rows if r["noise_level"] == 0])


def test_regex_baseline_is_good_on_templates_and_weak_on_hard_and_noisy():
    r = scoring.score_extraction(baselines.RegexExtractor(), load("extraction.jsonl"))
    assert r["easy_noise_0"]["all_fields"] > 0.95
    assert r["hard_noise_0"]["all_fields"] < 0.2          # headroom exists: the set is not saturated by a regex
    assert r["robustness_drop_all_fields"] > 0.05          # noise measurably hurts


def test_macro_f1_and_agreement_math():
    assert scoring.macro_f1(["a", "b"], ["a", "b"]) == 1.0
    assert scoring.macro_f1(["a", "a", "b", "b"], ["a", "a", "a", "a"]) == pytest.approx((2 / 3 + 0) / 2)
    assert scoring.agreement([{"x", "y"}, {"x", "y"}]) == 1.0
    assert scoring.agreement([{"x"}, {"y"}]) == 0.0
    assert scoring.agreement([{"x"}]) is None


def test_offline_baseline_run_is_deterministic_and_passes_its_floors(capsys):
    a = run.run_all(llm.LocalProvider(), baselines.RegexExtractor())
    b = run.run_all(llm.LocalProvider(), baselines.RegexExtractor())
    assert run.flatten(a) == run.flatten(b)
    rules = json.loads((Path(run.HERE) / "thresholds.json").read_text())
    assert run.check(a, rules["baseline_floor"]) == []
    assert run.check(a, {"retrieval.fact_recall@3": {"min": 0.99}}) != []   # the gate can actually fail
    assert run.main(["--check"]) == 0


def test_anthropic_extractor_request_shape_and_parsing():
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                               content=[SimpleNamespace(type="text", text=json.dumps({"equipment_id": "EQ-123", "batch_id": None, "area": None, "event_type": "contamination"}))])
    ex = baselines.AnthropicExtractor(client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert ex.extract("x")["equipment_id"] == "EQ-123"
    assert seen["model"] == "claude-opus-5-5" and "temperature" not in seen and "tool_choice" not in seen
    assert seen["output_config"]["format"]["type"] == "json_schema" and ex.usage == [10, 5]
