import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  DATA_ACCESS_DEFINITIONS,
  DECISION_STATE_DEFINITIONS,
  HASH_STATUS_DEFINITIONS,
  PREMIUM_OUTCOME_STATUS_DEFINITIONS,
  PREMIUM_PRICE_SOURCE_DEFINITIONS,
  SNAPSHOT_MODE_DEFINITIONS,
  STATUS_DEFINITIONS,
  SUPPORTED_DECISION_INTENT_VERSIONS,
  SUPPORTED_PREMIUM_OUTCOME_VERSIONS,
  TRACE_NODE_STATUS_DEFINITIONS,
  artifactPathToUrl,
  buildDashboardModel,
  loadDecisionIntent,
  loadPremiumOutcome,
  missingOptionalFields,
  normalizeDecisionIntentSidecar,
  normalizePremiumOutcomeSidecar,
  renderDashboard,
} from "../app.mjs";
import { copySnapshotFixture } from "../scripts/copy-snapshot-fixture.mjs";

const fixtureUrl = new URL("../fixtures/pa_feitian_snapshot_v1.json", import.meta.url);
const legacyFixtureUrl = new URL("../fixtures/pa_feitian_snapshot_v0.json", import.meta.url);
const frontendManifestFixtureUrl = new URL("../fixtures/pa_feitian_run_manifest_v1.json", import.meta.url);
const decisionIntentFixtureUrl = new URL("../fixtures/pa_feitian_decision_intent_v1.json", import.meta.url);
const premiumOutcomeFixtureUrl = new URL("../fixtures/pa_feitian_premium_outcome_v1.json", import.meta.url);
const manifestFixtureUrl = new URL("../../../src/tests/fixtures/pa_feitian_run_manifest_v1.json", import.meta.url);
const appFiles = [
  new URL("../index.html", import.meta.url),
  new URL("../app.mjs", import.meta.url),
  new URL("../styles.css", import.meta.url),
];

async function loadFixture(url = fixtureUrl) {
  return JSON.parse(await readFile(url, "utf8"));
}

function sha256Digest(raw) {
  return `sha256:${createHash("sha256").update(raw).digest("hex")}`;
}

test("renders summary, warning, signal table, and trace nodes from the v1 fixture", async () => {
  const snapshot = await loadFixture();
  const html = renderDashboard(snapshot);

  assert.match(html, /Total signals/);
  assert.match(html, /paft_scorecard_0001_kq_m_shfe_au_20260628000000/);
  assert.match(html, /paft_scorecard_0002_kq_m_shfe_au_20260629000000/);
  assert.match(html, /data-testid="signal-table"/);
  assert.match(html, /data-testid="signal-drill-down"/);
  assert.match(html, /data-testid="decision-trace-v1"/);
  assert.match(html, /data-testid="decision-trace-v1-input-refs"/);
  assert.match(html, /data-testid="decision-trace-v1-nodes"/);
  assert.match(html, /Generated snapshot/);
  assert.match(html, /data-testid="run-manifest-empty"/);
  assert.match(html, /Manifest metadata unavailable/);
  assert.match(html, /Score Today underlying signal/);
  assert.match(html, /scorecard_record:1/);
  assert.match(html, /sha256:/);
  assert.match(html, /iv_regime/);
  assert.match(html, /producer consumes score_today\/emission output/);
  assert.match(html, /forward premium\/underlying outcomes/);
});

