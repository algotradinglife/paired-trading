import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFile, stat, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { buildDashboardModel, renderDashboard } from "../../../frontend/pa-feitian-dashboard/app.mjs";

const repoRoot = new URL("../../../", import.meta.url);
const repoRootPath = fileURLToPath(repoRoot);

const sourceCommit = "5c74dd4964c814f1daefa09dc9f45ac3bfcc5788";
const generatedAtUtc = "2026-07-10T00:00:00Z";
const traversalStartedAtUtc = "2026-07-10T00:01:00Z";
const quantDataRootLabel = "external://optionstore/quant-data";

const sourceOutcomePath =
  "doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/source/pa_feitian_premium_outcome_v1.json";
const sourceManifestPath =
  "doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/source/pa_feitian_run_manifest_with_premium_outcome_v1.json";
const dashboardOutcomePath =
  "doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/dashboard/pa_feitian_premium_outcome_v1.json";
const dashboardManifestPath =
  "doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/dashboard/pa_feitian_run_manifest_v1.json";
const readmePath = "doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/README.md";
const verifierPath = "doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/verify.mjs";

const m4bRoot = "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10";
const m4bScorecardPath = `${m4bRoot}/score_today_cn_metal_120d_2026-07-10.json`;
const m4bSourceSnapshotPath = `${m4bRoot}/source/pa_feitian_snapshot_v1.json`;
const m4bDashboardSnapshotPath = `${m4bRoot}/dashboard/pa_feitian_snapshot_v1.json`;
const m4bSourceDecisionIntentPath = `${m4bRoot}/source/pa_feitian_decision_intent_v1.json`;
const m4bDashboardDecisionIntentPath = `${m4bRoot}/dashboard/pa_feitian_decision_intent_v1.json`;
const m4bSourceManifestPath = `${m4bRoot}/source/pa_feitian_run_manifest_with_decision_intent_v1.json`;
const goldenOutcomeFixturePath = "src/tests/fixtures/pa_feitian_premium_outcome_v1.json";
const frontendSnapshotFixturePath = "frontend/pa-feitian-dashboard/fixtures/pa_feitian_snapshot_v1.json";
const frontendDecisionIntentFixturePath = "frontend/pa-feitian-dashboard/fixtures/pa_feitian_decision_intent_v1.json";
const frontendOutcomeFixturePath = "frontend/pa-feitian-dashboard/fixtures/pa_feitian_premium_outcome_v1.json";
const frontendManifestFixturePath = "frontend/pa-feitian-dashboard/fixtures/pa_feitian_run_manifest_v1.json";
const frontendAppPaths = [
  "frontend/pa-feitian-dashboard/index.html",
  "frontend/pa-feitian-dashboard/app.mjs",
  "frontend/pa-feitian-dashboard/styles.css",
];

const expectedOutcomes = [
  {
    signalId: "paft_scorecard_0001_kq_m_shfe_au_20260313000000",
    sourceStatus: "data_blocked",
    decisionState: "watch",
    contract: "au2606c1152",
    optionStoreFile: "SHFE.au2606C1152.parquet",
    sourceRecordIndex: 1,
    selectedBarHash: "sha256:351100182b31f2a83c4fb96415e3d97475210fdea5dea93811034b55f9a80bb4",
    decisionTsUtc: "2026-03-13T00:00:00Z",
    entryTsUtc: "2026-03-16T00:00:00Z",
    exitTsUtc: "2026-03-19T00:00:00Z",
  },
  {
    signalId: "paft_scorecard_0002_kq_m_shfe_au_20260318000000",
    sourceStatus: "keep",
    decisionState: "watch",
    contract: "au2606c1136",
    optionStoreFile: "SHFE.au2606C1136.parquet",
    sourceRecordIndex: 2,
    selectedBarHash: "sha256:b1c953c88b91930f0be381b7791966c35295052f6acdb1843028c444ddeb5ff5",
    decisionTsUtc: "2026-03-18T00:00:00Z",
    entryTsUtc: "2026-03-19T00:00:00Z",
    exitTsUtc: "2026-03-20T00:00:00Z",
  },
  {
    signalId: "paft_scorecard_0003_kq_m_shfe_ag_20260515000000",
    sourceStatus: "data_blocked",
    decisionState: "watch",
    contract: "ag2607c19900",
    optionStoreFile: "SHFE.ag2607C19900.parquet",
    sourceRecordIndex: 3,
    selectedBarHash: "sha256:310f46efb6b88d1a40e2774dd3e8397a770cdcbc7a262b792811dbdb087a2246",
    decisionTsUtc: "2026-05-15T00:00:00Z",
    entryTsUtc: "2026-05-18T00:00:00Z",
    exitTsUtc: "2026-05-26T00:00:00Z",
  },
  {
    signalId: "paft_scorecard_0004_kq_m_shfe_ag_20260602000000",
    sourceStatus: "drop",
    decisionState: "reject",
    contract: "ag2608c18800",
    optionStoreFile: "SHFE.ag2608C18800.parquet",
    sourceRecordIndex: 4,
    selectedBarHash: "sha256:e0d9a7be35ce574fb260ba6966f292b14361ae4a93e7e759bdeeabeb9c6b287c",
    decisionTsUtc: "2026-06-02T00:00:00Z",
    entryTsUtc: "2026-06-03T00:00:00Z",
    exitTsUtc: "2026-06-08T00:00:00Z",
  },
];

