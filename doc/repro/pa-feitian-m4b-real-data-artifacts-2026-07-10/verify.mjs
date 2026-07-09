import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

import { buildDashboardModel, renderDashboard } from "../../../frontend/pa-feitian-dashboard/app.mjs";

const artifactRoot = new URL("./", import.meta.url);
const repoRoot = new URL("../../../", import.meta.url);

function repoUrl(path) {
  return new URL(path, repoRoot);
}

async function readJson(urlOrPath) {
  const url = typeof urlOrPath === "string" ? new URL(urlOrPath, artifactRoot) : urlOrPath;
  return JSON.parse(await readFile(url, "utf8"));
}

async function readRaw(urlOrPath) {
  const url = typeof urlOrPath === "string" ? new URL(urlOrPath, artifactRoot) : urlOrPath;
  return readFile(url);
}

function sha256(raw) {
  return `sha256:${createHash("sha256").update(raw).digest("hex")}`;
}

async function assertFileHash(repoRelativePath, expectedHash, label) {
  const actualHash = sha256(await readRaw(repoUrl(repoRelativePath)));
  assert.equal(actualHash, expectedHash, `${label} hash`);
  return actualHash;
}

function assertManifestHashLinks(manifest, label) {
  assert.equal(manifest.schema_version, "pa_feitian_run_manifest_v1", `${label} schema`);
  assert.equal(manifest.data_access.status, "real_data_available", `${label} data access`);
  assert.equal(
    manifest.input_hashes.scorecard_artifact,
    manifest.scorecard_artifact.sha256,
    `${label} scorecard input hash link`,
  );
  assert.equal(
    manifest.output_hashes.snapshot_artifact,
    manifest.snapshot_artifact.sha256,
    `${label} snapshot output hash link`,
  );
  assert.equal(
    manifest.output_hashes.decision_intent_artifact,
    manifest.decision_intent_artifact.sha256,
    `${label} decision-intent output hash link`,
  );
}

const scorecardPath =
  "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/score_today_cn_metal_120d_2026-07-10.json";
const sourceSnapshotPath =
  "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_snapshot_v1.json";
const sourceManifestPath =
  "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_run_manifest_with_decision_intent_v1.json";
const sourceSidecarPath =
  "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_decision_intent_v1.json";
const dashboardSnapshotPath =
  "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/dashboard/pa_feitian_snapshot_v1.json";
const dashboardManifestPath =
  "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/dashboard/pa_feitian_run_manifest_v1.json";
const dashboardSidecarPath =
  "doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/dashboard/pa_feitian_decision_intent_v1.json";

const scorecard = await readJson(repoUrl(scorecardPath));
const sourceSnapshot = await readJson(repoUrl(sourceSnapshotPath));
const sourceManifest = await readJson(repoUrl(sourceManifestPath));
const sourceSidecar = await readJson(repoUrl(sourceSidecarPath));
const dashboardSnapshot = await readJson(repoUrl(dashboardSnapshotPath));
const dashboardManifest = await readJson(repoUrl(dashboardManifestPath));
const dashboardSidecar = await readJson(repoUrl(dashboardSidecarPath));

assert.equal(scorecard.pool, "CN_METAL");
assert.equal(scorecard.instrument_class, "cn_metal_futures");
assert.equal(scorecard.window_days, 120);
assert.equal(scorecard.scored.length, 13, "score_today scored rows");
assert.equal(
  scorecard.scored.filter((record) => Array.isArray(record.options_calls) && record.options_calls.length).length,
  4,
  "score_today scored rows with options_calls",
);

assert.equal(sourceSnapshot.schema_version, "pa_feitian_snapshot_v1");
assert.equal(sourceSnapshot.signals.length, 4, "source snapshot signals");
assert.equal(sourceSidecar.schema_version, "pa_feitian_decision_intent_v1");
assert.equal(sourceSidecar.intents.length, 4, "source sidecar intents");
assert.deepEqual(
  new Set(sourceSnapshot.signals.map((signal) => signal.id)),
  new Set(sourceSidecar.intents.map((intent) => intent.signal_id)),
  "snapshot signals match decision-intent signals",
);

assert.deepEqual(dashboardSnapshot, sourceSnapshot, "dashboard snapshot copy");
assert.deepEqual(dashboardSidecar, sourceSidecar, "dashboard decision-intent copy");

assertManifestHashLinks(sourceManifest, "source review manifest");
assertManifestHashLinks(dashboardManifest, "dashboard manifest");

await assertFileHash(scorecardPath, sourceManifest.scorecard_artifact.sha256, "scorecard artifact");
await assertFileHash(sourceSnapshotPath, sourceManifest.snapshot_artifact.sha256, "source snapshot artifact");
await assertFileHash(sourceSidecarPath, sourceManifest.decision_intent_artifact.sha256, "source sidecar artifact");
await assertFileHash(dashboardSnapshotPath, sourceManifest.output_hashes.frontend_copy, "dashboard snapshot copy");
await assertFileHash(
  dashboardSidecarPath,
  sourceManifest.output_hashes.frontend_decision_intent_copy,
  "dashboard sidecar copy from source manifest",
);
await assertFileHash(
  dashboardManifest.decision_intent_artifact.path,
  dashboardManifest.decision_intent_artifact.sha256,
  "dashboard sidecar artifact",
);
await assertFileHash(
  dashboardManifest.frontend_copy_path,
  dashboardManifest.output_hashes.frontend_copy,
  "dashboard manifest frontend snapshot copy",
);
await assertFileHash(
  dashboardSidecarPath,
  dashboardManifest.output_hashes.frontend_decision_intent_copy,
  "dashboard manifest frontend sidecar copy",
);

const model = buildDashboardModel(dashboardSnapshot, {
  manifest: dashboardManifest,
  decisionIntent: dashboardSidecar,
});
const html = renderDashboard(dashboardSnapshot, {
  manifest: dashboardManifest,
  decisionIntent: dashboardSidecar,
});

assert.equal(model.snapshotMode, "generated");
assert.equal(model.totalSignals, 4);
assert.equal(model.manifest.dataAccess.status, "real_data_available");
assert.equal(model.decisionIntent.status, "loaded");
assert.equal(model.decisionIntent.intents.length, 4);
assert.equal(model.reviewOperations.sidecarHashStatus.status, "match");
assert.ok(model.reviewOperations.artifactRows.every((row) => row.hashStatus === "match"));
assert.match(html, /real_data_available/);
assert.match(html, /Explicit generated scorecard artifact/);
assert.match(html, /data-testid="decision-intent-review"/);

console.log(
  JSON.stringify(
    {
      ok: true,
      scorecard_rows: scorecard.scored.length,
      scorecard_rows_with_options: 4,
      snapshot_signals: sourceSnapshot.signals.length,
      decision_intents: sourceSidecar.intents.length,
      data_access: dashboardManifest.data_access.status,
      snapshot_mode: model.snapshotMode,
      sidecar_hash_status: model.reviewOperations.sidecarHashStatus.status,
      html_length: html.length,
    },
    null,
    2,
  ),
);