test("surfaces defensive states, trace node states, and missing optional fields", async () => {
  const snapshot = await loadFixture();
  const model = buildDashboardModel(snapshot);
  const html = renderDashboard(snapshot);

  assert.equal(model.totalSignals, 3);
  assert.equal(model.statusCounts.keep, 1);
  assert.equal(model.statusCounts.data_blocked, 1);
  assert.equal(model.statusCounts.model_dominated, 1);
  assert.ok("model_dominated" in STATUS_DEFINITIONS);
  assert.equal(SNAPSHOT_MODE_DEFINITIONS.fixture, "Fixture snapshot");
  assert.ok("blocked" in TRACE_NODE_STATUS_DEFINITIONS);
  assert.match(html, /model_dominated/);
  assert.match(html, /blocked/);
  assert.match(html, /Missing Optional Fields/);

  const blockedSignal = model.signals.find((signal) => signal.status === "data_blocked");
  assert.ok(blockedSignal);
  assert.equal(blockedSignal.decisionTrace.kind, "decision_trace_v1");
  assert.equal(blockedSignal.decisionTrace.summary.primary_blocker, "iv_rank_missing");
  assert.deepEqual(blockedSignal.decisionTrace.nodes.map((node) => node.id).slice(0, 3), [
    "underlying_signal",
    "policy_rule",
    "option_selection",
  ]);
  assert.deepEqual(missingOptionalFields(blockedSignal), [
    "Delta estimate",
    "IV rank",
    "Option runner outcome",
    "Proxy outcome",
  ]);
  assert.equal(
    missingOptionalFields({ ...blockedSignal, decision_trace: null }).includes("Decision trace"),
    false,
  );
});

test("renders generated and review manifest provenance labels", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(manifestFixtureUrl);
  const generatedSnapshot = {
    ...snapshot,
    run_config: {
      ...snapshot.run_config,
      mode: "scorecard",
      source_scorecard: "src/tests/fixtures/pa_feitian_scorecard_v1.json",
    },
    warnings: ["generated manifest smoke"],
  };

  const generatedModel = buildDashboardModel(generatedSnapshot, { manifest });
  const generatedHtml = renderDashboard(generatedSnapshot, { manifest });

  assert.equal(generatedModel.snapshotMode, "generated");
  assert.equal(generatedModel.manifest.dataAccess.status, "fixture_fallback");
  assert.equal(DATA_ACCESS_DEFINITIONS.fixture_fallback, "Deterministic fixture fallback");
  assert.equal(HASH_STATUS_DEFINITIONS.match, "Manifest hash link matches");
  assert.equal(generatedModel.reviewOperations.dataAccess.status, "fixture_fallback");
  assert.equal(
    generatedModel.reviewOperations.artifactRows.find((row) => row.label === "Scorecard artifact").hashStatus,
    "match",
  );
  assert.equal(
    generatedModel.reviewOperations.artifactRows.find((row) => row.label === "Snapshot artifact").hashStatus,
    "match",
  );
  assert.equal(generatedModel.reviewOperations.sidecarHashStatus.status, "missing");
  assert.match(generatedHtml, /data-testid="run-manifest-provenance"/);
  assert.match(generatedHtml, /data-testid="review-operations"/);
  assert.match(generatedHtml, /data-testid="artifact-provenance-table"/);
  assert.match(generatedHtml, /data_access classification/);
  assert.match(generatedHtml, /Sidecar hash status/);
  assert.match(generatedHtml, /Generated snapshot/);
  assert.match(generatedHtml, /Scorecard artifact/);
  assert.match(generatedHtml, /Snapshot artifact/);
  assert.match(generatedHtml, /Frontend snapshot copy/);
  assert.match(generatedHtml, /src\/tests\/fixtures\/pa_feitian_scorecard_v1\.json/);
  assert.match(generatedHtml, /fixture_fallback/);
  assert.match(generatedHtml, /Decision intent artifact hash status is missing/);
  assert.match(generatedHtml, /frontend\/pa-feitian-dashboard\/fixtures\/pa_feitian_snapshot_v1\.json/);
  assert.match(generatedHtml, /Input hashes/);
  assert.match(generatedHtml, /Output hashes/);

  const reviewedManifest = {
    ...manifest,
    review_state: {
      status: "approved",
      reviewer: "chatgpt",
      reviewed_at_utc: "2026-07-08T00:00:00Z",
      notes: ["review gate approved"],
    },
  };
  const reviewModel = buildDashboardModel(generatedSnapshot, { manifest: reviewedManifest });
  const reviewHtml = renderDashboard(generatedSnapshot, { manifest: reviewedManifest });

  assert.equal(reviewModel.snapshotMode, "review");
  assert.match(reviewHtml, /Review snapshot/);
  assert.match(reviewHtml, /approved/);
  assert.match(reviewHtml, /chatgpt/);
  assert.match(reviewHtml, /review gate approved/);
});

