import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const python = process.env.PA_FEITIAN_PYTHON;
const quantDataRoot = process.env.QUANT_DATA_ROOT;

if (!python) throw new Error("PA_FEITIAN_PYTHON is required");
if (!quantDataRoot) throw new Error("QUANT_DATA_ROOT is required");
const dailyDir = resolve(quantDataRoot, "daily");
if (!existsSync(dailyDir) || !statSync(dailyDir).isDirectory()) {
  throw new Error("QUANT_DATA_ROOT/daily must be an existing directory");
}
assert.deepEqual(readdirSync(dailyDir), [], "blocked packet requires the inspected empty daily root");

const config = JSON.parse(readFileSync(resolve(packetDir, "candidate_availability_v1.json")));

function run(args) {
  execFileSync(python, args, {
    cwd: repoRoot,
    env: { ...process.env, PYTHONPATH: "src" },
    stdio: "pipe",
  });
}

function json(relativePath) {
  return JSON.parse(readFileSync(resolve(packetDir, relativePath)));
}

function sha256(relativePath) {
  return "sha256:" + createHash("sha256").update(readFileSync(resolve(packetDir, relativePath))).digest("hex");
}

function validatePythonContracts() {
  const files = Object.keys(config.artifact_sha256).map((relativePath) => resolve(packetDir, relativePath));
  const code = `
from engine.pa_feitian.evaluation import (
    load_evaluation_aggregate_result, load_evaluation_dataset,
)
from engine.pa_feitian.manifest import load_run_manifest
from pathlib import Path
for raw in ${JSON.stringify(files)}:
    path = Path(raw)
    if "run_manifest" in path.name:
        load_run_manifest(path)
    elif "evaluation_dataset" in path.name:
        load_evaluation_dataset(path)
    else:
        load_evaluation_aggregate_result(path)
print("python_contracts_ok")
`;
  run(["-c", code]);
}

assert.equal(config.schema_version, "pa_feitian_m6_candidate_availability_v1");
assert.equal(config.classification, "retrospective_exploratory_blocked_evidence");
assert.equal(config.not_prospective_preregistration, true);
assert.equal(config.comparison_artifacts_generated, false);
assert.equal(config.dashboard_copies_generated, false);
assert.equal(config.automatic_strategy_approval, false);
assert.equal(config.candidate_evaluation.status, "data_blocked");
assert.equal(config.candidate_evaluation.raw_premium_path_reproducible, false);
assert.equal(config.candidate_evaluation.m5_candidate_sidecar_generated, false);
assert.equal(config.candidate_evaluation.m6_candidate_artifacts_generated, false);
assert.equal(config.candidate_evaluation.recovery_requirement.selected_contracts.length, 4);

run([
  "src/scripts/evaluate_pa_feitian_m6_baseline.py",
  "--m5-manifest", config.baseline.source_m5_manifest,
  "--premium-outcome", config.baseline.premium_outcome,
  "--decision-intent", "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_decision_intent_v1.json",
  "--dataset-out", "doc/repro/pa-feitian-m6-real-evidence-2026-07-11/source/pa_feitian_evaluation_dataset_baseline_v1.json",
  "--aggregate-out", "doc/repro/pa-feitian-m6-real-evidence-2026-07-11/source/pa_feitian_evaluation_aggregate_result_baseline_v1.json",
  "--manifest-out", "doc/repro/pa-feitian-m6-real-evidence-2026-07-11/source/pa_feitian_run_manifest_baseline_evaluation_v1.json",
  "--generated-at-utc", "2026-07-11T00:00:00Z",
  "--seed", "7", "--bootstrap-replicates", "1000", "--lower-quantile", "0.05",
  "--minimum-effective-samples", "3", "--folds", "2", "--minimum-train-events", "1",
  "--timezone", "UTC", "--trading-calendar", "XSGE",
]);

validatePythonContracts();
for (const [relativePath, expectedHash] of Object.entries(config.artifact_sha256)) {
  assert.equal(sha256(relativePath), expectedHash, `hash mismatch: ${relativePath}`);
}

const baseline = json(config.baseline.evaluation_aggregate_result);
const pooled = baseline.groups.find((group) => group.dimension === "pooled");
assert.deepEqual(pooled.status_counts, config.baseline.expected_status_counts);
assert.equal(pooled.result_status, "generated");
assert.equal(pooled.effective_sample_count, 4);
assert.equal(pooled.premium_r.win_rate, 0);

for (const file of ["README.md", "candidate_availability_v1.json", "verify.mjs", ...Object.keys(config.artifact_sha256)]) {
  const contents = readFileSync(resolve(packetDir, file), "utf8");
  assert.ok(!contents.includes(quantDataRoot), `runtime root leaked into ${file}`);
  assert.ok(!contents.includes("/home/" + "drwho1985"), `machine-local path leaked into ${file}`);
}

console.log(JSON.stringify({ ok: true, candidate_evidence: "data_blocked_unavailable" }));
