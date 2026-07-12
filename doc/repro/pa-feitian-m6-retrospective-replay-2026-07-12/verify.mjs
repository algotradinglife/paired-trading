import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const python = process.env.PA_FEITIAN_PYTHON;
assert.ok(python, "PA_FEITIAN_PYTHON is required");

const paths = {
  contract: "docs/research/pa-feitian-m6-epistemic-replay-contract-v1.json",
  artifact: "doc/repro/pa-feitian-m6-retrospective-replay-2026-07-12/retrospective_replay_evidence_v1.json",
  protocol: "docs/research/pa-feitian-m6-historical-asof-protocol-v1.json",
  historicalAudit: "doc/repro/pa-feitian-m6-historical-asof-2026-07-11/coverage_feasibility_audit_v1.json",
  provenance: "doc/repro/pa-feitian-m6-continuous-provenance-2026-07-11/continuous_provenance_manifest_v1.json",
  availability: "doc/repro/pa-feitian-m6-raw-availability-2026-07-12/raw_availability_blocker_v1.json",
};
const expected = {
  contract: "sha256:f6f3daa7a1dae99bc2e69a5a3471802173fad1f1333c814ec1152802592a0290",
  artifact: "sha256:eaeb6c3fffa93115c4fc7a0f8b86abbabed5e776bdd8f3c139826150f51a12fb",
  protocol: "sha256:1ee6e334ada94fa928d311f3d7992d1708e4334c5b16e8e39b51ffedafcd7a1d",
  historicalAudit: "sha256:3639f224e41e5fe205184088a0a0724529b2a6fc005d8e2d5410dbb5d20c07f8",
  provenance: "sha256:a239a15d7f11bfacac0565a32e6f6bb5895ff8c5815cf5138926722590ffd3a3",
  availability: "sha256:a0f9b91b86b33bfdf97d9fc325435a8b8f6cdf8925eb5464edbea9c3494939ee",
};
const bytes = (path) => readFileSync(resolve(repoRoot, path));
const digest = (value) => `sha256:${createHash("sha256").update(value).digest("hex")}`;

for (const [name, path] of Object.entries(paths)) {
  assert.equal(digest(bytes(path)), expected[name], `${name} hash drift`);
}

const artifact = JSON.parse(bytes(paths.artifact).toString("utf8"));
assert.equal(artifact.hermes_task, "t_23c01908");
assert.equal(artifact.acquisition_metadata.complete_inputs, 0);
assert.equal(artifact.acquisition_metadata.append_only_manifest_milestone, "M8");
assert.equal(artifact.mode_results.retrospective_finalized.status, "enabled_with_explicit_limitations");
assert.equal(artifact.mode_results.retrospective_finalized.missing_acquisition_metadata_is_blocker, false);
assert.equal(artifact.mode_results.retrospective_finalized.causal_roll_schedule_reuse, true);
assert.equal(artifact.mode_results.operational_observability.status, "blocked");
assert.equal(artifact.mode_results.operational_observability.missing_acquisition_metadata_is_blocker, true);
assert.equal(artifact.mode_results.operational_observability.causal_roll_schedule_reuse, false);
assert.equal(artifact.decision_gates.length, 4);
assert.ok(artifact.decision_gates.every((row) => row.contract_reselection === false));
assert.ok(artifact.decision_gates.every((row) => row.limitations.length === 4));
assert.ok(Object.values(artifact.promotion).every((value) => value === false));

const source = bytes("src/engine/pa_feitian/retrospective_replay.py").toString("utf8");
assert.doesNotMatch(source, /\bdate\.today\s*\(/, "implicit date.today");
assert.doesNotMatch(source, /\bdatetime\.(?:now|utcnow)\s*\(/, "implicit current time");
assert.doesNotMatch(source, /\.glob\s*\(/, "directory discovery");

const output = execFileSync(
  python,
  [
    "src/scripts/verify_pa_feitian_m6_retrospective_replay.py",
    "--contract", paths.contract,
    "--artifact", paths.artifact,
    "--protocol", paths.protocol,
    "--historical-audit", paths.historicalAudit,
    "--provenance", paths.provenance,
    "--availability", paths.availability,
  ],
  { cwd: repoRoot, env: { ...process.env, PYTHONPATH: "src" }, encoding: "utf8" },
);
const result = JSON.parse(output);
assert.equal(result.ok, true);
assert.equal(result.retrospective_finalized, "enabled_with_explicit_limitations");
assert.equal(result.operational_observability, "blocked");
assert.equal(result.acquisition_manifest_milestone, "M8");
assert.equal(result.advance_m7, false);
console.log(JSON.stringify(result));