test("renders manifest-referenced decision-intent sidecar reviewer fields", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const decisionIntentRaw = await readFile(decisionIntentFixtureUrl, "utf8");
  const decisionIntent = await loadFixture(decisionIntentFixtureUrl);
  const decisionIntentHash = sha256Digest(decisionIntentRaw);
  const normalized = normalizeDecisionIntentSidecar(decisionIntent);
  const model = buildDashboardModel(snapshot, { manifest, decisionIntent });
  const html = renderDashboard(snapshot, { manifest, decisionIntent });

  assert.ok(SUPPORTED_DECISION_INTENT_VERSIONS.has("pa_feitian_decision_intent_v1"));
  assert.equal(DECISION_STATE_DEFINITIONS.trade_ready, "Trade-ready sidecar state");
  assert.equal(normalized.schemaVersion, "pa_feitian_decision_intent_v1");
  assert.equal(model.decisionIntent.status, "loaded");
  assert.equal(
    model.decisionIntent.artifact.path,
    "frontend/pa-feitian-dashboard/fixtures/pa_feitian_decision_intent_v1.json",
  );
  assert.equal(manifest.decision_intent_artifact.sha256, decisionIntentHash);
  assert.equal(manifest.output_hashes.decision_intent_artifact, decisionIntentHash);
  assert.equal(model.decisionIntent.stateCounts.trade_ready, 1);
  assert.equal(model.decisionIntent.executionAllowedCount, 1);
  assert.equal(model.reviewOperations.sidecarHashStatus.status, "match");
  assert.equal(
    model.reviewOperations.artifactRows.find((row) => row.label === "Decision intent artifact").hashStatus,
    "match",
  );
  assert.equal(
    model.reviewOperations.artifactRows.find((row) => row.label === "Decision intent frontend copy").hashStatus,
    "match",
  );

  const tradeReadySignal = model.signals.find((signal) => signal.decisionIntent?.decision_state === "trade_ready");
  assert.ok(tradeReadySignal);
  assert.equal(tradeReadySignal.decisionIntent.execution_allowed, true);
  assert.equal(tradeReadySignal.decisionIntent.product_direction_tier, "aligned_trade_candidate");

  assert.match(html, /data-testid="decision-intent-review"/);
  assert.match(html, /data-testid="decision-intent-sidecar"/);
  assert.match(html, /data-testid="decision-intent-no-lookahead"/);
  assert.match(html, /data-testid="sidecar-hash-status"/);
  assert.match(html, /data-testid="sidecar-provenance"/);
  assert.match(html, /Decision intent artifact/);
  assert.match(html, /Decision intent frontend copy/);
  assert.match(html, /manifest_referenced_decision_intent_sidecar/);
  assert.match(html, /engine\.pa_feitian\.decision_intent_adapter\.v0_2/);
  assert.match(html, /decision_state/);
  assert.match(html, /execution_allowed: true/);
  assert.match(html, /aligned_trade_candidate/);
  assert.match(html, /TRADE_READY_PREMIUM_CONFIRMED/);
  assert.match(html, /PREMIUM_STOP_CLEAR/);
  assert.match(html, /LIQUIDITY_OK/);
  assert.match(html, /Stop distance/);
  assert.match(html, /swing_low_premium/);
  assert.match(html, /premium_macd/);
  assert.match(html, /adequate/);
  assert.match(html, /scorecard_record:2/);
  assert.match(html, /sha256:30d70f3ca92533885529ec662b92395cbbf62444da34b832d4749b3cee3a8fcc/);
  assert.match(html, /Posterior diagnostic fields are present/);
});