function repoUrl(path) {
  return new URL(path, repoRoot);
}

async function readRaw(urlOrPath) {
  const url = typeof urlOrPath === "string" ? repoUrl(urlOrPath) : urlOrPath;
  return readFile(url);
}

async function readJson(urlOrPath) {
  return JSON.parse(await readRaw(urlOrPath));
}

function sha256(raw) {
  return `sha256:${createHash("sha256").update(raw).digest("hex")}`;
}

async function assertFileHash(repoRelativePath, expectedHash, label) {
  const actualHash = sha256(await readRaw(repoRelativePath));
  assert.equal(actualHash, expectedHash, `${label} hash`);
  return actualHash;
}

async function captureEvidenceBytes() {
  return new Map(
    await Promise.all(
      [sourceOutcomePath, sourceManifestPath, dashboardOutcomePath, dashboardManifestPath].map(
        async (path) => [path, await readRaw(path)],
      ),
    ),
  );
}

function runChecked(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repoRootPath,
    encoding: "utf8",
    env: { ...process.env, ...options.env },
  });
  if (result.status !== 0) {
    throw new Error(
      [
        `${command} ${args.join(" ")} failed with status ${result.status}`,
        result.stdout,
        result.stderr,
      ]
        .filter(Boolean)
        .join("\n"),
    );
  }
  return result;
}

function pythonExecutable() {
  return process.env.PA_FEITIAN_PYTHON || "python3";
}

function runtimeQuantDataRoot() {
  const root = process.env.QUANT_DATA_ROOT;
  assert.ok(root, "QUANT_DATA_ROOT must point to the runtime OptionStore root");
  return root;
}

async function dashboardManifestTextFromSource() {
  const manifest = await readJson(sourceManifestPath);
  const decisionCopyHash = sha256(await readRaw(m4bDashboardDecisionIntentPath));
  manifest.decision_intent_artifact.path = m4bDashboardDecisionIntentPath;
  manifest.premium_outcome_artifact.path = dashboardOutcomePath;
  manifest.output_hashes.frontend_decision_intent_copy = decisionCopyHash;
  return `${JSON.stringify(manifest, null, 2)}\n`;
}

async function writeDashboardManifestFromSource() {
  await writeFile(repoUrl(dashboardManifestPath), await dashboardManifestTextFromSource(), "utf8");
}

async function assertIdempotentRealBuild() {
  const before = await captureEvidenceBytes();
  const python = pythonExecutable();
  const runtimeRoot = runtimeQuantDataRoot();
  runChecked(
    python,
    [
      "src/scripts/build_pa_feitian_premium_outcomes.py",
      "--snapshot",
      m4bSourceSnapshotPath,
      "--decision-intent",
      m4bSourceDecisionIntentPath,
      "--source-m4-manifest",
      m4bSourceManifestPath,
      "--quant-data-root",
      runtimeRoot,
      "--quant-data-root-label",
      quantDataRootLabel,
      "--out",
      sourceOutcomePath,
      "--manifest-out",
      sourceManifestPath,
      "--frontend-outcome-copy",
      dashboardOutcomePath,
      "--generated-at-utc",
      generatedAtUtc,
      "--policy-declared-at-utc",
      generatedAtUtc,
      "--traversal-started-at-utc",
      traversalStartedAtUtc,
      "--source-commit",
      sourceCommit,
    ],
    { env: { PYTHONPATH: "src" } },
  );
  await writeDashboardManifestFromSource();
  const after = await captureEvidenceBytes();
  for (const [path, rawBefore] of before.entries()) {
    assert.equal(after.get(path).toString("utf8"), rawBefore.toString("utf8"), `${path} byte-identical rebuild`);
  }
}

