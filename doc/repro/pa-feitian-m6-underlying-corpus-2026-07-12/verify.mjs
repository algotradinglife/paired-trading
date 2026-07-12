import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = path.resolve(import.meta.dirname, "../../..");
const python = process.env.PA_FEITIAN_PYTHON;
const rawRoot = process.env.QUANT_DATA_ROOT;
const quantRepo = process.env.QUANT_REPO;
const pairedRepo = process.env.PAIRED_REPO;
assert.ok(python, "PA_FEITIAN_PYTHON is required");
assert.ok(rawRoot, "QUANT_DATA_ROOT is required");
assert.ok(quantRepo, "QUANT_REPO is required");
assert.ok(pairedRepo, "PAIRED_REPO is required");

const relative = "doc/repro/pa-feitian-m6-underlying-corpus-2026-07-12/underlying_signal_corpus_v1.json";
const bytes = fs.readFileSync(path.join(root, relative));
const digest = `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`;
assert.equal(digest, "sha256:cb3407910dd15f4327a2465da3a00d6797f81fd9124066695887ddb53d3bf080");
const artifact = JSON.parse(bytes);
assert.equal(artifact.schema_version, "pa_feitian_m6_underlying_signal_corpus_v1");
assert.equal(artifact.research_mode, "retrospective_finalized");
assert.equal(artifact.coverage.included_records, 670);
assert.equal(artifact.coverage.supported_series, 2680);
assert.equal(artifact.coverage.excluded_decisions, 18);
assert.deepEqual(artifact.coverage.exclusion_reasons, { missing_15_00_source_bar: 18 });
assert.equal(artifact.guardrails.implicit_current_time, false);
assert.equal(artifact.guardrails.directory_or_catalog_discovery, false);
assert.equal(artifact.guardrails.future_rows_allowed, false);
assert.equal(artifact.guardrails.downstream_promotion, false);

const result = spawnSync(
  python,
  [
    "src/scripts/verify_pa_feitian_underlying_corpus.py",
    "--contract", "docs/research/pa-feitian-m6-underlying-corpus-contract-v1.json",
    "--provenance", "doc/repro/pa-feitian-m6-continuous-provenance-2026-07-11/continuous_provenance_manifest_v1.json",
    "--raw-root", rawRoot,
    "--quant-repo", quantRepo,
    "--paired-repo", pairedRepo,
    "--artifact", relative,
  ],
  { cwd: root, encoding: "utf8", env: { ...process.env, PYTHONPATH: "src" } },
);
if (result.status !== 0) {
  process.stderr.write(result.stderr);
  process.stdout.write(result.stdout);
}
assert.equal(result.status, 0);
const verified = JSON.parse(result.stdout);
assert.equal(verified.ok, true);
assert.equal(verified.records, 670);
assert.equal(verified.supported_series, 2680);
assert.equal(verified.corpus_payload_sha256, "sha256:3a0078d4bd2bb2f141b8175479afad6554a705b538796e59a7ab8e69effafe02");
assert.equal(verified.operational_observability, "blocked");
assert.equal(verified.future_row_invariance, true);
assert.equal(verified.hidden_current_time_or_discovery, false);
assert.equal(verified.advance_m7, false);
console.log(JSON.stringify(verified));