test("renders manifest-referenced premium outcome sidecar reviewer fields", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const decisionIntent = await loadFixture(decisionIntentFixtureUrl);
  const premiumOutcomeRaw = await readFile(premiumOutcomeFixtureUrl, "utf8");
  const premiumOutcome = await loadFixture(premiumOutcomeFixtureUrl);
  const premiumOutcomeHash = sha256Digest(premiumOutcomeRaw);
  const normalized = normalizePremiumOutcomeSidecar(premiumOutcome);
  const model = buildDashboardModel(snapshot, { manifest, decisionIntent, premiumOutcome });
  const html = renderDashboard(snapshot, { manifest, decisionIntent, premiumOutcome });

  assert.ok(SUPPORTED_PREMIUM_OUTCOME_VERSIONS.has("pa_feitian_premium_outcome_v1"));
  assert.equal(PREMIUM_OUTCOME_STATUS_DEFINITIONS.observed, "Observed premium path");
  assert.equal(PREMIUM_PRICE_SOURCE_DEFINITIONS.model_derived, "Model-derived evidence only");
  assert.equal(normalized.schemaVersion, "pa_feitian_premium_outcome_v1");
  assert.equal(model.premiumOutcome.status, "loaded");
  assert.equal(
    model.premiumOutcome.artifact.path,
    "frontend/pa-feitian-dashboard/fixtures/pa_feitian_premium_outcome_v1.json",
  );
  assert.equal(manifest.premium_outcome_artifact.sha256, premiumOutcomeHash);
  assert.equal(manifest.output_hashes.premium_outcome_artifact, premiumOutcomeHash);
  assert.equal(manifest.output_hashes.frontend_premium_outcome_copy, premiumOutcomeHash);
  assert.equal(model.premiumOutcome.evaluationCounts.observed, 1);
  assert.equal(model.premiumOutcome.evaluationCounts.ambiguous, 1);
  assert.equal(model.premiumOutcome.evaluationCounts.data_blocked, 1);
  assert.equal(model.premiumOutcome.evaluationCounts.not_evaluable, 1);
  assert.deepEqual(model.premiumOutcome.duplicateSourceSignalIds, [
    "paft_scorecard_0002_kq_m_shfe_au_20260629000000",
  ]);
  assert.equal(model.reviewOperations.premiumOutcomeHashStatus.status, "match");
  assert.equal(
    model.reviewOperations.artifactRows.find((row) => row.label === "Premium outcome artifact").hashStatus,
    "match",
  );
  assert.equal(
    model.reviewOperations.artifactRows.find((row) => row.label === "Premium outcome frontend copy").hashStatus,
    "match",
  );

  const tradeReadySignal = model.signals.find(
    (signal) => signal.id === "paft_scorecard_0002_kq_m_shfe_au_20260629000000",
  );
  assert.equal(tradeReadySignal.premiumOutcomes.length, 2);
  assert.deepEqual(
    tradeReadySignal.premiumOutcomes.map((outcome) => outcome.evaluation_status),
    ["observed", "ambiguous"],
  );
  const observedOutcome = tradeReadySignal.premiumOutcomes.find(
    (outcome) => outcome.evaluation_status === "observed",
  );
  assert.equal(observedOutcome.premium_metrics.premium_r, 5.016949153);
  assert.equal(observedOutcome.underlying_context.underlying_r, 0.42);

  assert.match(html, /data-testid="premium-outcome-review"/);
  assert.match(html, /data-testid="premium-outcome-signal-review"/);
  assert.match(html, /data-testid="premium-outcome-card"/);
  assert.match(html, /data-testid="premium-outcome-no-lookahead"/);
  assert.match(html, /data-testid="premium-outcome-hash-status"/);
  assert.match(html, /data-testid="premium-outcome-provenance"/);
  assert.match(html, /Premium outcome artifact/);
  assert.match(html, /Premium outcome frontend copy/);
  assert.match(html, /manifest_referenced_premium_outcome_sidecar/);
  assert.match(html, /observed/);
  assert.match(html, /ambiguous/);
  assert.match(html, /data_blocked/);
  assert.match(html, /not_evaluable/);
  assert.match(html, /Selected Contract/);
  assert.match(html, /au2608c880/);
  assert.match(html, /Policy/);
  assert.match(html, /retrospective_fixed/);
  assert.match(html, /Entry-relative stop/);
  assert.match(html, /Entry-relative target/);
  assert.match(html, /Entry \/ Exit/);
  assert.match(html, /Fill reason/);
  assert.match(html, /premium_target/);
  assert.match(html, /Premium multiple/);
  assert.match(html, /Premium R/);
  assert.match(html, /Premium MFE/);
  assert.match(html, /Premium MAE/);
  assert.match(html, /Underlying-R Context/);
  assert.match(html, /Underlying R context/);
  assert.match(html, /daily OHLC; observation-only, not exact tick execution proof/);
  assert.match(html, /Model-derived premium outcome evidence is not observed/);
  assert.match(html, /Ambiguous premium outcome ordering/);
  assert.match(html, /Data-blocked premium outcome records are not observed results/);
  assert.match(html, /Multiple premium outcome policy records share source_signal_id/);
  assert.doesNotMatch(html, /daily OHLC proves exact tick execution/);
});