function assertUtcAfter(later, earlier, label) {
  assert.ok(Date.parse(later) > Date.parse(earlier), `${label}: ${later} must be after ${earlier}`);
}

function assertUtcNotAfter(left, right, label) {
  assert.ok(Date.parse(left) <= Date.parse(right), `${label}: ${left} must be at or before ${right}`);
}

function groupBy(items, keyFn) {
  const grouped = new Map();
  for (const item of items) {
    const key = keyFn(item);
    grouped.set(key, [...(grouped.get(key) || []), item]);
  }
  return grouped;
}

async function assertPythonSchemaValidation() {
  const python = pythonExecutable();
  const code = `
import json
from pathlib import Path
from engine.pa_feitian.manifest import load_run_manifest
from engine.pa_feitian.premium_outcome import load_premium_outcome, premium_outcome_to_jsonable
from engine.pa_feitian.schema_validation import (
    validate_pa_feitian_premium_outcome_schema,
    validate_pa_feitian_run_manifest_schema,
)

paths = {
    "source_outcome": Path("${sourceOutcomePath}"),
    "dashboard_outcome": Path("${dashboardOutcomePath}"),
    "frontend_outcome": Path("${frontendOutcomeFixturePath}"),
    "golden_outcome_fixture": Path("${goldenOutcomeFixturePath}"),
}
for label, path in paths.items():
    sidecar = load_premium_outcome(path)
    validate_pa_feitian_premium_outcome_schema(premium_outcome_to_jsonable(sidecar))

for path in [
    Path("${sourceManifestPath}"),
    Path("${dashboardManifestPath}"),
    Path("${frontendManifestFixturePath}"),
]:
    manifest = load_run_manifest(path)
    validate_pa_feitian_run_manifest_schema(manifest.model_dump(mode="json", exclude_none=False))
print("python_schema_ok")
`;
  runChecked(python, ["-c", code], { env: { PYTHONPATH: "src" } });
}

function assertNoLookahead(outcome) {
  const decisionTs = outcome.decision_ts_utc;
  assert.equal(outcome.policy.fixed_before_traversal, true, `${outcome.outcome_id} fixed policy`);
  assertUtcNotAfter(
    outcome.policy.declared_at_utc,
    outcome.policy.traversal_started_at_utc,
    `${outcome.outcome_id} policy declaration`,
  );
  assertUtcNotAfter(
    outcome.selected_contract.contract_selection_asof_utc,
    decisionTs,
    `${outcome.outcome_id} contract selection as-of`,
  );
  assertUtcAfter(outcome.first_eligible_entry_ts_utc, decisionTs, `${outcome.outcome_id} first entry`);
  assertUtcAfter(outcome.entry_fill.ts_utc, decisionTs, `${outcome.outcome_id} entry fill`);
  assertUtcAfter(
    outcome.data_quality.first_premium_observation_ts_utc,
    decisionTs,
    `${outcome.outcome_id} first premium observation`,
  );
  assertUtcAfter(
    outcome.data_quality.last_premium_observation_ts_utc,
    decisionTs,
    `${outcome.outcome_id} last premium observation`,
  );
  assert.ok(
    Date.parse(outcome.exit_fill.ts_utc) >= Date.parse(outcome.entry_fill.ts_utc),
    `${outcome.outcome_id} exit must not precede entry`,
  );
  for (const inputRef of outcome.no_lookahead_inputs) {
    assertUtcNotAfter(inputRef.asof_ts_utc, decisionTs, `${outcome.outcome_id} input ${inputRef.id}`);
    assert.doesNotMatch(
      `${inputRef.id} ${inputRef.source}`.toLowerCase(),
      /posterior|outcome|label|mfe|mae|hit_marker|stop_first/,
      `${outcome.outcome_id} no-lookahead input label`,
    );
  }
}

