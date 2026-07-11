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

const root = "doc/repro/pa-feitian-m6-candidate-recovery-2026-07-11";
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
  [candidateOutcome]: "sha256:9dbd7d9058dc2d4ed4a643447b8c4dc4ba27bad24a7e99078b310bd682a5628d",
  [candidateManifest]: "sha256:23ebf1a4730aa939e1338733c63fff1210c76b36b0fe6422616cc2202dc0d0ed",
  [baselineDataset]: "sha256:6ebcef341f7cea43036c3e2b9b609661c9a828f0992ce5793221d5a8ae6c1fba",
  [baselineAggregate]: "sha256:1128f718722788d50e2d2c0ce1200b32b578c94c6c4c5ad24e3e9f24d0c2b7d2",
  [candidateDataset]: "sha256:1bb0aa8426aa5c65f00ae491b827308c4ddb1e0225c2fde8e361ad17bb99b1ad",
  [candidateAggregate]: "sha256:e1a1a217f299365fcd33836d78a6448e0115ab1400dec3b1d26f70c00f8d2c4d",
  [screening]: "sha256:98156c33be21c899d1567e196ecb10029acc8c6045d7435b769d187961b2bf88",
  [failureReport]: "sha256:cf6a5b5f55ee99773e2f861a9ab2b132f12e2db347b4b322b7e9ff8faf9aded7",
  [`${dashboard}/pa_feitian_run_manifest_candidate_stop_30pct_v1.json`]: "sha256:9ddaf0d9062da075d2f36988fc834a8ccfbca4f3788287c8f1266b5579990129",
  [`${dashboard}/pa_feitian_run_manifest_baseline_screening_v1.json`]: "sha256:0d47359c4e4abf246687568eafac91c4dc39dd728fda7b82296594bfbfb2e840",
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
assert.deepEqual(candidate.outcomes.map((outcome) => outcome.evaluation_status), ["observed", "observed", "observed", "data_blocked"]);
assert.equal(candidate.outcomes[1].exit_reason, "time_exit");
const report = json(screening).candidates[0];
assert.equal(report.classification, "blocked");
assert.equal(report.comparison.paired_effective_event_count, 0);
assert.match(report.limitations[0], /observed event-id set differs/);

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
assert.equal(baselineModel.evaluation.screening.payload.candidates[0].classification, "blocked");
assert.ok(
  baselineModel.evaluation.linkRows
    .filter((row) => row.label.startsWith("Screening"))
    .every((row) => row.hashStatus === "match"),
);
assert.match(baselineHtml, /pa_feitian_m6_daily_long_option_stop_30pct/);

for (const path of Object.keys(expectedHashes)) {
  assert.doesNotMatch(readFileSync(resolve(repoRoot, path), "utf8"), /\/(?:home|mnt|Users)\//, `${path} local path`);
}

console.log(JSON.stringify({ ok: true, candidate: "candidate_stop_30pct", screening: report.classification, paired_events: report.comparison.paired_effective_event_count }));