test("flags premium outcome source and frontend copy hash mismatches", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const premiumOutcome = await loadFixture(premiumOutcomeFixtureUrl);
  const tamperedManifest = {
    ...manifest,
    output_hashes: {
      ...manifest.output_hashes,
      premium_outcome_artifact: `sha256:${"0".repeat(64)}`,
      frontend_premium_outcome_copy: `sha256:${"2".repeat(64)}`,
    },
  };

  const model = buildDashboardModel(snapshot, { manifest: tamperedManifest, premiumOutcome });
  const html = renderDashboard(snapshot, { manifest: tamperedManifest, premiumOutcome });

  assert.equal(model.reviewOperations.premiumOutcomeHashStatus.status, "mismatch");
  assert.equal(
    model.reviewOperations.artifactRows.find((row) => row.label === "Premium outcome artifact").hashStatus,
    "mismatch",
  );
  assert.equal(
    model.reviewOperations.artifactRows.find((row) => row.label === "Premium outcome frontend copy").hashStatus,
    "mismatch",
  );
  assert.match(html, /Premium outcome artifact hash status is mismatch/);
  assert.match(html, /Premium outcome frontend copy hash status is mismatch/);
});

test("loads premium outcome sidecar from the manifest artifact path", async () => {
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const premiumOutcome = await loadFixture(premiumOutcomeFixtureUrl);
  const artifactUrl = artifactPathToUrl(manifest.premium_outcome_artifact.path);
  const loaded = await loadPremiumOutcome(async (url) => {
    assert.equal(url.pathname, "/frontend/pa-feitian-dashboard/fixtures/pa_feitian_premium_outcome_v1.json");
    return {
      ok: true,
      status: 200,
      json: async () => premiumOutcome,
    };
  }, manifest);

  assert.equal(artifactUrl, "/frontend/pa-feitian-dashboard/fixtures/pa_feitian_premium_outcome_v1.json");
  assert.equal(loaded.schema_version, "pa_feitian_premium_outcome_v1");
});

test("renders premium outcome missing, referenced_missing, and load_error states defensively", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const manifestWithoutPremium = {
    ...manifest,
    premium_outcome_artifact: undefined,
    output_hashes: {
      ...manifest.output_hashes,
      premium_outcome_artifact: undefined,
      frontend_premium_outcome_copy: undefined,
    },
  };

  const referencedMissingModel = buildDashboardModel(snapshot, { manifest });
  const referencedMissingHtml = renderDashboard(snapshot, { manifest });
  assert.equal(referencedMissingModel.premiumOutcome.status, "referenced_missing");
  assert.match(referencedMissingHtml, /referenced_missing/);
  assert.match(referencedMissingHtml, /Manifest references a premium outcome sidecar, but no sidecar payload is loaded/);

  const loadErrorModel = buildDashboardModel(snapshot, {
    manifest,
    premiumOutcomeError: new Error("premium fixture HTTP 500"),
  });
  const loadErrorHtml = renderDashboard(snapshot, {
    manifest,
    premiumOutcomeError: new Error("premium fixture HTTP 500"),
  });
  assert.equal(loadErrorModel.premiumOutcome.status, "load_error");
  assert.match(loadErrorHtml, /load_error/);
  assert.match(loadErrorHtml, /Premium outcome sidecar failed to load: premium fixture HTTP 500/);

  const notReferencedModel = buildDashboardModel(snapshot, { manifest: manifestWithoutPremium });
  const notReferencedHtml = renderDashboard(snapshot, { manifest: manifestWithoutPremium });
  assert.equal(notReferencedModel.premiumOutcome.status, "not_referenced");
  assert.match(notReferencedHtml, /not_referenced/);
  assert.match(notReferencedHtml, /Manifest does not reference a premium outcome sidecar/);
});

