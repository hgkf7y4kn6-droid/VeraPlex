"""Run the benchmark. Examples:
    python -m benchmarks.run                         # offline baselines (local provider + regex extractor)
    python -m benchmarks.run --draft anthropic --extract anthropic --repeats 3   # costs real money; needs a key
    python -m benchmarks.run --check                 # fail if offline baselines fall below provisional floors
"""
import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app.core import providers
from app.core.config import settings
from app.modules.ai import llm
from benchmarks import scoring
from benchmarks.baselines import AnthropicExtractor, RegexExtractor

DATA = Path(__file__).parent / "data"
HERE = Path(__file__).parent


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / name).read_text().splitlines() if line.strip()]


def verify_manifest() -> dict:
    m = json.loads((DATA / "MANIFEST.json").read_text())
    for name, meta in m["files"].items():
        got = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        if got != meta["sha256"]:
            raise SystemExit(f"benchmark data changed without a manifest update: {name}")
    return m


def pct(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(p * (len(vals) - 1))))]


class Meter:
    def __init__(self):
        self.lat, self.tin, self.tout, self.calls = [], 0, 0, 0

    def call(self, provider, context):
        t = time.perf_counter()
        r = provider.draft("five_whys_fishbone", context)
        self.lat.append(time.perf_counter() - t)
        self.tin += r.input_tokens
        self.tout += r.output_tokens
        self.calls += 1
        return r.output

    def summary(self) -> dict:
        cost = (self.tin * settings.ai_input_usd_per_mtok + self.tout * settings.ai_output_usd_per_mtok) / 1e6
        return {"calls": self.calls, "latency_p50_s": round(pct(self.lat, .5), 3) if self.lat else None,
                "latency_p95_s": round(pct(self.lat, .95), 3) if self.lat else None,
                "input_tokens": self.tin, "output_tokens": self.tout, "est_cost_usd": round(cost, 4),
                "est_cost_per_case_usd": round(cost / self.calls, 5) if self.calls else None}


def run_grounding(index, provider, repeats: int, max_cases: int | None) -> dict:
    cases = load("grounding.jsonl")
    if max_cases:
        cases = cases[:max_cases]
    meter, results, agree = Meter(), [], []
    for c in cases:
        ctx = scoring.build_context(index, c)
        runs, first = [], None
        for _ in range(repeats):
            raw = meter.call(provider, ctx)
            first = first or raw
            runs.append(set(scoring.cited_ids(raw)))
        results.append(scoring.score_case(c, ctx, first))
        a = scoring.agreement(runs)
        if a is not None:
            agree.append(a)
    agg = scoring.aggregate_grounding(results)
    agg["run_agreement"] = statistics.mean(agree) if agree else None
    return {"metrics": agg, "cost": meter.summary()}


def run_injection(index, provider, max_cases: int | None) -> dict:
    cases = {c["id"]: c for c in load("grounding.jsonl")}
    rows = load("injection.jsonl")[: max_cases or None]
    meter, res = Meter(), []
    for inj in rows:
        base = cases[inj["base_case"]]
        ctx = scoring.inject(base, scoring.build_context(index, base), inj)
        raw = meter.call(provider, ctx)
        res.append(scoring.score_injection(raw, inj, llm.allowed_source_ids(ctx)))
    by_loc = {}
    for loc in sorted({r["location"] for r in res}):
        sub = [r for r in res if r["location"] == loc]
        by_loc[loc] = sum(r["success"] for r in sub) / len(sub)
    return {"metrics": {"n": len(res), "attack_success_rate": sum(r["success"] for r in res) / len(res),
                        "canary_rate": sum(r["canary"] for r in res) / len(res),
                        "forged_citation_rate": sum(r["forged"] for r in res) / len(res), "by_location": by_loc},
            "cost": meter.summary()}


def run_all(draft_provider, extractor, repeats=1, max_cases=None, max_extract=None) -> dict:
    manifest = verify_manifest()
    index = scoring.Index(load("corpus.jsonl"))
    ext_rows = load("extraction.jsonl")
    if max_extract:
        keep = {r["base_id"] for r in ext_rows if r["noise_level"] == 0}
        keep = set(sorted(keep)[:max_extract])
        ext_rows = [r for r in ext_rows if r["base_id"] in keep]
    return {
        "meta": {"benchmark": manifest["benchmark"], "version": manifest["version"], "data_hashes": {k: v["sha256"][:12] for k, v in manifest["files"].items()},
                 "review_status": manifest["review_status"], "provenance": manifest["provenance"]["origin"],
                 "draft_provider": getattr(draft_provider, "name", "?"), "extractor": getattr(extractor, "name", "?"),
                 "model": getattr(draft_provider, "model", None), "embedder": providers.embedder.name, "repeats": repeats,
                 "run_at": datetime.now(UTC).isoformat(timespec="seconds")},
        "retrieval": scoring.score_retrieval(index, load("retrieval.jsonl")),
        "grounding": run_grounding(index, draft_provider, repeats, max_cases),
        "injection": run_injection(index, draft_provider, max_cases),
        "extraction": scoring.score_extraction(extractor, ext_rows),
    }


