#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const contractPath = resolve(
  repoRoot,
  "docs/research/pa-feitian-m6-exploratory-swing-views-contract-v1.json",
);
const candidateAuditPath = resolve(
  repoRoot,
  "doc/repro/pa-feitian-phase1-data-capability-2026-07-30/candidate_interface_audit_v1.json",
);
const artifactPath = resolve(packetDir, "exploratory_swing_views_v1.json");
const readmePath = resolve(packetDir, "README.md");
const python = process.env.PA_FEITIAN_PYTHON || "python3";

function bytes(path) {
  return readFileSync(path);
}

function json(path) {
  return JSON.parse(bytes(path).toString("utf8"));
}

function digest(content) {
  return `sha256:${createHash("sha256").update(content).digest("hex")}`;
}

const contract = json(contractPath);
const candidateAudit = json(candidateAuditPath);
const artifact = json(artifactPath);
const families = ["SHFE.au", "SHFE.ag", "CZCE.TA", "CZCE.MA", "SHFE.cu", "DCE.i"];
const cadences = ["daily", "hour", "min15", "min5"];
const regimes = ["quiet", "typical", "volatile"];

assert.equal(
  contract.schema_version,
  "pa_feitian_m6_exploratory_swing_views_contract_v1",
);
assert.equal(contract.issue_number, 53);
assert.equal(contract.audit_as_of_local_date, "2026-07-30");
assert.equal(contract.runtime_input.binding, "QUANT_DATA_ROOT");
assert.equal(contract.runtime_input.access, "read_only");
assert.deepEqual(contract.runtime_input.interfaces, [
  "underlying_contract_ohlc_activity",
  "option_premium_ohlc_activity",
]);
assert.equal(contract.window_protocol.completed_observations, 20);
assert.equal(contract.window_protocol.stride_observations, 20);
assert.equal(
  contract.window_protocol.representative_requires_daily_option_coverage,
  true,
);
assert.equal(
  contract.window_protocol.post_audit_rows,
  "excluded_before_series_inventory_and_window_partitioning",
);
assert.equal(
  contract.window_protocol.future_only_files,
  "excluded_from_source_inventory",
);
assert.equal(
  contract.window_protocol.selection_uses_strategy_outcomes_or_profitability,
  false,
);
assert.equal(
  contract.option_premium_overlay.required_distinct_dates_for_comparable_path,
  20,
);
assert.equal(
  contract.option_premium_overlay.duplicate_date_series_in_path_distribution,
  false,
);
assert.equal(
  contract.option_premium_overlay.incomplete_fragment_series_in_path_distribution,
  false,
);
assert.equal(contract.output.atomic_same_directory_replace, true);
assert.equal(contract.output.output_inside_data_root, false);
assert.equal(
  contract.output.output_may_overwrite_contract_or_candidate_audit,
  false,
);
assert.equal(contract.guardrails.source_refresh_or_mutation, false);
assert.equal(contract.guardrails.performance_calculation, false);
assert.equal(contract.guardrails.profitability_ranking, false);

assert.equal(
  candidateAudit.schema_version,
  "pa_feitian_phase1_candidate_interface_audit_v1",
);
assert.equal(artifact.schema_version, "pa_feitian_m6_exploratory_swing_views_v1");
assert.equal(artifact.issue_number, 53);
assert.equal(artifact.audit_as_of_local_date, "2026-07-30");
assert.equal(artifact.study_label, "exploratory_historical_data_view_only");
assert.equal(artifact.contract.sha256, digest(bytes(contractPath)));
assert.equal(
  artifact.candidate_interface_evidence.sha256,
  digest(bytes(candidateAuditPath)),
);
assert.equal(
  artifact.candidate_interface_evidence.source_inventory_sha256,
  candidateAudit.source.inventory_sha256,
);
assert.equal(artifact.source.access, "read_only");
assert.equal(artifact.source.source_refresh_performed, false);
assert.equal(artifact.source.filesystem_timestamps_used_as_freshness, false);
assert.equal(artifact.source.post_audit_rows_excluded_before_partitioning, true);
assert.equal(artifact.source.future_only_files_excluded_from_inventory, true);
assert.equal(artifact.source.daily_underlying_files_in_frozen_inventory, 326);
assert.equal(artifact.source.daily_option_files_in_frozen_inventory, 7459);

