#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  mkdtempSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const contractPath = join(
  repoRoot,
  "docs/research/pa-feitian-m6-native-source-registration-contract-v1.json",
);
const artifactPath = join(here, "native_source_registration_audit_v1.json");

function bytes(path) {
  return readFileSync(path);
}

function sha256(value) {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function parse(path) {
  return JSON.parse(bytes(path).toString("utf8"));
}

const contract = parse(contractPath);
const audit = parse(artifactPath);

assert.equal(
  sha256(bytes(contractPath)),
  "sha256:8c2713ae02710e8dbdeeff04fa4be84b818690b9d881104a23069c218f5b83c1",
);
assert.equal(
  sha256(bytes(artifactPath)),
  "sha256:93f39fe6a7badbed7400dd1719195fd64cd9ed817ba2140aa4ee4b8df1a44fee",
);
assert.equal(audit.contract_sha256, sha256(bytes(contractPath)));
assert.equal(
  contract.dependency.merged_gate_contract_sha256,
  "sha256:ce8508f1cb6f15d5030e6424404f07c7d2e346811ccbc1bad033f63d4bc3d351",
);
assert.equal(
  contract.dependency.approved_native_source_version_manifest_sha256_before_audit,
  null,
);
assert.equal(audit.schema_version, "pa_feitian_m6_native_source_registration_audit_v1");
assert.equal(audit.issue_number, 58);
assert.equal(audit.source.matrix_cell_count, 18);
assert.equal(audit.cells.length, 18);
assert.equal(audit.source.source_file_count, 978);
assert.equal(audit.source.source_row_count, 2702545);
assert.equal(audit.source.source_byte_count, 45966586);
assert.equal(audit.source.captured_once_per_source_file, true);
assert.equal(
  audit.source.complete_private_inventory_sha256,
  "sha256:13e00e03007e47525bdeac9e5fddb81d222375d7921557b9b1569fe2bd17b819",
);
assert.equal(
  audit.source.public_membership_sha256,
  "sha256:2cdcd4e6ef456885d59fd89125099e3f1ceb0c27b82a849db45e298f2b1e310d",
);

const total = (selector) =>
  audit.cells.reduce((sum, cell) => sum + selector(cell), 0);

assert.equal(
  total((cell) => cell.source_to_candidate_accounting.prehistory_rows_excluded),
  154969,
);
assert.equal(
  total(
    (cell) =>
      cell.source_to_candidate_accounting.candidate_rows_at_or_after_history_start,
  ),
  2547576,
);
assert.equal(
  total(
    (cell) =>
      cell.source_to_candidate_accounting
        .intraday_or_normalized_rows_on_authorized_endpoints,
  ),
  2026486,
);
assert.equal(
  total((cell) => cell.source_to_candidate_accounting.unexplained_timestamp_rows),
  521090,
);
assert.equal(total((cell) => cell.quality.ohlc_violation_rows), 169);
assert.equal(
  total(
    (cell) =>
      cell.cadence === "daily"
        ? 0
        : cell.timestamp_semantics.provider_bar_end_semantics_bound_file_count,
  ),
  0,
);

assert.equal(audit.verdict.status, "data_blocked");
assert.deepEqual(audit.verdict.reason_codes, [
  "ohlc_quality_findings_present",
  "provider_bar_end_semantics_unbound",
  "timestamps_outside_frozen_session_end_grid",
]);
assert.deepEqual(audit.verdict.required_next_actions, [
  "repair_or_replace_the_invalid_required_source_cells",
  "revise_and_review_a_lossless_source_specific_timestamp_normalization_contract",
]);
assert.equal(audit.verdict.approved_native_source_version_registered, false);
assert.equal(audit.verdict.contract_updated, false);
assert.equal(audit.verdict.formal_allow_demonstrated, false);
assert.equal(audit.verdict.issue_51_unblocked, false);
assert.equal(
  audit.source_version_candidate.materialized_private_snapshot_cells,
  0,
);
assert.equal(
  audit.source_version_candidate.native_source_version_manifest_sha256,
  null,
);
assert.deepEqual(audit.claim_boundary, {
  execution_authorized: false,
  m7_or_m8_authorized: false,
  option_inputs_accessed: false,
  private_paths_or_rows_published: false,
  source_refreshed_or_mutated: false,
  strategy_events_materialized: false,
  strategy_outcomes_accessed: false,
});

const publicText = `${bytes(contractPath).toString("utf8")}\n${bytes(
  artifactPath,
).toString("utf8")}\n${bytes(join(here, "README.md")).toString("utf8")}`;
for (const forbidden of [
  "/home/",
  "/mnt/",
  "/tmp/",
  "\\Users\\",
  ".parquet",
  ".csv",
  "github_pat_",
  "ghp_",
  "sk-",
  "xoxb-",
]) {
  assert.equal(
    publicText.toLowerCase().includes(forbidden.toLowerCase()),
    false,
    `public packet contains forbidden token ${forbidden}`,
  );
}
assert.equal(
  /\b(?:SHFE|CZCE|DCE)\.[A-Za-z]+\d/i.test(publicText),
  false,
  "public packet contains a raw contract identifier",
);

const args = process.argv.slice(2);
if (args.length > 0) {
  assert.deepEqual(args.slice(0, 1), ["--data-root"]);
  assert.equal(args.length, 2);
  const temporary = mkdtempSync(join(tmpdir(), "p1-exp-002-source-audit-"));
  const rebuilt = join(temporary, "audit.json");
  try {
    const result = spawnSync(
      process.env.PYTHON || "python",
      [
        join(
          repoRoot,
          "src/scripts/build_pa_feitian_native_source_registration.py",
        ),
        "--contract",
        contractPath,
        "--data-root",
        args[1],
        "--output",
        rebuilt,
        "--workers",
        "8",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );
    assert.equal(
      result.status,
      0,
      `real-root rebuild failed: ${result.stderr || result.stdout}`,
    );
    assert.deepEqual(bytes(rebuilt), bytes(artifactPath));
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}

console.log(
  JSON.stringify({
    ok: true,
    matrix_cells: audit.cells.length,
    source_files: audit.source.source_file_count,
    source_rows: audit.source.source_row_count,
    verdict: audit.verdict.status,
  }),
);