function assertRealOutcomes({ sourceOutcome, sourceManifest, snapshot, decisionIntent }) {
  assert.equal(sourceOutcome.schema_version, "pa_feitian_premium_outcome_v1");
  assert.equal(sourceOutcome.generated_at_utc, generatedAtUtc);
  assert.equal(sourceOutcome.source_commit, sourceCommit);
  assert.equal(sourceOutcome.outcomes.length, 4, "real selected contracts evaluated");
  assert.equal(sourceManifest.data_access.status, "real_data_available");
  assert.equal(sourceManifest.data_access.source, quantDataRootLabel);
  assert.equal(sourceManifest.run_config.quant_data_root, quantDataRootLabel);
  assert.equal(
    sourceManifest.cli_args[sourceManifest.cli_args.indexOf("--quant-data-root") + 1],
    quantDataRootLabel,
  );
  assert.equal(
    sourceOutcome.provenance.cli_args[
      sourceOutcome.provenance.cli_args.indexOf("--quant-data-root") + 1
    ],
    quantDataRootLabel,
  );
  assert.ok(sourceOutcome.provenance.notes.includes(`quant_data_root=${quantDataRootLabel}`));
  assert.equal(sourceManifest.run_config.observation_only, true);
  assert.equal(sourceManifest.run_config.no_contract_reselection, true);
  assert.equal(sourceManifest.run_config.policy_declared_at_utc, generatedAtUtc);
  assert.equal(sourceManifest.run_config.traversal_started_at_utc, traversalStartedAtUtc);

  const outcomesBySignal = new Map(sourceOutcome.outcomes.map((outcome) => [outcome.source_signal_id, outcome]));
  const signalsById = new Map(snapshot.signals.map((signal) => [signal.id, signal]));
  const intentsBySignal = new Map(decisionIntent.intents.map((intent) => [intent.signal_id, intent]));

  for (const expected of expectedOutcomes) {
    const signal = signalsById.get(expected.signalId);
    const intent = intentsBySignal.get(expected.signalId);
    const outcome = outcomesBySignal.get(expected.signalId);
    assert.ok(signal, `${expected.signalId} snapshot signal`);
    assert.ok(intent, `${expected.signalId} decision intent`);
    assert.ok(outcome, `${expected.signalId} outcome`);

    assert.equal(signal.status, expected.sourceStatus, `${expected.signalId} source status preserved`);
    assert.equal(intent.decision_state, expected.decisionState, `${expected.signalId} decision state preserved`);
    assert.equal(intent.execution_allowed, false, `${expected.signalId} execution remains blocked`);
    assert.equal(intent.decision_ts_utc, expected.decisionTsUtc, `${expected.signalId} decision timestamp`);
    assert.equal(signal.features_det.selected_option_contract, expected.contract);
    assert.equal(signal.features_det.source_record_index, expected.sourceRecordIndex);

    const selectedCall = signal.features_det.options_calls.find(
      (call) => call.contract_sym === expected.contract,
    );
    assert.ok(selectedCall, `${expected.signalId} selected call metadata`);
    assert.equal(selectedCall.price_source, "store", `${expected.signalId} source premium is store`);
    assert.notEqual(selectedCall.model_dominated, true, `${expected.signalId} not model dominated`);

    assert.equal(outcome.decision_intent_signal_id, expected.signalId);
    assert.equal(outcome.decision_ts_utc, expected.decisionTsUtc);
    assert.equal(outcome.evaluation_status, "observed", `${expected.signalId} honest M5 status`);
    assert.equal(outcome.exit_reason, "premium_stop", `${expected.signalId} exit reason`);
    assert.equal(outcome.selected_contract.contract_symbol, expected.contract);
    assert.equal(outcome.source_contract_id, `scorecard_record:${expected.sourceRecordIndex}:options_calls:0`);
    assert.equal(outcome.selected_contract.selection_source_ref, `scorecard_record:${expected.sourceRecordIndex}`);
    assert.equal(outcome.first_eligible_entry_ts_utc, expected.entryTsUtc);
    assert.equal(outcome.entry_fill.ts_utc, expected.entryTsUtc);
    assert.equal(outcome.exit_fill.ts_utc, expected.exitTsUtc);
    assert.equal(outcome.data_quality.premium_price_source_type, "observed");
    assert.equal(outcome.data_quality.bar_granularity, "daily");
    assert.equal(outcome.data_quality.required_premium_bars_available, true);
    assert.equal(outcome.data_quality.ambiguity, null);
    assert.equal(outcome.data_quality.data_gap, null);
    assert.equal(outcome.underlying_context, null, `${expected.signalId} no premium/underlying denominator mixing`);
    assert.equal(
      outcome.premium_metrics.risk.denominator_label,
      "declared_premium_risk_after_costs",
      `${expected.signalId} premium R denominator`,
    );
    assertNoLookahead(outcome);

    const barHashKey = `selected_option_bars:${outcome.outcome_id}`;
    assert.equal(
      sourceOutcome.provenance.input_hashes[barHashKey],
      expected.selectedBarHash,
      `${expected.signalId} sidecar selected-bar hash`,
    );
    assert.equal(
      sourceManifest.input_hashes[barHashKey],
      expected.selectedBarHash,
      `${expected.signalId} manifest selected-bar hash`,
    );
  }
}