test("renders an empty premium outcome sidecar without fabricating signal outcomes", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const premiumOutcome = await loadFixture(premiumOutcomeFixtureUrl);
  const emptyPremiumOutcome = {
    ...premiumOutcome,
    outcomes: [],
    warnings: [],
  };
  const model = buildDashboardModel(snapshot, { manifest, premiumOutcome: emptyPremiumOutcome });
  const html = renderDashboard(snapshot, { manifest, premiumOutcome: emptyPremiumOutcome });

  assert.equal(model.premiumOutcome.status, "loaded");
  assert.equal(model.premiumOutcome.outcomes.length, 0);
  assert.deepEqual(model.premiumOutcome.missingSignalIds, snapshot.signals.map((signal) => signal.id));
  assert.equal(model.signals.every((signal) => signal.premiumOutcomes.length === 0), true);
  assert.match(html, /data-testid="premium-outcome-empty"/);
  assert.match(html, /No premium outcome records/);
  assert.match(html, /data-testid="premium-outcome-missing"/);
});

test("detects unmatched premium outcome source signals while preserving multiple policy outcomes", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const premiumOutcome = await loadFixture(premiumOutcomeFixtureUrl);
  const unmatchedOutcome = {
    ...premiumOutcome.outcomes[0],
    outcome_id: "paft_premium_outcome_unmatched_signal_v1",
    source_signal_id: "paft_scorecard_missing_source_signal",
    decision_intent_signal_id: "paft_scorecard_missing_source_signal",
  };
  const modifiedPremiumOutcome = {
    ...premiumOutcome,
    outcomes: [...premiumOutcome.outcomes, unmatchedOutcome],
  };
  const model = buildDashboardModel(snapshot, { manifest, premiumOutcome: modifiedPremiumOutcome });
  const html = renderDashboard(snapshot, { manifest, premiumOutcome: modifiedPremiumOutcome });

  assert.deepEqual(model.premiumOutcome.unmatchedSourceSignalIds, ["paft_scorecard_missing_source_signal"]);
  assert.deepEqual(model.premiumOutcome.duplicateSourceSignalIds, [
    "paft_scorecard_0002_kq_m_shfe_au_20260629000000",
  ]);
  assert.equal(
    model.signals.find((signal) => signal.id === "paft_scorecard_0002_kq_m_shfe_au_20260629000000")
      .premiumOutcomes.length,
    2,
  );
  assert.match(html, /Premium outcome records without snapshot signals: paft_scorecard_missing_source_signal/);
  assert.match(html, /Multiple premium outcome policy records share source_signal_id/);
});

test("flags sidecar hash mismatches as reviewer-ready warnings", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const decisionIntent = await loadFixture(decisionIntentFixtureUrl);
  const tamperedManifest = {
    ...manifest,
    output_hashes: {
      ...manifest.output_hashes,
      decision_intent_artifact: `sha256:${"0".repeat(64)}`,
      frontend_decision_intent_copy: `sha256:${"1".repeat(64)}`,
    },
  };

  const model = buildDashboardModel(snapshot, { manifest: tamperedManifest, decisionIntent });
  const html = renderDashboard(snapshot, { manifest: tamperedManifest, decisionIntent });

  assert.equal(model.reviewOperations.sidecarHashStatus.status, "mismatch");
  assert.match(html, /mismatch/);
  assert.match(html, /Decision intent artifact hash status is mismatch/);
  assert.match(html, /Decision intent frontend copy hash status is mismatch/);
});

