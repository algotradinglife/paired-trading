import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { buildDashboardModel, renderDashboard } from "../../../frontend/pa-feitian-dashboard/app.mjs";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const python = process.env.PA_FEITIAN_PYTHON;
const quantDataRoot = process.env.QUANT_DATA_ROOT;

if (!python) throw new Error("PA_FEITIAN_PYTHON is required");
if (!quantDataRoot) throw new Error("QUANT_DATA_ROOT is required");

const files = [
  "SHFE.au2606C1152.parquet",
  "SHFE.au2606C1136.parquet",
  "SHFE.ag2607C19900.parquet",
  "SHFE.ag2608C18800.parquet",
];
for (const file of files) {
  assert.equal(statSync(resolve(quantDataRoot, "daily", file)).isFile(), true, `${file} is required`);
}

const root = "doc/repro/pa-feitian-m6-data-quality-recovery-2026-07-11";
const source = `${root}/source`;
const dashboard = `${root}/dashboard`;
const candidateOutcome = `${source}/pa_feitian_premium_outcome_candidate_stop_30pct_v1.json`;
const candidateManifest = `${source}/pa_feitian_run_manifest_candidate_stop_30pct_v1.json`;
const baselineDataset = `${source}/pa_feitian_evaluation_dataset_baseline_v1.json`;
const baselineAggregate = `${source}/pa_feitian_evaluation_aggregate_result_baseline_v1.json`;
const candidateDataset = `${source}/pa_feitian_evaluation_dataset_candidate_stop_30pct_v1.json`;
const candidateAggregate = `${source}/pa_feitian_evaluation_aggregate_result_candidate_stop_30pct_v1.json`;
const screening = `${source}/pa_feitian_evaluation_screening_report_v1.json`;
const failureReport = `${source}/failure_modes/candidate_stop_30pct_failure_mode_report.json`;

const expectedHashes = {
  [candidateOutcome]: "sha256:e3270e76178870dabf2f97424f4a01db93604d64458ee3c44eb4a0ed5f8a7d01",
  [candidateManifest]: "sha256:ed43e72651426a2ddc5938aa0f6a64fcaac44496884bec864388495b1833ad09",
  [baselineDataset]: "sha256:70bad7e48391b71eb3cb01ad7482e5938d26c58d47e5fd518fe3338179592d1c",
  [baselineAggregate]: "sha256:350d5bcdcada75fb25e5408db8c09c8e826a6f8d8319d7eb2858fa5b4c404e76",
  [candidateDataset]: "sha256:dad77b16a6fc2b660b050999c2411e0916550c2903c3f8b343bae15e20b5133b",
  [candidateAggregate]: "sha256:da447eef3aa3cb3067a4bb59a878f4bd3d5bebb36e7bfbefe81cd4072f6fc5a5",
  [screening]: "sha256:5b3d8d51f8e7aaddd6bee8e04ed264a8beff10a5e06de74af84c4ba908563a2a",
  [failureReport]: "sha256:7c8dc57ec27dbe083b143391521aa681ec9bd2016e0a11774631b1d6801c4709",
  [`${dashboard}/pa_feitian_run_manifest_candidate_stop_30pct_v1.json`]: "sha256:7ab1ad1d208e0ca30da2700c34cbf448eec70d3feae7c8b3ed8c78bc30eb7672",
  [`${dashboard}/pa_feitian_run_manifest_baseline_screening_v1.json`]: "sha256:e1bb530c419c48e5700009a625370a5d794da9514d81e2603274698453d2e8e4",
};

function run(args) {
  execFileSync(python, args, { cwd: repoRoot, env: { ...process.env, PYTHONPATH: "src" }, stdio: "pipe" });
}

function json(path) {
  return JSON.parse(readFileSync(resolve(repoRoot, path), "utf8"));
}

function sha256(path) {
  return "sha256:" + createHash("sha256").update(readFileSync(resolve(repoRoot, path))).digest("hex");
}

run([
  "src/scripts/build_pa_feitian_premium_outcomes.py",
  "--snapshot", "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_snapshot_v1.json",
  "--decision-intent", "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_decision_intent_v1.json",
  "--source-m4-manifest", "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_run_manifest_with_decision_intent_v1.json",
  "--quant-data-root", quantDataRoot, "--quant-data-root-label", "external://optionstore/quant-data",
  "--out", candidateOutcome, "--manifest-out", candidateManifest,
  "--frontend-outcome-copy", `${dashboard}/pa_feitian_premium_outcome_candidate_stop_30pct_v1.json`,
  "--generated-at-utc", "2026-07-11T12:00:00Z", "--policy-declared-at-utc", "2026-07-11T12:00:00Z",
  "--traversal-started-at-utc", "2026-07-11T12:01:00Z", "--source-commit", "67096c3c384e7bbcfda9721b7f36d8fe782801a2",
  "--policy-id", "pa_feitian_m6_daily_long_option_stop_30pct", "--policy-version", "v1.retro_20260711",
  "--stop-fraction-of-entry", "0.3", "--target-multiples-of-entry", "2.0", "--max-holding-bars", "10",
]);

