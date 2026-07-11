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
  [protocol]: "sha256:33a2a32a436a1b1ca8921809b86724ce7401672681952aac510b3375cf039875",
  [`${packet}/coverage_audit_v1.json`]: "sha256:90ed911fcbd0c664979a93307906e98db8531269f3e71b8cb9e635a01051c701",
  [`${packet}/premium_outcome_baseline_50pct_v1.json`]: "sha256:71e34e7fa1844f9138e38c19bd5f668b5ee293b25fdef8505861f2a44accf598",
  [`${packet}/premium_outcome_candidate_30pct_v1.json`]: "sha256:5114c9b3ddc256907fd18738baa0acb82fe11f058861f3dc1856b1c7d32c04e4",
  [`${packet}/historical_cohort_report_v1.json`]: "sha256:f48952da3046161b2c21249c164c2caae206c66cbcac0662324cc9d210bf9e46",
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
assert.equal(report.research_interpretation.evaluated_track.name, "legacy_m5_integration_control");
assert.equal(report.research_interpretation.evaluated_track.faithful_feitian_hypothesis, false);
assert.equal(
  report.research_interpretation.faithful_hypothesis_track.status,
  "coverage_gap_not_evaluated",
);
assert.match(
  report.research_interpretation.faithful_hypothesis_track.packet_conclusion,
  /neither tests nor refutes/,
);
assert.equal(report.research_interpretation.upstream_research.documents.length, 4);
assert.equal(report.research_interpretation.upstream_performance_metrics_imported, false);

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
