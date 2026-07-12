import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const python = process.env.PA_FEITIAN_PYTHON;
const rawRoot = process.env.QUANT_DATA_ROOT;
const pairedRepo = process.env.PAIRED_REPO;
assert.ok(python, "PA_FEITIAN_PYTHON is required");
assert.ok(rawRoot, "QUANT_DATA_ROOT is required");
assert.ok(pairedRepo, "PAIRED_REPO is required");

const packetPath = "doc/repro/pa-feitian-m6-raw-availability-2026-07-12/raw_availability_blocker_v1.json";
const provenancePath = "doc/repro/pa-feitian-m6-continuous-provenance-2026-07-11/continuous_provenance_manifest_v1.json";
const protocolPath = "docs/research/pa-feitian-m6-historical-asof-protocol-v1.json";
const digest = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
const bytes = (path) => readFileSync(resolve(repoRoot, path));
const json = (path) => JSON.parse(bytes(path).toString("utf8"));

assert.equal(digest(bytes(packetPath)), "sha256:a0f9b91b86b33bfdf97d9fc325435a8b8f6cdf8925eb5464edbea9c3494939ee");
assert.equal(digest(bytes(provenancePath)), "sha256:a239a15d7f11bfacac0565a32e6f6bb5895ff8c5815cf5138926722590ffd3a3");
assert.equal(digest(bytes(protocolPath)), "sha256:1ee6e334ada94fa928d311f3d7992d1708e4334c5b16e8e39b51ffedafcd7a1d");
assert.doesNotMatch(bytes(packetPath).toString("utf8"), /\/(?:home|mnt|Users)\//, "packet path hygiene");

const packet = json(packetPath);
assert.equal(packet.hermes_task, "t_550fa726");
assert.equal(packet.result, "deterministic_blocker_retaining_quarantine");
assert.equal(packet.raw_inputs.length, 210);
assert.equal(new Set(packet.raw_inputs.map((row) => row.path)).size, 210);
assert.equal(packet.gap_summary.inputs_with_complete_evidence, 0);
assert.equal(packet.gap_summary.inputs_with_gaps, 210);
assert.ok(packet.raw_inputs.every((row) => row.status === "quarantined"));
assert.ok(packet.raw_inputs.every((row) => row.historical_as_of_availability === "unproven"));
assert.ok(packet.raw_inputs.every((row) => !row.filesystem_timestamps_accepted_as_provenance));
assert.deepEqual(packet.roll_schedule_audit.map((row) => row.session_prefixes_checked), [1313, 1313]);
assert.ok(packet.roll_schedule_audit.every((row) => row.prefix_failures === 0));
assert.equal(packet.capability_boundary.raw_acquisition_and_historical_availability, "quarantined");
assert.equal(packet.capability_boundary.embedded_main_month_is_roll, "quarantined");
assert.equal(packet.capability_boundary.underlying_candidates_eligible_for_score_today, false);
assert.equal(packet.capability_boundary.performance_evaluation_allowed, false);
assert.equal(packet.capability_boundary.iv_or_regime_promotion_attempted, false);
assert.equal(packet.capability_boundary.advance_m7, false);
assert.equal(packet.capability_boundary.execution_change_allowed, false);

const source = bytes("src/engine/pa_feitian/raw_availability.py").toString("utf8");
assert.doesNotMatch(source, /\bdate\.today\s*\(/, "implicit date.today");
assert.doesNotMatch(source, /\bdatetime\.(?:now|utcnow)\s*\(/, "implicit now");
assert.doesNotMatch(source, /\.glob\s*\(/, "raw directory discovery");
assert.doesNotMatch(source, /\.stat\s*\(/, "filesystem timestamp provenance");

const output = execFileSync(
  python,
  [
    "src/scripts/verify_pa_feitian_raw_availability.py",
    "--packet", packetPath,
    "--provenance", provenancePath,
    "--raw-root", rawRoot,
    "--paired-repo", pairedRepo,
  ],
  { cwd: repoRoot, env: { ...process.env, PYTHONPATH: "src" }, encoding: "utf8" },
);
const result = JSON.parse(output);
assert.equal(result.ok, true);
assert.equal(result.raw_inputs, 210);
assert.equal(result.inputs_with_complete_evidence, 0);
assert.equal(result.session_prefixes_checked, 2626);
assert.equal(result.quarantine_retained, true);
assert.equal(result.advance_m7, false);
console.log(JSON.stringify(result));