test("loads decision-intent sidecar from the manifest artifact path", async () => {
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const decisionIntent = await loadFixture(decisionIntentFixtureUrl);
  const artifactUrl = artifactPathToUrl(manifest.decision_intent_artifact.path);
  const loaded = await loadDecisionIntent(async (url) => {
    assert.equal(url.pathname, "/frontend/pa-feitian-dashboard/fixtures/pa_feitian_decision_intent_v1.json");
    return {
      ok: true,
      status: 200,
      json: async () => decisionIntent,
    };
  }, manifest);

  assert.equal(artifactUrl, "/frontend/pa-feitian-dashboard/fixtures/pa_feitian_decision_intent_v1.json");
  assert.equal(loaded.schema_version, "pa_feitian_decision_intent_v1");
});

test("renders decision-intent missing, observation-only, and blocked states defensively", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(frontendManifestFixtureUrl);
  const decisionIntent = await loadFixture(decisionIntentFixtureUrl);
  const defensiveSidecar = {
    ...decisionIntent,
    intents: [
      {
        ...decisionIntent.intents[0],
        decision_state: "observation_runner",
        product_direction_tier: "observation_only",
        reason_codes: [
          ...decisionIntent.intents[0].reason_codes,
          "OBSERVATION_ONLY_PRODUCT_DIRECTION",
        ],
      },
      decisionIntent.intents[2],
    ],
    warnings: ["observation-only reviewer fixture"],
  };
  const model = buildDashboardModel(snapshot, { manifest, decisionIntent: defensiveSidecar });
  const html = renderDashboard(snapshot, { manifest, decisionIntent: defensiveSidecar });

  assert.equal(model.decisionIntent.stateCounts.observation_runner, 1);
  assert.equal(model.decisionIntent.stateCounts.watch, 1);
  assert.equal(model.decisionIntent.executionAllowedCount, 0);
  assert.equal(
    model.signals.find((signal) => signal.id === "paft_scorecard_0002_kq_m_shfe_au_20260629000000")
      .decisionIntent,
    null,
  );
  assert.match(html, /data-testid="decision-intent-missing"/);
  assert.match(html, /Snapshot signals missing decision-intent records/);
  assert.match(html, /Observation-only product-direction warning/);
  assert.match(html, /observation_only/);
  assert.match(html, /OBSERVATION_ONLY_PRODUCT_DIRECTION/);
  assert.match(html, /LIQ_RECOVERY_REQUIRED/);
  assert.match(html, /blocked/);
  assert.match(html, /Recovery required/);

  const missingSidecarHtml = renderDashboard(snapshot, { manifest });
  assert.match(missingSidecarHtml, /referenced_missing/);
  assert.match(missingSidecarHtml, /no sidecar payload is loaded/);
});

test("renders legacy decision_trace fallback for v0 snapshots", async () => {
  const snapshot = await loadFixture(legacyFixtureUrl);
  const model = buildDashboardModel(snapshot);
  const html = renderDashboard(snapshot);

  assert.equal(model.contract, "pa_feitian_snapshot_v0");
  assert.equal(model.totalSignals, 2);
  assert.equal(model.signals[0].decisionTrace.kind, "legacy");
  assert.equal(
    model.signals[0].decisionTrace.text,
    "fixture: underlying alert exists; option premium contract pending",
  );
  assert.match(html, /data-testid="legacy-decision-trace"/);
  assert.match(html, /legacy decision_trace/);
  assert.match(html, /fixture: underlying alert exists/);
  assert.doesNotMatch(html, /data-testid="decision-trace-v1-nodes"/);

  const blockedSignal = model.signals.find((signal) => signal.status === "data_blocked");
  assert.ok(blockedSignal);
  assert.deepEqual(missingOptionalFields(blockedSignal).slice(0, 2), [
    "Decision",
    "Decision trace",
  ]);
});