for (const [manifest, outcome, dataset, aggregate, generatedAt] of [
  ["doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/source/pa_feitian_run_manifest_with_premium_outcome_v1.json", "doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/source/pa_feitian_premium_outcome_v1.json", baselineDataset, baselineAggregate, "2026-07-11T12:05:00Z"],
  [candidateManifest, candidateOutcome, candidateDataset, candidateAggregate, "2026-07-11T12:05:00Z"],
]) {
  run([
    "src/scripts/evaluate_pa_feitian_m6_baseline.py", "--m5-manifest", manifest, "--premium-outcome", outcome,
    "--decision-intent", "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_decision_intent_v1.json",
    "--dataset-out", dataset, "--aggregate-out", aggregate,
    "--manifest-out", dataset === baselineDataset ? `${source}/pa_feitian_run_manifest_baseline_evaluation_v1.json` : `${source}/pa_feitian_run_manifest_candidate_stop_30pct_evaluation_v1.json`,
    "--generated-at-utc", generatedAt, "--seed", "7", "--bootstrap-replicates", "1000", "--lower-quantile", "0.05",
    "--minimum-effective-samples", "3", "--folds", "2", "--minimum-train-events", "1", "--timezone", "UTC", "--trading-calendar", "XSGE",
  ]);
}

run([
  "src/scripts/compare_pa_feitian_m6_policies.py", "--baseline-dataset", baselineDataset,
  "--baseline-aggregate", baselineAggregate, "--comparison-config", `${root}/policy_comparison_config_v1.json`,
  "--candidate-input", "candidate_stop_30pct", candidateDataset, candidateAggregate,
  "--screening-out", screening, "--failure-report-dir", `${source}/failure_modes`, "--generated-at-utc", "2026-07-11T12:10:00Z",
]);
run([
  "src/scripts/build_pa_feitian_m6_dashboard_artifacts.py", "--source-manifest", candidateManifest,
  "--snapshot", "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/dashboard/pa_feitian_snapshot_v1.json",
  "--decision-intent", "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/dashboard/pa_feitian_decision_intent_v1.json",
  "--premium-outcome", candidateOutcome, "--evaluation-dataset", candidateDataset, "--evaluation-aggregate", candidateAggregate,
  "--failure-mode-report", failureReport, "--dashboard-dir", dashboard,
  "--manifest-out", `${dashboard}/pa_feitian_run_manifest_candidate_stop_30pct_v1.json`, "--generated-at-utc", "2026-07-11T12:15:00Z",
]);
run([
  "src/scripts/build_pa_feitian_m6_dashboard_artifacts.py",
  "--source-manifest", `${source}/pa_feitian_run_manifest_baseline_evaluation_v1.json`,
  "--snapshot", "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/dashboard/pa_feitian_snapshot_v1.json",
  "--decision-intent", "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/dashboard/pa_feitian_decision_intent_v1.json",
  "--premium-outcome", "doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/dashboard/pa_feitian_premium_outcome_v1.json",
  "--evaluation-dataset", baselineDataset, "--evaluation-aggregate", baselineAggregate,
  "--screening-report", screening, "--dashboard-dir", dashboard,
  "--manifest-out", `${dashboard}/pa_feitian_run_manifest_baseline_screening_v1.json`, "--generated-at-utc", "2026-07-11T12:15:00Z",
]);

for (const [path, expected] of Object.entries(expectedHashes)) assert.equal(sha256(path), expected, `${path} hash`);

const candidate = json(candidateOutcome);
assert.deepEqual(candidate.outcomes.map((outcome) => outcome.evaluation_status), ["observed", "observed", "observed", "observed"]);
assert.equal(candidate.outcomes[1].exit_reason, "time_exit");
assert.equal(candidate.outcomes[3].exit_reason, "premium_stop");
const report = json(screening).candidates[0];
assert.equal(report.classification, "inconclusive");
assert.equal(report.comparison.paired_effective_event_count, 4);
assert.equal(report.reviewer_status, "pending");
assert.match(report.classification_basis[0], /cannot advance M7/);
assert.match(report.limitations.at(-1), /retrospective exploratory comparison/);