# ----------------------------------------------------------------------------- gates
def flatten(report: dict) -> dict:
    g, i, e = report["grounding"]["metrics"], report["injection"]["metrics"], report["extraction"]
    return {
        "retrieval.fact_recall@3": report["retrieval"]["fact_recall@3"], "retrieval.false_positive_rate": report["retrieval"]["false_positive_rate"],
        "grounding.citation_validity": g["citation_validity"], "grounding.evidence_recall": g["evidence_recall"],
        "grounding.hallucination_rate_unanswerable": g["hallucination_rate_unanswerable"],
        "injection.attack_success_rate": i["attack_success_rate"],
        "extraction.noise_0.all_fields": e["noise_0"]["all_fields"], "extraction.hard_noise_0.all_fields": e["hard_noise_0"]["all_fields"], "extraction.noise_0.event_type_macro_f1": e["noise_0"]["event_type_macro_f1"],
        "extraction.robustness_drop_all_fields": e["robustness_drop_all_fields"],
    }


def check(report: dict, rules: dict) -> list[str]:
    flat, bad = flatten(report), []
    for key, rule in rules.items():
        if key.startswith("_"):
            continue
        v = flat.get(key)
        if v is None:
            bad.append(f"{key}: not measured")
        elif "min" in rule and v < rule["min"]:
            bad.append(f"{key}: {v:.3f} < floor {rule['min']}")
        elif "max" in rule and v > rule["max"]:
            bad.append(f"{key}: {v:.3f} > ceiling {rule['max']}")
    return bad


def markdown(report: dict) -> str:
    f = lambda v: "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))  # noqa: E731
    m = report["meta"]
    lines = [f"# Benchmark report - {m['draft_provider']} / {m['extractor']}",
             f"*{m['benchmark']} v{m['version']} - {m['provenance']} data - {m['review_status']}*", "",
             "| Metric | Value |", "|---|---|"]
    for k, v in flatten(report).items():
        lines.append(f"| {k} | {f(v)} |")
    c = report["grounding"]["cost"]
    lines += ["", f"Draft calls: {c['calls']}, p50 {f(c['latency_p50_s'])}s, p95 {f(c['latency_p95_s'])}s, est. ${f(c['est_cost_usd'])} "
              f"(${f(c['est_cost_per_case_usd'])}/case); run agreement {f(report['grounding']['metrics']['run_agreement'])}"]
    return "\n".join(lines)


def make_provider(name: str):
    if name == "local":
        return llm.LocalProvider()
    if name == "anthropic":
        p = llm.external_provider_factory()
        if p is None:
            raise SystemExit("no Anthropic API key configured (VERAPLEX_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY)")
        return p
    raise SystemExit(f"unknown provider {name}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", default="local", choices=["local", "anthropic"])
    ap.add_argument("--extract", default="regex", choices=["regex", "anthropic"])
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--max-cases", type=int)
    ap.add_argument("--max-extract", type=int, help="limit extraction to the first N base reports (x3 noise levels)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true", help="enforce baseline floors (offline baselines only)")
    a = ap.parse_args(argv)
    external = a.draft == "anthropic" or a.extract == "anthropic"
    report = run_all(make_provider(a.draft), RegexExtractor() if a.extract == "regex" else AnthropicExtractor(),
                     a.repeats, a.max_cases, a.max_extract)
    thresholds = json.loads((HERE / "thresholds.json").read_text())
    print(markdown(report))
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        stamp = f"{a.draft}-{a.extract}"
        (a.out / f"report-{stamp}.json").write_text(json.dumps(report, indent=2, default=str))
        (a.out / f"report-{stamp}.md").write_text(markdown(report))
    if a.check:
        bad = check(report, thresholds["baseline_floor"])
        for b in bad:
            print("FAIL", b)
        return 1 if bad else 0
    if external:
        gaps = check(report, thresholds["tier2_targets"])
        print("\nTier 2 targets (provisional, informational):", "ALL MET" if not gaps else "")
        for g in gaps:
            print("  not met -", g)
    return 0


if __name__ == "__main__":
    sys.exit(main())
