# Offline Quality Baseline

`benchmarks.quality_baseline` turns archived `ParsedDocument` JSON fixtures into
a deterministic, machine-readable parser-by-sample matrix. It does not call
Docling, MinerU, routing, Gateway, network services, or an LLM. The fixture's
`provenance.parser_id` is retained only as a reporting dimension; every sample
uses the same `quality.run_quality(document)` call.

## Run

From `document_parser/`, evaluate all archived quality fixtures and print JSON:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.quality_baseline --glob "tests/quality/fixtures/parsed_documents/*.json"
```

Write a report explicitly:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.quality_baseline `
  --glob "tests/quality/fixtures/parsed_documents/*.json" `
  --output benchmarks/quality_baseline/latest.json
```

An existing report is protected by default. Pass `--replace-existing` only when
the replacement is intentional.

## Report contract

The report is canonical JSON (`QualityBaselineReport` 1.0) with no timestamp or
machine-specific paths. It contains:

- one record for every parser × sample fixture, including fixture SHA-256;
- structural-completeness checks and a score based only on applicable contract
  checks (blocks, IDs, order, table links, and asset references);
- generic capability declarations, expected/undeclared/non-available evidence,
  and missing-capability count;
- unchanged quality gate state, issue counts by severity, repair count/rules,
  and quality capability summary;
- deterministic per-parser and overall summaries, including gate pass and
  manual-review rates (`pass` and `pass_with_warnings` are counted as pass).

The score is a contract completeness signal, not semantic ground truth or a
claim that one parser is better. Use it with a versioned fixture corpus and
human annotation before changing routing policy.