async function assertRealOptionFilesExistOnlyUnderOptionStore() {
  const runtimeRoot = runtimeQuantDataRoot();
  for (const expected of expectedOutcomes) {
    const filePath = `${runtimeRoot}/daily/${expected.optionStoreFile}`;
    const info = await stat(filePath);
    assert.equal(info.isFile(), true, `${filePath} exists`);
  }
}

function assertGoldenStatusFixture(goldenOutcome) {
  const statuses = new Set(goldenOutcome.outcomes.map((outcome) => outcome.evaluation_status));
  assert.deepEqual(statuses, new Set(["observed", "ambiguous", "data_blocked", "not_evaluable"]));
  const byStatus = groupBy(goldenOutcome.outcomes, (outcome) => outcome.evaluation_status);
  assert.equal(byStatus.get("observed")[0].data_quality.premium_price_source_type, "observed");
  assert.equal(byStatus.get("ambiguous")[0].data_quality.ambiguity.kind, "same_bar_stop_target");
  assert.ok(byStatus.get("data_blocked")[0].data_quality.data_gap, "data_blocked fixture has gap evidence");
  assert.equal(byStatus.get("not_evaluable")[0].data_quality.premium_price_source_type, "model_derived");
  assert.ok(byStatus.get("observed")[0].premium_metrics);
  assert.ok(byStatus.get("observed")[0].underlying_context);
  assert.equal(
    Object.hasOwn(byStatus.get("observed")[0].premium_metrics, "underlying_r"),
    false,
    "premium metrics do not embed underlying_r",
  );
}

async function assertManifestAndCopies({ sourceOutcome, sourceManifest, dashboardOutcome, dashboardManifest }) {
  assert.deepEqual(dashboardOutcome, sourceOutcome, "dashboard premium outcome copy");
  assert.equal(sourceManifest.premium_outcome_artifact.path, sourceOutcomePath);
  assert.equal(dashboardManifest.premium_outcome_artifact.path, dashboardOutcomePath);
  assert.equal(sourceManifest.decision_intent_artifact.path, m4bSourceDecisionIntentPath);
  assert.equal(dashboardManifest.decision_intent_artifact.path, m4bDashboardDecisionIntentPath);
  assert.equal(sourceManifest.frontend_copy_path, m4bDashboardSnapshotPath);
  assert.equal(dashboardManifest.frontend_copy_path, m4bDashboardSnapshotPath);

  await assertFileHash(m4bScorecardPath, sourceManifest.scorecard_artifact.sha256, "M4b scorecard");
  await assertFileHash(m4bSourceSnapshotPath, sourceManifest.snapshot_artifact.sha256, "M4b source snapshot");
  await assertFileHash(
    m4bSourceDecisionIntentPath,
    sourceManifest.decision_intent_artifact.sha256,
    "M4b source decision intent",
  );
  await assertFileHash(sourceOutcomePath, sourceManifest.premium_outcome_artifact.sha256, "source outcome");
  await assertFileHash(dashboardOutcomePath, sourceManifest.output_hashes.frontend_premium_outcome_copy, "dashboard outcome");
  await assertFileHash(dashboardOutcomePath, dashboardManifest.premium_outcome_artifact.sha256, "dashboard outcome artifact");
  await assertFileHash(
    m4bDashboardDecisionIntentPath,
    dashboardManifest.output_hashes.frontend_decision_intent_copy,
    "dashboard decision-intent copy",
  );

  assert.equal(sourceManifest.input_hashes.source_m4_manifest, sourceOutcome.provenance.input_hashes.source_manifest);
  assert.equal(sourceManifest.input_hashes.source_manifest, sourceOutcome.provenance.input_hashes.source_manifest);
  assert.equal(sourceManifest.input_hashes.snapshot_artifact, sourceOutcome.provenance.input_hashes.snapshot_artifact);
  assert.equal(
    sourceManifest.input_hashes.decision_intent_artifact,
    sourceOutcome.provenance.input_hashes.decision_intent_artifact,
  );
  assert.equal(sourceManifest.output_hashes.premium_outcome_artifact, sourceManifest.premium_outcome_artifact.sha256);
  assert.equal(
    sourceManifest.output_hashes.frontend_premium_outcome_copy,
    dashboardManifest.output_hashes.frontend_premium_outcome_copy,
  );
}