assert.deepEqual(
  artifact.interface_availability.map((row) => row.instrument_family),
  families,
);
assert.deepEqual(
  artifact.family_window_summaries.map((row) => row.instrument_family),
  families,
);
const expectedPopulations = new Map([
  ["SHFE.au", [405, 405, 186]],
  ["SHFE.ag", [651, 651, 319]],
  ["CZCE.TA", [379, 351, 26]],
  ["CZCE.MA", [379, 345, 30]],
  ["SHFE.cu", [750, 750, 324]],
  ["DCE.i", [662, 662, 109]],
]);
for (const summary of artifact.family_window_summaries) {
  const all = summary.all_complete_windows;
  const eligible = summary.representative_eligible_clean_windows;
  const expected = expectedPopulations.get(summary.instrument_family);
  assert.deepEqual(
    [all.window_count, all.quality_counts.clean, eligible.window_count],
    expected,
  );
  assert(eligible.window_count <= all.quality_counts.clean);
  assert.equal(summary.latest_window_calendar_lag_days >= 0, true);
  for (const population of [
    all.clean_window_total_excursion_pct,
    eligible.total_excursion_pct,
  ]) {
    assert.deepEqual(Object.keys(population), ["p20", "p50", "p80"]);
    assert(Object.values(population).every(Number.isFinite));
  }
}
for (const family of artifact.interface_availability) {
  assert.deepEqual(
    family.cadences.map((row) => row.cadence),
    cadences,
  );
  for (const cadence of family.cadences) {
    assert.equal(cadence.interfaces.underlying.available, true);
    assert.equal(cadence.interfaces.option_premium.available, true);
    assert.equal(cadence.interfaces.option_premium.activity.selection_threshold, null);
    for (const interfaceName of ["underlying", "option_premium"]) {
      const source = cadence.interfaces[interfaceName];
      assert.deepEqual(Object.keys(source.coverage).sort(), [
        "maximum_observation_timestamp",
        "minimum_observation_timestamp",
      ]);
      assert.deepEqual(Object.keys(source.freshness).sort(), [
        "calendar_lag_days",
        "latest_observation",
        "status",
      ]);
    }
  }
}

