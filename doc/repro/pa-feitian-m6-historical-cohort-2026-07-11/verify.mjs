import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const python = process.env.PA_FEITIAN_PYTHON;
const quantDataRoot = process.env.QUANT_DATA_ROOT;
assert.ok(python, "PA_FEITIAN_PYTHON is required");
assert.equal(
  quantDataRoot,
  "/mnt/c/Users/hhusl/quant_data",
  "QUANT_DATA_ROOT must use the frozen runtime root",
);

const protocol = "docs/research/pa-feitian-m6-historical-cohort-protocol-v1.json";
const packet = "doc/repro/pa-feitian-m6-historical-cohort-2026-07-11";
const files = {
  [protocol]: "sha256:26334611239774812ebc42aa824aa6cf1a406e683110e57ee22ab72a78201cf9",
  [`${packet}/coverage_audit_v1.json`]: "sha256:3091610774d7210bbbfda1b7e5a4be1d70a6da2ecdb7302b45e36cd8d5509cf1",
  [`${packet}/premium_outcome_baseline_50pct_v1.json`]: "sha256:71e34e7fa1844f9138e38c19bd5f668b5ee293b25fdef8505861f2a44accf598",
  [`${packet}/premium_outcome_candidate_30pct_v1.json`]: "sha256:5114c9b3ddc256907fd18738baa0acb82fe11f058861f3dc1856b1c7d32c04e4",
  [`${packet}/historical_cohort_report_v1.json`]: "sha256:b989da4fd1bbcf349993a27ec7d3d863aef29574dcb8ec1a3ac488b463e4556e",
};

function bytes(path) {
  return readFileSync(resolve(repoRoot, path));
}

function json(path) {
  return JSON.parse(bytes(path).toString("utf8"));
}

function sha256(path) {
  return `sha256:${createHash("sha256").update(bytes(path)).digest("hex")}`;
}

for (const [path, expected] of Object.entries(files)) {
  assert.equal(sha256(path), expected, `${path} pinned hash`);
  assert.doesNotMatch(bytes(path).toString("utf8"), /\/(?:home|mnt|Users)\//, `${path} public path hygiene`);
}

const report = json(`${packet}/historical_cohort_report_v1.json`);
const audit = json(`${packet}/coverage_audit_v1.json`);
assert.deepEqual(report.coverage_funnel, {
  eligible_rows: 4,
  excluded_rows: 9,
  exclusions_by_reason: {
    missing_rank1_selected_option_contract: 2,
    outside_frozen_universe: 7,
  },
  source_rows: 13,
});
assert.equal(report.pooled_descriptive.comparable_event_count, 4);
assert.equal(report.pooled_descriptive.inferential_use_allowed, false);
assert.equal(report.threshold_gates.grouped_results.emitted, false);
assert.equal(report.threshold_gates.oos_results.emitted, false);
assert.equal(report.threshold_gates.screening.classification, "insufficient_sample");
assert.equal(report.threshold_gates.screening.advance_m7, false);
assert.equal(audit.rows.length, 13);
assert.equal(audit.bounded_contract_count, 4);
assert.equal(audit.guardrails.raw_directory_glob, false);
assert.deepEqual(report.policy_status_counts, {
  baseline: { observed: 4 },
  candidate: { observed: 4 },
});

const temp = mkdtempSync(join(tmpdir(), "pa-feitian-m6-hist-"));
try {
  const rebuilt = {
    audit: join(temp, "audit.json"),
    baseline: join(temp, "baseline.json"),
    candidate: join(temp, "candidate.json"),
    report: join(temp, "report.json"),
  };
  execFileSync(
    python,
    [
      "src/scripts/build_pa_feitian_historical_cohort.py",
      "--protocol", protocol,
      "--quant-data-root", quantDataRoot,
      "--audit-out", rebuilt.audit,
      "--baseline-out", rebuilt.baseline,
      "--candidate-out", rebuilt.candidate,
      "--report-out", rebuilt.report,
      "--generated-at-utc", "2026-07-11T13:30:00Z",
      "--source-commit", "c6225aa567d7115d96a2dc4b4d298ce7b667f33b",
    ],
    { cwd: repoRoot, env: { ...process.env, PYTHONPATH: "src" }, stdio: "pipe" },
  );
  for (const [rebuiltPath, committedPath] of [
    [rebuilt.audit, `${packet}/coverage_audit_v1.json`],
    [rebuilt.baseline, `${packet}/premium_outcome_baseline_50pct_v1.json`],
    [rebuilt.candidate, `${packet}/premium_outcome_candidate_30pct_v1.json`],
    [rebuilt.report, `${packet}/historical_cohort_report_v1.json`],
  ]) {
    assert.deepEqual(readFileSync(rebuiltPath), bytes(committedPath), `${committedPath} deterministic rebuild`);
  }
  execFileSync(
    python,
    [
      "-c",
      [
        "from engine.pa_feitian.premium_outcome import load_premium_outcome",
        `load_premium_outcome('${rebuilt.baseline}')`,
        `load_premium_outcome('${rebuilt.candidate}')`,
      ].join(";"),
    ],
    { cwd: repoRoot, env: { ...process.env, PYTHONPATH: "src" }, stdio: "pipe" },
  );
} finally {
  rmSync(temp, { recursive: true, force: true });
}

console.log(JSON.stringify({
  ok: true,
  task: "t_b68066e4",
  source_rows: 13,
  eligible: 4,
  excluded: 9,
  paired_events: 4,
  gate: "insufficient_sample",
  grouped_emitted: false,
  oos_emitted: false,
}));