async function assertFrontendFixtureCopies({
  sourceOutcome,
  dashboardManifest,
  snapshot,
  decisionIntent,
  frontendSnapshot,
  frontendDecisionIntent,
  frontendOutcome,
  frontendManifest,
}) {
  assert.deepEqual(frontendSnapshot, snapshot, "frontend snapshot copy is real M4b snapshot");
  assert.deepEqual(frontendDecisionIntent, decisionIntent, "frontend decision-intent copy is real M4b sidecar");
  assert.deepEqual(frontendOutcome, sourceOutcome, "frontend premium outcome copy is real M5 outcome");
  assert.deepEqual(frontendOutcome.provenance, sourceOutcome.provenance, "frontend outcome provenance preserved");

  assert.equal(frontendManifest.snapshot_artifact.path, frontendSnapshotFixturePath);
  assert.equal(frontendManifest.decision_intent_artifact.path, frontendDecisionIntentFixturePath);
  assert.equal(frontendManifest.premium_outcome_artifact.path, frontendOutcomeFixturePath);
  assert.equal(frontendManifest.frontend_copy_path, frontendSnapshotFixturePath);
  assert.equal(frontendManifest.snapshot_artifact.sha256, dashboardManifest.snapshot_artifact.sha256);
  assert.equal(frontendManifest.decision_intent_artifact.sha256, dashboardManifest.decision_intent_artifact.sha256);
  assert.equal(frontendManifest.premium_outcome_artifact.sha256, dashboardManifest.premium_outcome_artifact.sha256);
  assert.deepEqual(frontendManifest.data_access, dashboardManifest.data_access, "frontend manifest data_access preserved");
  assert.deepEqual(frontendManifest.input_hashes, dashboardManifest.input_hashes, "frontend manifest input hashes preserved");
  assert.deepEqual(frontendManifest.output_hashes, dashboardManifest.output_hashes, "frontend manifest output hashes preserved");

  await assertFileHash(frontendSnapshotFixturePath, frontendManifest.snapshot_artifact.sha256, "frontend snapshot");
  await assertFileHash(
    frontendDecisionIntentFixturePath,
    frontendManifest.decision_intent_artifact.sha256,
    "frontend decision intent",
  );
  await assertFileHash(frontendOutcomeFixturePath, frontendManifest.premium_outcome_artifact.sha256, "frontend outcome");
}

async function assertFrontendArtifactOnlyBoundary(html) {
  const frontendSource = (
    await Promise.all(frontendAppPaths.map((path) => readRaw(path).then((raw) => raw.toString("utf8"))))
  ).join("\n");
  const forbiddenSourceReferences = [
    ["src", "data"].join("/"),
    ["data", "store"].join("/"),
    ["bar", "loader"].join("_"),
    ["engine", "divergence"].join("/"),
    ["engine", "options"].join("/"),
    ["scripts", "analyze"].join("/"),
    ["scripts", "score_today"].join("/"),
    "OptionStore",
    "raw market",
    "raw_market",
    "QUANT_DATA_ROOT",
  ];
  for (const forbidden of forbiddenSourceReferences) {
    assert.equal(frontendSource.includes(forbidden), false, `frontend source is artifact-only: ${forbidden}`);
  }
  const forbiddenRenderedFragments = [
    "QUANT_DATA_ROOT",
    ["", "daily", "SHFE"].join("/"),
    ".parquet",
    ["/", "mnt"].join(""),
    ["/", "Users"].join(""),
  ];
  for (const forbidden of forbiddenRenderedFragments) {
    assert.equal(html.includes(forbidden), false, `rendered dashboard hides runtime/raw path fragment: ${forbidden}`);
  }
}

