import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  DECISION_STATE_DEFINITIONS,
  SNAPSHOT_MODE_DEFINITIONS,
  STATUS_DEFINITIONS,
  SUPPORTED_DECISION_INTENT_VERSIONS,
  TRACE_NODE_STATUS_DEFINITIONS,
  artifactPathToUrl,
  buildDashboardModel,
  loadDecisionIntent,
  missingOptionalFields,
  normalizeDecisionIntentSidecar,
  renderDashboard,
} from "../app.mjs";
import { copySnapshotFixture } from "../scripts/copy-snapshot-fixture.mjs";

const fixtureUrl = new URL("../fixtures/pa_feitian_snapshot_v1.json", import.meta.url);
const legacyFixtureUrl = new URL("../fixtures/pa_feitian_snapshot_v0.json", import.meta.url);
const frontendManifestFixtureUrl = new URL("../fixtures/pa_feitian_run_manifest_v1.json", import.meta.url);
const decisionIntentFixtureUrl = new URL("../fixtures/pa_feitian_decision_intent_v1.json", import.meta.url);
const manifestFixtureUrl = new URL("../../../src/tests/fixtures/pa_feitian_run_manifest_v1.json", import.meta.url);
const appFiles = [
  new URL("../index.html", import.meta.url),
  new URL("../app.mjs", import.meta.url),
  new URL("../styles.css", import.meta.url),
];

async function loadFixture(url = fixtureUrl) {
  return JSON.parse(await readFile(url, "utf8"));
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
  assert.match(html, /Fixture snapshot/);
  assert.match(html, /data-testid="run-manifest-empty"/);
  assert.match(html, /Manifest metadata unavailable/);
  assert.match(html, /Score Today underlying signal/);
  assert.match(html, /scorecard_record:1/);
  assert.match(html, /sha256:/);
  assert.match(html, /iv_regime/);
  assert.match(html, /snapshot v1 is a shadow contract fixture/);
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
  assert.match(generatedHtml, /data-testid="run-manifest-provenance"/);
  assert.match(generatedHtml, /Generated snapshot/);
  assert.match(generatedHtml, /Scorecard artifact/);
  assert.match(generatedHtml, /Snapshot artifact/);
  assert.match(generatedHtml, /src\/tests\/fixtures\/pa_feitian_scorecard_v1\.json/);
  assert.match(generatedHtml, /fixture_fallback/);
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
  const decisionIntent = await loadFixture(decisionIntentFixtureUrl);
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
  assert.equal(model.decisionIntent.stateCounts.trade_ready, 1);
  assert.equal(model.decisionIntent.executionAllowedCount, 1);

  const tradeReadySignal = model.signals.find((signal) => signal.decisionIntent?.decision_state === "trade_ready");
  assert.ok(tradeReadySignal);
  assert.equal(tradeReadySignal.decisionIntent.execution_allowed, true);
  assert.equal(tradeReadySignal.decisionIntent.product_direction_tier, "aligned_trade_candidate");

  assert.match(html, /data-testid="decision-intent-review"/);
  assert.match(html, /data-testid="decision-intent-sidecar"/);
  assert.match(html, /data-testid="decision-intent-no-lookahead"/);
  assert.match(html, /Decision intent artifact/);
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
  assert.match(html, /sha256:46381c5371ddbe46a554640294f26dba20bf72006c8fc5298142ac9facf82f53/);
  assert.match(html, /Posterior diagnostic fields are present/);
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
  ];

  assert.match(frontendSource, /fixtures\/pa_feitian_snapshot_v1\.json/);
  assert.doesNotMatch(frontendSource, /src\/tests\/fixtures\/pa_feitian_snapshot_v1\.json/);
  for (const forbidden of forbiddenReferences) {
    assert.doesNotMatch(frontendSource, new RegExp(forbidden.replace("/", "\\/")));
  }
});