assert.equal(artifact.representative_swing_views.length, 18);
for (const family of families) {
  const views = artifact.representative_swing_views.filter(
    (view) => view.instrument_family === family,
  );
  assert.deepEqual(views.map((view) => view.regime_slice), regimes);
  for (const view of views) {
    assert.equal(view.observation_count, 20);
    assert.equal(view.input_quality.status, "clean");
    assert.equal(view.freshness.status, "stale");
    assert.equal(view.freshness.calendar_lag_days >= 0, true);
    assert.equal(typeof view.descriptive_metrics.total_excursion_pct, "number");
    assert.equal(view.normalized_path_encoding.bar_count, 20);
    assert.equal(view.normalized_path_encoding.raw_prices_published, false);
    assert.equal(view.normalized_ohlc_path.length, 20);
    assert.equal(view.normalized_ohlc_path[0].open_index, 100);
    for (const [index, bar] of view.normalized_ohlc_path.entries()) {
      assert.equal(bar.bar_index, index);
      const values = [
        bar.open_index,
        bar.high_index,
        bar.low_index,
        bar.close_index,
      ];
      assert(values.every((value) => Number.isFinite(value) && value > 0));
      assert(bar.high_index >= bar.low_index);
      assert(bar.high_index >= bar.open_index);
      assert(bar.high_index >= bar.close_index);
      assert(bar.low_index <= bar.open_index);
      assert(bar.low_index <= bar.close_index);
    }
    const overlay = view.option_premium_overlay;
    assert.equal(overlay.selection_influence, false);
    assert(overlay.observation_count > 0);
    assert(overlay.coherent_observation_count > 0);
    assert(overlay.anonymous_series_with_observations > 0);
    assert(["clean", "messy", "invalid"].includes(overlay.quality_status));
    assert.equal(
      overlay.input_quality_violation_observation_count,
      overlay.nonpositive_or_missing_observation_count
        + overlay.ohlc_incoherent_observation_count
        + overlay.duplicate_date_observation_count,
    );
    const coverage = overlay.distinct_date_coverage;
    assert.equal(coverage.required_for_comparable_path, 20);
    assert(
      Object.values(coverage.distribution).every(
        (value) => Number.isFinite(value) && value >= 1 && value <= 20,
      ),
    );
    assert(coverage.two_point_fragment_series_count >= 0);
    assert(coverage.incomplete_fragment_series_count >= 0);
    assert(coverage.duplicate_date_series_count >= 0);
    const comparable = overlay.comparable_complete_path_metrics;
    assert.equal(comparable.required_distinct_date_count, 20);
    assert(["available", "unavailable"].includes(comparable.status));
    assert(
      comparable.anonymous_series_count
        <= overlay.anonymous_series_with_observations
          - Math.max(
            coverage.incomplete_fragment_series_count,
            coverage.duplicate_date_series_count,
          ),
    );
    if (comparable.status === "available") {
      assert(comparable.anonymous_series_count > 0);
      for (const distribution of [
        comparable.close_path_change_pct_distribution,
        comparable.total_excursion_pct_distribution,
      ]) {
        assert(Object.values(distribution).every(Number.isFinite));
      }
    } else {
      assert.equal(comparable.anonymous_series_count, 0);
      assert.equal(typeof comparable.reason, "string");
      assert.equal("close_path_change_pct_distribution" in comparable, false);
      assert.equal("total_excursion_pct_distribution" in comparable, false);
    }
  }
}

assert.deepEqual(
  Object.keys(artifact.quality_examples).sort(),
  ["clean", "invalid", "messy", "stale"],
);
assert.equal(artifact.quality_examples.clean.quality_status, "clean");
assert.equal(artifact.quality_examples.messy.quality_status, "messy");
assert.equal(artifact.quality_examples.invalid.quality_status, "invalid");
assert.equal(artifact.quality_examples.stale.quality_status, "clean");
assert.equal(artifact.evidence_separation.preregistered_evidence, "not produced");
assert.equal(
  artifact.evidence_separation.future_live_or_shadow,
  "not authorized or assessed",
);
assert.equal(artifact.evidence_separation.issue_51_unblocked, false);
assert.equal(artifact.public_safety.raw_rows, false);
assert.equal(artifact.public_safety.raw_ohlc_values, false);
assert.equal(artifact.public_safety.strategy_outcomes, false);
assert.equal(artifact.public_safety.profitability_metrics, false);