async function assertFrontendRenderCompatibility({
  frontendManifest,
  frontendSnapshot,
  frontendDecisionIntent,
  frontendOutcome,
}) {
  const premiumOutcomeHash = sha256(await readRaw(frontendOutcomeFixturePath));
  const model = buildDashboardModel(frontendSnapshot, {
    manifest: frontendManifest,
    decisionIntent: frontendDecisionIntent,
    premiumOutcome: frontendOutcome,
  });
  const html = renderDashboard(frontendSnapshot, {
    manifest: frontendManifest,
    decisionIntent: frontendDecisionIntent,
    premiumOutcome: frontendOutcome,
  });

  assert.equal(model.snapshotMode, "generated");
  assert.equal(model.totalSignals, 4);
  assert.equal(model.manifest.dataAccess.status, "real_data_available");
  assert.equal(model.decisionIntent.status, "loaded");
  assert.equal(model.decisionIntent.intents.length, 4);
  assert.equal(model.premiumOutcome.status, "loaded");
  assert.equal(model.premiumOutcome.outcomes.length, 4);
  assert.equal(model.premiumOutcome.evaluationCounts.observed, 4);
  assert.deepEqual(model.premiumOutcome.duplicateOutcomeIds, []);
  assert.deepEqual(model.premiumOutcome.duplicateSourceSignalIds, []);
  assert.deepEqual(model.premiumOutcome.unmatchedSourceSignalIds, []);
  assert.deepEqual(model.premiumOutcome.missingSignalIds, []);
  assert.equal(model.reviewOperations.sidecarHashStatus.status, "match");
  assert.equal(model.reviewOperations.premiumOutcomeHashStatus.status, "match");
  assert.equal(frontendManifest.premium_outcome_artifact.sha256, premiumOutcomeHash);
  assert.equal(frontendManifest.output_hashes.frontend_premium_outcome_copy, premiumOutcomeHash);
  assert.ok(
    model.reviewOperations.artifactRows.every((row) => row.hashStatus === "match"),
    "frontend artifact rows remain hash-clean with M5 manifest",
  );
  for (const expected of expectedOutcomes) {
    const signal = model.signals.find((candidate) => candidate.id === expected.signalId);
    assert.ok(signal, `${expected.signalId} rendered model signal`);
    assert.equal(signal.premiumOutcomes.length, 1, `${expected.signalId} one premium outcome`);
    const outcome = signal.premiumOutcomes[0];
    assert.equal(outcome.evaluation_status, "observed", `${expected.signalId} observed model outcome`);
    assert.equal(outcome.selected_contract.contract_symbol, expected.contract, `${expected.signalId} rendered contract`);
    assert.ok(outcome.premium_metrics, `${expected.signalId} premium metrics rendered from artifact`);
    assert.equal(outcome.exit_reason, "premium_stop", `${expected.signalId} premium stop rendered`);
  }
  assert.match(html, /real_data_available/);
  assert.match(html, /data-testid="decision-intent-review"/);
  assert.match(html, /data-testid="premium-outcome-review"/);
  assert.match(html, /paft_scorecard_0004_kq_m_shfe_ag_20260602000000/);
  assert.match(html, /au2606c1152/);
  assert.match(html, /ag2608c18800/);
  assert.match(html, /Premium R/);
  assert.match(html, /declared_premium_risk_after_costs/);
  assert.match(html, /premium_stop/);
  assert.doesNotMatch(html, /Premium outcome records without snapshot signals/);
  assert.doesNotMatch(html, /Snapshot signals missing premium outcome records/);
  assert.doesNotMatch(html, /daily OHLC proves exact tick execution/);
  await assertFrontendArtifactOnlyBoundary(html);
}

