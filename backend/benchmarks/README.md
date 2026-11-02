# VeraPlex pharma benchmark (v0.1.0)

Measures whether a model or pipeline is fit to draft quality records. It follows the evaluation section of the build plan: scored per capability, with deployment gates, and with unanswerable and adversarial cases included.

> **Status: synthetic and unreviewed.** Every record was authored for this benchmark. No gold label has been checked by a pharmaceutical SME or QA lead, and no real, public-domain or customer data is included yet. Treat results as engineering signal, not evidence of GxP fitness.

## Tasks

| Task | Data | What is scored |
|---|---|---|
| **Retrieval** | 16 invented SOPs; 32 paraphrased answerable queries + 8 unanswerable | fact recall@1/3/5 (the retrieved chunk must contain the gold fact), MRR, abstention / false-positive rate on queries with no SOP |
| **Grounded drafting** | 24 deviations (16 answerable, 8 with nothing in the records that explains the cause); half the answerable ones have a related prior event, half the unanswerable ones a distractor | citation validity (fabricated ids), evidence recall (overall and given the gold SOP was retrieved), suggested-SOP precision, claim support rate, **hallucination rate on unanswerable cases** (a confident answer to "why" 2-5 with no record to support it), gap-reporting rate, run-to-run agreement, latency, tokens, cost |
| **Prompt injection** | 12 cases: instructions hidden in the deviation text, a prior event, or an SOP passage (canary token, forged citation id, fake `</source>` tags) | attack success rate overall and by location |
| **Extraction / classification** | 78 reports x 3 noise levels (clean, light OCR noise, heavy): 60 templated "easy" and 18 "hard" narratives with a distractor unit and no obvious keywords | per-field exact match (equipment, batch, area, event type), event-type macro-F1, accuracy drop under noise |

The drafting task runs the **production** prompt, escaping, schema and `validate_draft` code paths against the benchmark corpus, so a model is scored on what would actually ship. Scoring uses the model's *raw* output (before validation), so the benchmark measures the model, while production adds the validator on top.

## Running

```bash
cd backend
python -m benchmarks.run                          # offline baselines, free
python -m benchmarks.run --check                  # CI gate: baselines must not regress below thresholds.json floors
python -m benchmarks.run --draft anthropic --extract anthropic --repeats 3 --out benchmarks/reports
                                                  # real model; costs money; needs VERAPLEX_ANTHROPIC_API_KEY
python -m benchmarks.run --draft anthropic --max-cases 6 --max-extract 6    # cheap smoke run
python -m benchmarks.build_dataset                # regenerate data (deterministic, seeded) and the manifest
```

`data/MANIFEST.json` records row counts and SHA-256 per file; the runner refuses to run if data changed without a manifest update. Tests prove the generator reproduces the committed files.

## Offline baseline results (v0.1.0)

| Metric | Baseline | Meaning |
|---|---|---|
| retrieval fact recall@3 | 0.69 | The offline lexical embedder struggles with paraphrase; this is the number a real embedder must beat |
| unanswerable false-positive rate | 0.38 | 3 of 8 off-topic queries still return a weak match above the 0.08 score cut-off |
| extraction (easy, clean) | 0.77 all fields | |
| extraction (hard, clean) | 0.00 | distractor equipment and keyword-free phrasing defeat the regex baseline |
| accuracy drop under heavy noise | 0.22 | |
| grounded drafting / injection | 1.00 validity, 0.00 hallucination, 0.00 attack success | trivially true for the local provider, which makes no claims |

The local provider is a floor for *safety* metrics, not a quality bar: it is safe because it says almost nothing. A model is only interesting if it keeps those safety numbers while raising evidence recall and extraction accuracy.

## Gates

`thresholds.json` holds two sets of **provisional** numbers:

- `baseline_floor`: regression guard on the offline baselines, enforced in CI.
- `tier2_targets`: what a model should reach before being considered for Tier 2 (drafts for regulated records). Informational on model runs. **The plan requires these numbers to be set with the QA lead; the current values are the author's placeholders.** Tier 3 (controlled decisions) has no gate because no model may deploy there.

## Known limitations

- **Authored by an LLM, unreviewed.** Labels and "facts" may contain errors or unrealistic phrasing that a domain expert would catch. Synthetic text is more regular than real deviation reports; the templated extraction set saturates easily (the hard subset exists for that reason).
- **Small.** Dozens of cases per task: results carry wide uncertainty; a single case moves rates by 4-12 points. Do not rank models on small differences.
- **Lexical contamination risk.** Queries were written against the same wording as the SOPs, partly paraphrased. Retrieval numbers say little about real corpora.
- **No scanned-document robustness.** Noise is character-level OCR-style corruption of text, not real scans, layouts or tables.
- **Not covered yet:** summarisation fidelity (long SOPs), regulatory reasoning, forecasting/anomaly detection, multilingual input, bias, and any customer-specific vocabulary.
- **Public-domain material is not included.** FDA guidance and warning letters are US government works and are the intended next source, but they must be ingested with a reviewed provenance entry (source URL, retrieval date, licence note, hash) before being scored. Do not add customer data without recorded written permission.
- Model rows (`--draft anthropic`) have **never been run**: no API key was available when this was built.
