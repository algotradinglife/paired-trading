import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  STATUS_DEFINITIONS,
  buildDashboardModel,
  missingOptionalFields,
  renderDashboard,
} from "../app.mjs";
import { copySnapshotFixture } from "../scripts/copy-snapshot-fixture.mjs";

const fixtureUrl = new URL("../fixtures/pa_feitian_snapshot_v0.json", import.meta.url);
const appFiles = [
  new URL("../index.html", import.meta.url),
  new URL("../app.mjs", import.meta.url),
  new URL("../styles.css", import.meta.url),
];

async function loadFixture() {
  return JSON.parse(await readFile(fixtureUrl, "utf8"));
}

test("renders summary, warning, signal table, and drill-down from fixture", async () => {
  const snapshot = await loadFixture();
  const html = renderDashboard(snapshot);

  assert.match(html, /Total signals/);
  assert.match(html, /paft_fixture_0001/);
  assert.match(html, /paft_fixture_0002/);
  assert.match(html, /data-testid="signal-table"/);
  assert.match(html, /data-testid="signal-drill-down"/);
  assert.match(html, /snapshot v0 is a contract fixture/);
  assert.match(html, /premium-space outcomes must remain separate/);
});

test("surfaces defensive states and missing optional fields", async () => {
  const snapshot = await loadFixture();
  const model = buildDashboardModel(snapshot);
  const html = renderDashboard(snapshot);

  assert.equal(model.totalSignals, 2);
  assert.equal(model.statusCounts.advisory, 1);
  assert.equal(model.statusCounts.data_blocked, 1);
  assert.ok("model_dominated" in STATUS_DEFINITIONS);
  assert.match(html, /model_dominated/);
  assert.match(html, /Missing Optional Fields/);

  const blockedSignal = model.signals.find((signal) => signal.status === "data_blocked");
  assert.ok(blockedSignal);
  assert.deepEqual(missingOptionalFields(blockedSignal).slice(0, 2), [
    "Decision",
    "Decision trace",
  ]);
  assert.ok(blockedSignal.missingOptional.includes("IV rank"));
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
  const tempRoot = await mkdtemp(join(tmpdir(), "pa-feitian-dashboard-"));
  const generatedSource = join(tempRoot, "generated-pa-feitian-snapshot.json");
  const copiedOut = join(tempRoot, "fixtures", "pa_feitian_snapshot_v0.json");
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
        ...snapshot.signals[0],
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
  const html = renderDashboard(copiedSnapshot);

  assert.equal(copyResult.changed, true);
  assert.equal(copiedSnapshot.run_config.mode, "scorecard");
  assert.equal(copiedSnapshot.summary.integration_milestone, "generated_snapshot_copy_smoke");
  assert.match(html, /paft_generated_0001/);
  assert.match(html, /scorecard/);
  assert.match(html, /generated snapshot copy smoke/);
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

  assert.match(frontendSource, /fixtures\/pa_feitian_snapshot_v0\.json/);
  assert.doesNotMatch(frontendSource, /src\/tests\/fixtures\/pa_feitian_snapshot_v0\.json/);
  for (const forbidden of forbiddenReferences) {
    assert.doesNotMatch(frontendSource, new RegExp(forbidden.replace("/", "\\/")));
  }
});