async function assertNoObviousSecrets() {
  const artifactText = [
    (await readRaw(sourceOutcomePath)).toString("utf8"),
    (await readRaw(sourceManifestPath)).toString("utf8"),
    (await readRaw(dashboardOutcomePath)).toString("utf8"),
    (await readRaw(dashboardManifestPath)).toString("utf8"),
    (await readRaw(frontendSnapshotFixturePath)).toString("utf8"),
    (await readRaw(frontendDecisionIntentFixturePath)).toString("utf8"),
    (await readRaw(frontendOutcomeFixturePath)).toString("utf8"),
    (await readRaw(frontendManifestFixturePath)).toString("utf8"),
    (await readRaw(readmePath)).toString("utf8"),
    (await readRaw(verifierPath)).toString("utf8"),
  ].join("\n");
  assert.doesNotMatch(
    artifactText,
    /(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}|BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY)/,
    "no obvious public token or private-key material",
  );
  for (const fragment of ["/" + "mnt", "/" + "Users", "dr" + "who", "hhu" + "sl"]) {
    assert.equal(artifactText.includes(fragment), false, `no local path fragment ${fragment}`);
  }
}

await assertIdempotentRealBuild();
await assertPythonSchemaValidation();

const sourceOutcome = await readJson(sourceOutcomePath);
const sourceManifest = await readJson(sourceManifestPath);
const dashboardOutcome = await readJson(dashboardOutcomePath);
const dashboardManifest = await readJson(dashboardManifestPath);
const snapshot = await readJson(m4bSourceSnapshotPath);
const decisionIntent = await readJson(m4bSourceDecisionIntentPath);
const dashboardSnapshot = await readJson(m4bDashboardSnapshotPath);
const dashboardDecisionIntent = await readJson(m4bDashboardDecisionIntentPath);
const goldenOutcome = await readJson(goldenOutcomeFixturePath);
const frontendSnapshot = await readJson(frontendSnapshotFixturePath);
const frontendDecisionIntent = await readJson(frontendDecisionIntentFixturePath);
const frontendOutcome = await readJson(frontendOutcomeFixturePath);
const frontendManifest = await readJson(frontendManifestFixturePath);

assertRealOutcomes({ sourceOutcome, sourceManifest, snapshot, decisionIntent });
await assertRealOptionFilesExistOnlyUnderOptionStore();
assertGoldenStatusFixture(goldenOutcome);
await assertManifestAndCopies({ sourceOutcome, sourceManifest, dashboardOutcome, dashboardManifest });
assert.deepEqual(dashboardSnapshot, snapshot, "M4b dashboard snapshot copy");
assert.deepEqual(dashboardDecisionIntent, decisionIntent, "M4b dashboard decision-intent copy");
await assertFrontendFixtureCopies({
  sourceOutcome,
  dashboardManifest,
  snapshot,
  decisionIntent,
  frontendSnapshot,
  frontendDecisionIntent,
  frontendOutcome,
  frontendManifest,
});
await assertFrontendRenderCompatibility({
  frontendManifest,
  frontendSnapshot,
  frontendDecisionIntent,
  frontendOutcome,
});
await assertNoObviousSecrets();

console.log(
  JSON.stringify(
    {
      ok: true,
      source_commit: sourceCommit,
      generated_at_utc: generatedAtUtc,
      quant_data_root: quantDataRootLabel,
      real_contracts: expectedOutcomes.map((outcome) => outcome.contract),
      real_statuses: sourceOutcome.outcomes.map((outcome) => outcome.evaluation_status),
      golden_fixture_statuses: [...new Set(goldenOutcome.outcomes.map((outcome) => outcome.evaluation_status))].sort(),
      data_access: sourceManifest.data_access.status,
      source_outcome_sha256: sha256(await readRaw(sourceOutcomePath)),
      source_manifest_sha256: sha256(await readRaw(sourceManifestPath)),
      frontend_manifest_sha256: sha256(await readRaw(frontendManifestFixturePath)),
      frontend_premium_outcome_sha256: sha256(await readRaw(frontendOutcomeFixturePath)),
      dashboard_render_html_length: renderDashboard(frontendSnapshot, {
        manifest: frontendManifest,
        decisionIntent: frontendDecisionIntent,
        premiumOutcome: frontendOutcome,
      }).length,
    },
    null,
    2,
  ),
);
