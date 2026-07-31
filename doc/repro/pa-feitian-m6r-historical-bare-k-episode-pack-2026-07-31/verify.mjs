#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const contractPath = join(
  repoRoot,
  "docs/research/pa-feitian-m6r-historical-bare-k-episode-pack-contract-v1.json",
);
const names = {
  manifest: "episode_manifest_v1.json",
  blind: "blind_episode_pack_v1.json",
  sealed_reveal: "sealed_reveal_pack_v1.json",
  coverage: "coverage_and_exclusions_v1.json",
  annotation_template: "blind_annotation_template_v1.json",
};

function bytes(path) {
  return readFileSync(path);
}

function parse(path) {
  return JSON.parse(bytes(path).toString("utf8"));
}

function sha256(value) {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

const contract = parse(contractPath);
const artifact = Object.fromEntries(
  Object.entries(names).map(([name, filename]) => [name, parse(join(here, filename))]),
);

assert.equal(
  sha256(bytes(contractPath)),
  "sha256:f52e680145ef7251bab6b1d902d9604f31f361a9ac8172815ddd969c6e64308f",
);
assert.equal(contract.schema_version, "pa_feitian_m6r_historical_bare_k_episode_pack_contract_v1");
assert.equal(contract.issue_number, 64);
assert.equal(contract.blind_reveal_protocol.blind_pack_exposes_family_exchange_or_product, false);
assert.equal(contract.blind_reveal_protocol.blind_pack_exposes_calendar_dates_or_era, false);
assert.equal(contract.quality_protocol.invalid_or_missing_rows_may_be_skipped_or_concatenated_across, false);
assert.equal(contract.episode_protocol.same_family_selected_full_calendar_intervals_may_overlap_across_sources, false);
assert.equal(
  contract.episode_protocol.ranking_or_labeling_uses_reveal_direction_magnitude_metrics_outcomes_or_profitability,
  false,
);
assert.equal(
  contract.public_representation.anonymous_episode_id,
  "opaque deterministic identifier derived only from the canonical normalized pre-anchor blind payload; no provenance or selection metadata participates",
);

assert.equal(
  sha256(bytes(join(here, names.manifest))),
  "sha256:2e2c2c9f60afe38be8fabaf742dcb2bacb0f650e60df851f0326002dfa01b195",
);
for (const [name, filename] of Object.entries(names).filter(([name]) => name !== "manifest")) {
  assert.equal(
    artifact.manifest.artifact_bindings[name].public_location,
    `doc/repro/pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31/${filename}`,
  );
  assert.equal(
    artifact.manifest.artifact_bindings[name].sha256,
    sha256(bytes(join(here, filename))),
  );
}
assert.equal(artifact.manifest.episode_count, 72);
assert.equal(artifact.manifest.episode_mapping_in_manifest, false);
assert.equal(artifact.manifest.strategy_or_performance_claim, false);
assert.equal(artifact.manifest.m7_authorized, false);

const blind = artifact.blind;
assert.deepEqual(Object.keys(blind).sort(), ["episode_count", "episodes", "issue_number", "schema_version"]);
assert.equal(blind.schema_version, "pa_feitian_m6r_blind_bare_k_episode_pack_v1");
assert.equal(blind.episode_count, 72);
assert.equal(blind.episodes.length, 72);
for (const episode of blind.episodes) {
  assert.deepEqual(Object.keys(episode).sort(), ["bars", "episode_id"]);
  assert.match(episode.episode_id, /^M6R-[0-9a-f]{20}$/);
  assert.equal(episode.bars.length, 40);
  assert.deepEqual(episode.bars.map((bar) => bar.bar_index), Array.from({ length: 40 }, (_, i) => i - 39));
  for (const bar of episode.bars) {
    assert.deepEqual(Object.keys(bar).sort(), ["bar_index", "close_index", "high_index", "low_index", "open_index"]);
    for (const key of ["open_index", "high_index", "low_index", "close_index"]) {
      assert.equal(Number.isFinite(bar[key]) && bar[key] > 0, true);
    }
    assert.equal(bar.high_index >= bar.low_index, true);
    assert.equal(bar.high_index >= bar.open_index && bar.high_index >= bar.close_index, true);
    assert.equal(bar.low_index <= bar.open_index && bar.low_index <= bar.close_index, true);
  }
}
assert.deepEqual(
  blind.episodes.map((episode) => episode.episode_id),
  [...blind.episodes.map((episode) => episode.episode_id)].sort(),
);
assert.equal(new Set(blind.episodes.map((episode) => episode.episode_id)).size, 72);
const blindText = JSON.stringify(blind).toLowerCase();
for (const forbidden of ["family", "exchange", "product", "contract", "source", "timestamp", "date", "era", "stratum", "activity", "control", "sampling", "reveal", "future"]) {
  assert.equal(blindText.includes(forbidden), false, `blind packet leaks ${forbidden}`);
}

const annotations = artifact.annotation_template;
assert.deepEqual(Object.keys(annotations).sort(), ["annotations", "blind_pack_sha256", "schema_version"]);
assert.equal(annotations.schema_version, "pa_feitian_m6r_blind_annotations_v1");
assert.equal(annotations.blind_pack_sha256, sha256(bytes(join(here, names.blind))));
assert.deepEqual(annotations.annotations.map((row) => Object.keys(row).sort()), Array(72).fill(["annotation", "episode_id"]));
assert.equal(annotations.annotations.every((row) => row.annotation === ""), true);

const sealed = artifact.sealed_reveal;
assert.deepEqual(Object.keys(sealed).sort(), ["encoding", "encoding_is_encryption", "issue_number", "payload_base64", "payload_sha256", "schema_version"]);
assert.equal(sealed.schema_version, "pa_feitian_m6r_sealed_bare_k_reveal_pack_v1");
assert.equal(sealed.encoding, "base64_canonical_json");
assert.equal(sealed.encoding_is_encryption, false);
const revealBytes = Buffer.from(sealed.payload_base64, "base64");
assert.equal(sha256(revealBytes), sealed.payload_sha256);
const reveal = JSON.parse(revealBytes.toString("utf8"));
assert.equal(reveal.schema_version, "pa_feitian_m6r_bare_k_reveal_payload_v1");
assert.equal(reveal.blind_pack_sha256, annotations.blind_pack_sha256);
assert.equal(reveal.episode_count, 72);
assert.equal(reveal.episodes.length, 72);
assert.equal(reveal.annotation_gate.nonempty_annotation_per_episode_required, true);
assert.equal(reveal.episodes.every((episode) => episode.future_bars.length === 20), true);
assert.equal(reveal.episodes.every((episode) => episode.provenance.instrument_family), true);
for (const episode of reveal.episodes) {
  const blindTimes = episode.provenance.blind_bar_timestamps.map((timestamp) => new Date(timestamp));
  const futureTimes = episode.future_bars.map((bar) => new Date(bar.timestamp));
  assert.equal(blindTimes.every((time, index) => index === 0 || blindTimes[index - 1] < time), true);
  assert.equal(futureTimes.every((time, index) => index === 0 || futureTimes[index - 1] < time), true);
  assert.equal(futureTimes.every((time) => blindTimes.at(-1) < time), true);
  for (const bar of episode.future_bars) {
    assert.equal(bar.high_index >= bar.low_index, true);
    assert.equal(bar.high_index >= bar.open_index && bar.high_index >= bar.close_index, true);
    assert.equal(bar.low_index <= bar.open_index && bar.low_index <= bar.close_index, true);
  }
}
for (const family of new Set(reveal.episodes.map((episode) => episode.provenance.instrument_family))) {
  const intervals = reveal.episodes
    .filter((episode) => episode.provenance.instrument_family === family)
    .map((episode) => ({
      start: new Date(episode.provenance.blind_start_timestamp),
      end: new Date(episode.future_bars.at(-1).timestamp),
    }));
  for (let left = 0; left < intervals.length; left += 1) {
    for (let right = left + 1; right < intervals.length; right += 1) {
      assert.equal(
        intervals[left].end < intervals[right].start || intervals[right].end < intervals[left].start,
        true,
        `same-family calendar interval overlap remains for ${family}`,
      );
    }
  }
}

const coverage = artifact.coverage;
assert.equal(coverage.schema_version, "pa_feitian_m6r_bare_k_episode_coverage_v1");
assert.equal(coverage.aggregate.family_count, 9);
assert.equal(coverage.aggregate.exchange_count, 3);
assert.equal(coverage.aggregate.selected_episode_count, 72);
assert.equal(coverage.aggregate.candidate_activity_episode_count, 36);
assert.equal(coverage.aggregate.ordinary_control_episode_count, 36);
assert.equal(coverage.family_coverage.length, 9);
assert.equal(coverage.exchange_coverage.length, 3);
assert.equal(coverage.family_coverage.every((row) => row.selected_episode_count === 8), true);
assert.equal(coverage.family_coverage.every((row) => row.selected_by_sampling_role.candidate_activity === 4), true);
assert.equal(coverage.family_coverage.every((row) => row.selected_by_sampling_role.ordinary_control === 4), true);

const publicText = [
  bytes(contractPath).toString("utf8"),
  ...Object.values(names).map((filename) => bytes(join(here, filename)).toString("utf8")),
  bytes(join(here, "README.md")).toString("utf8"),
].join("\n");
for (const forbidden of ["/home/", "/mnt/", "/tmp/", "\\\\Users\\\\", ".parquet", ".csv", "github_pat_", "ghp_", "sk-", "xoxb-"]) {
  assert.equal(publicText.toLowerCase().includes(forbidden.toLowerCase()), false, `public packet contains ${forbidden}`);
}
assert.equal(/\b(?:SHFE|CZCE|DCE)\.[A-Za-z]+\d/i.test(publicText), false, "public packet contains a raw contract identifier");

const args = process.argv.slice(2);
if (args.length > 0) {
  assert.deepEqual(args.slice(0, 1), ["--data-root"]);
  assert.equal(args.length, 2);
  const temporary = mkdtempSync(join(tmpdir(), "m6r-bare-k-episode-pack-"));
  try {
    const result = spawnSync(
      process.env.PA_FEITIAN_PYTHON || process.env.PYTHON || "python",
      [
        join(repoRoot, "src/scripts/build_pa_feitian_m6r_historical_bare_k_episode_pack.py"),
        "--contract", contractPath,
        "--data-root", args[1],
        "--output-directory", temporary,
        "--workers", "8",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
        env: { ...process.env, PYTHONPATH: join(repoRoot, "src") },
      },
    );
    assert.equal(result.status, 0, `real-root rebuild failed: ${result.stderr || result.stdout}`);
    for (const filename of Object.values(names)) {
      assert.deepEqual(bytes(join(temporary, filename)), bytes(join(here, filename)), `${filename} is not byte-stable`);
    }
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}

console.log(JSON.stringify({ ok: true, episodes: 72, families: 9, exchanges: 3 }));