const baselineRows = json(baselineDataset).rows;
const candidateRows = json(candidateDataset).rows;
const candidateRowsByEvent = new Map(candidateRows.map((row) => [row.event_id, row]));
const descriptiveDifferences = baselineRows.map(
  (row) => candidateRowsByEvent.get(row.event_id).premium_r - row.premium_r,
);
const mean = (values) => values.reduce((sum, value) => sum + value, 0) / values.length;
assert.equal(baselineRows.length, 4);
assert.equal(candidateRows.length, 4);
assert.equal(mean(baselineRows.map((row) => row.premium_r)), -1.0009036144499999);
assert.equal(mean(candidateRows.map((row) => row.premium_r)), -0.841500172225);
assert.equal(mean(descriptiveDifferences), 0.15940344222499997);

run(["-c", `
from engine.pa_feitian.evaluation import load_evaluation_aggregate_result, load_evaluation_dataset, load_evaluation_failure_mode_report, load_evaluation_screening_report
from engine.pa_feitian.manifest import load_run_manifest
from engine.pa_feitian.premium_outcome import load_premium_outcome
load_premium_outcome("${candidateOutcome}")
for path in ["${candidateManifest}", "${source}/pa_feitian_run_manifest_baseline_evaluation_v1.json", "${source}/pa_feitian_run_manifest_candidate_stop_30pct_evaluation_v1.json", "${dashboard}/pa_feitian_run_manifest_candidate_stop_30pct_v1.json", "${dashboard}/pa_feitian_run_manifest_baseline_screening_v1.json"]: load_run_manifest(path)
for path in ["${baselineDataset}", "${candidateDataset}"]: load_evaluation_dataset(path)
for path in ["${baselineAggregate}", "${candidateAggregate}"]: load_evaluation_aggregate_result(path)
load_evaluation_failure_mode_report("${failureReport}")
load_evaluation_screening_report("${screening}")
`]);

const dashboardSnapshot = json(`${dashboard}/pa_feitian_snapshot_v1.json`);
const dashboardManifest = json(`${dashboard}/pa_feitian_run_manifest_candidate_stop_30pct_v1.json`);
const options = {
  manifest: dashboardManifest,
  decisionIntent: json(`${dashboard}/pa_feitian_decision_intent_v1.json`),
  premiumOutcome: json(`${dashboard}/pa_feitian_premium_outcome_candidate_stop_30pct_v1.json`),
  evaluationDataset: json(`${dashboard}/pa_feitian_evaluation_dataset_candidate_stop_30pct_v1.json`),
  evaluationAggregate: json(`${dashboard}/pa_feitian_evaluation_aggregate_result_candidate_stop_30pct_v1.json`),
  evaluationFailureModes: json(`${dashboard}/candidate_stop_30pct_failure_mode_report.json`),
};
const model = buildDashboardModel(dashboardSnapshot, options);
const html = renderDashboard(dashboardSnapshot, options);
assert.equal(model.evaluation.state, "insufficient");
assert.match(html, /data_blocked/);
assert.match(html, /candidate_stop_30pct/);

const baselineOptions = {
  manifest: json(`${dashboard}/pa_feitian_run_manifest_baseline_screening_v1.json`),
  decisionIntent: json(`${dashboard}/pa_feitian_decision_intent_v1.json`),
  premiumOutcome: json(`${dashboard}/pa_feitian_premium_outcome_v1.json`),
  evaluationDataset: json(`${dashboard}/pa_feitian_evaluation_dataset_baseline_v1.json`),
  evaluationAggregate: json(`${dashboard}/pa_feitian_evaluation_aggregate_result_baseline_v1.json`),
  evaluationScreening: json(`${dashboard}/pa_feitian_evaluation_screening_report_v1.json`),
};
const baselineModel = buildDashboardModel(dashboardSnapshot, baselineOptions);
const baselineHtml = renderDashboard(dashboardSnapshot, baselineOptions);
assert.equal(baselineModel.evaluation.screening.status, "loaded");
assert.equal(baselineModel.evaluation.screening.payload.candidates[0].classification, report.classification);
assert.ok(
  baselineModel.evaluation.linkRows
    .filter((row) => row.label.startsWith("Screening"))
    .every((row) => row.hashStatus === "match"),
);
assert.match(baselineHtml, /pa_feitian_m6_daily_long_option_stop_30pct/);

for (const path of Object.keys(expectedHashes)) {
  assert.doesNotMatch(readFileSync(resolve(repoRoot, path), "utf8"), /\/(?:home|mnt|Users)\//, `${path} local path`);
}

console.log(JSON.stringify({
  ok: true,
  candidate: "candidate_stop_30pct",
  candidate_statuses: candidate.outcomes.map((outcome) => outcome.evaluation_status),
  screening: report.classification,
  paired_events: report.comparison.paired_effective_event_count,
  baseline_mean_premium_r: mean(baselineRows.map((row) => row.premium_r)),
  candidate_mean_premium_r: mean(candidateRows.map((row) => row.premium_r)),
  descriptive_mean_difference: mean(descriptiveDifferences),
}));