test("renders an explicit empty state when the contract has no signals", async () => {
  const snapshot = await loadFixture();
  const emptySnapshot = {
    ...snapshot,
    summary: { ...snapshot.summary, signals_total: 0, by_status: {} },
    signals: [],
    warnings: [],
  };

  const html = renderDashboard(emptySnapshot);

  assert.match(html, /data-testid="empty-signals"/);
  assert.match(html, /No signals in this snapshot/);
  assert.doesNotMatch(html, /data-testid="signal-table"/);
});

test("copies a generated snapshot artifact into a frontend fixture target", async () => {
  const snapshot = await loadFixture();
  const manifest = await loadFixture(manifestFixtureUrl);
  const tempRoot = await mkdtemp(join(tmpdir(), "pa-feitian-dashboard-"));
  const generatedSource = join(tempRoot, "generated-pa-feitian-snapshot.json");
  const copiedOut = join(tempRoot, "fixtures", "pa_feitian_snapshot_v1.json");
  const generatedSnapshot = {
    ...snapshot,
    generated_at_utc: "2026-07-08T00:00:00Z",
    run_config: { ...snapshot.run_config, mode: "scorecard" },
    summary: {
      ...snapshot.summary,
      signals_total: 1,
      by_status: { keep: 1 },
      integration_milestone: "generated_snapshot_copy_smoke",
    },
    signals: [
      {
        ...snapshot.signals[1],
        id: "paft_generated_0001",
        status: "keep",
        decision: "keep",
      },
    ],
    warnings: ["generated snapshot copy smoke"],
  };

  await writeFile(generatedSource, JSON.stringify(generatedSnapshot), "utf8");
  const copyResult = await copySnapshotFixture({ source: generatedSource, out: copiedOut, quiet: true });
  const copiedSnapshot = JSON.parse(await readFile(copiedOut, "utf8"));
  const html = renderDashboard(copiedSnapshot, { manifest });

  assert.equal(copyResult.changed, true);
  assert.equal(copiedSnapshot.run_config.mode, "scorecard");
  assert.equal(copiedSnapshot.summary.integration_milestone, "generated_snapshot_copy_smoke");
  assert.match(html, /Generated snapshot/);
  assert.match(html, /data-testid="run-manifest-provenance"/);
  assert.match(html, /paft_generated_0001/);
  assert.match(html, /scorecard/);
  assert.match(html, /generated snapshot copy smoke/);
});

test("copies and renders a legacy v0 artifact for fallback smoke coverage", async () => {
  const snapshot = await loadFixture(legacyFixtureUrl);
  const tempRoot = await mkdtemp(join(tmpdir(), "pa-feitian-dashboard-legacy-"));
  const generatedSource = join(tempRoot, "generated-pa-feitian-snapshot-v0.json");
  const copiedOut = join(tempRoot, "fixtures", "pa_feitian_snapshot_v0.json");

  await writeFile(generatedSource, JSON.stringify(snapshot), "utf8");
  const copyResult = await copySnapshotFixture({ source: generatedSource, out: copiedOut, quiet: true });
  const copiedSnapshot = JSON.parse(await readFile(copiedOut, "utf8"));
  const html = renderDashboard(copiedSnapshot);

  assert.equal(copyResult.changed, true);
  assert.equal(copyResult.snapshot.schema_version, "pa_feitian_snapshot_v0");
  assert.match(html, /legacy decision_trace/);
  assert.match(html, /fixture: underlying alert exists/);
});

test("frontend files only reference the fixture contract, not raw data pipelines", async () => {
  const texts = await Promise.all(appFiles.map((file) => readFile(file, "utf8")));
  const frontendSource = texts.join("\n");
  const forbiddenReferences = [
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
  ];

  assert.match(frontendSource, /fixtures\/pa_feitian_snapshot_v1\.json/);
  assert.doesNotMatch(frontendSource, /src\/tests\/fixtures\/pa_feitian_snapshot_v1\.json/);
  for (const forbidden of forbiddenReferences) {
    assert.doesNotMatch(frontendSource, new RegExp(forbidden.replace("/", "\\/")));
  }
});