const publicText = Buffer.concat([
  bytes(contractPath),
  bytes(candidateAuditPath),
  bytes(artifactPath),
  bytes(readmePath),
]).toString("utf8");
assert.doesNotMatch(
  publicText,
  /(?:^|[\s"'])\/(?:home|mnt|Users|var|tmp|root)\//,
  "public packet contains an absolute local path",
);
assert.doesNotMatch(
  publicText,
  /\.parquet|\.csv/i,
  "public packet contains a source filename",
);
assert.doesNotMatch(
  publicText,
  /\b(?:SHFE|CZCE|DCE)\.[A-Za-z]+\d/,
  "public packet contains a raw contract identifier",
);
assert.doesNotMatch(
  publicText,
  /(?:api[_-]?key|access[_-]?token|private[_-]?key|password)\s*[:=]/i,
  "public packet appears to contain a credential",
);
assert.doesNotMatch(
  publicText,
  /(?:\bgithub_pat_|\bgh[opusr]_|\bsk-(?:proj-)?|\bxox[baprs]-|\bAKIA[0-9A-Z]{12,}|\bAIza[0-9A-Za-z_-]{20,}|\bya29\.)/i,
  "public packet contains a common token prefix",
);

const readme = bytes(readmePath).toString("utf8");
for (const summary of artifact.family_window_summaries) {
  const all = summary.all_complete_windows;
  const eligible = summary.representative_eligible_clean_windows;
  const row = [
    summary.instrument_family,
    all.window_count,
    all.quality_counts.clean,
    eligible.window_count,
    all.clean_window_total_excursion_pct.p20,
    all.clean_window_total_excursion_pct.p50,
    all.clean_window_total_excursion_pct.p80,
    eligible.total_excursion_pct.p20,
    eligible.total_excursion_pct.p50,
    eligible.total_excursion_pct.p80,
  ].join(" | ");
  assert(readme.includes(`| ${row} |`), `README population row drifted: ${row}`);
}
for (const view of artifact.representative_swing_views) {
  const overlay = view.option_premium_overlay;
  const coverage = overlay.distinct_date_coverage.distribution;
  const comparable = overlay.comparable_complete_path_metrics;
  const row = [
    view.instrument_family,
    view.regime_slice,
    `${view.start_date} to ${view.end_date}`,
    view.descriptive_metrics.total_excursion_pct,
    view.descriptive_metrics.realized_variability_annualized_pct,
    view.normalized_ohlc_path.length,
    overlay.anonymous_series_with_observations,
    `${coverage.p20}/${coverage.p50}/${coverage.p80}`,
    comparable.anonymous_series_count,
    comparable.status,
  ].join(" | ");
  assert(readme.includes(`| ${row} |`), `README representative row drifted: ${row}`);
}
for (const family of artifact.interface_availability) {
  const daily = family.cadences.find((row) => row.cadence === "daily");
  const underlying = daily.interfaces.underlying;
  const option = daily.interfaces.option_premium;
  const row = [
    family.instrument_family,
    underlying.file_count.toLocaleString("en-US"),
    option.file_count.toLocaleString("en-US"),
    `${(option.activity.share * 100).toFixed(4)}%`,
    option.ohlc_quality.violation_rows.toLocaleString("en-US"),
  ].join(" | ");
  assert(readme.includes(`| ${row} |`), `README availability row drifted: ${row}`);
}
const totalWindows = artifact.family_window_summaries.reduce(
  (total, row) => total + row.all_complete_windows.window_count,
  0,
);
const totalEligible = artifact.family_window_summaries.reduce(
  (total, row) => total + row.representative_eligible_clean_windows.window_count,
  0,
);
assert(readme.includes(`${totalWindows.toLocaleString("en-US")} complete windows`));
assert(readme.includes(`${totalEligible.toLocaleString("en-US")} representative-eligible`));

if (process.env.PA_FEITIAN_REGENERATE === "1") {
  assert(process.env.QUANT_DATA_ROOT, "QUANT_DATA_ROOT is required for regeneration");
  const temporary = mkdtempSync(join(tmpdir(), "pa-feitian-swing-views-"));
  const rebuilt = join(temporary, "exploratory_swing_views_v1.json");
  try {
    const completed = spawnSync(
      python,
      [
        "src/scripts/build_pa_feitian_exploratory_swing_views.py",
        "--contract",
        contractPath,
        "--candidate-audit",
        candidateAuditPath,
        "--data-root",
        process.env.QUANT_DATA_ROOT,
        "--output",
        rebuilt,
        "--workers",
        process.env.PA_FEITIAN_WORKERS || "8",
      ],
      {
        cwd: repoRoot,
        env: { ...process.env, PYTHONPATH: resolve(repoRoot, "src") },
        encoding: "utf8",
      },
    );
    assert.equal(completed.status, 0, completed.stderr || completed.stdout);
    assert.deepEqual(bytes(rebuilt), bytes(artifactPath));
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}

console.log(JSON.stringify({
  ok: true,
  issue: 53,
  families: artifact.family_window_summaries.length,
  representative_views: artifact.representative_swing_views.length,
  underlying_windows: artifact.family_window_summaries.reduce(
    (total, row) => total + row.all_complete_windows.window_count,
    0,
  ),
  artifact_sha256: digest(bytes(artifactPath)),
}));
