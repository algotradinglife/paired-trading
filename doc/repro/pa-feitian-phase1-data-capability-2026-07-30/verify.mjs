#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  mkdtempSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const candidateContractPath = resolve(
  repoRoot,
  "docs/research/pa-feitian-phase1-candidate-interface-audit-contract-v1.json",
);
const inventoryContractPath = resolve(
  repoRoot,
  "docs/research/pa-feitian-phase1-data-capability-contract-v1.json",
);
const candidateAuditPath = resolve(packetDir, "candidate_interface_audit_v1.json");
const inventoryPath = resolve(packetDir, "candidate_capability_inventory_v1.json");
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

function runPython(arguments_) {
  const completed = spawnSync(python, arguments_, {
    cwd: repoRoot,
    env: { ...process.env, PYTHONPATH: resolve(repoRoot, "src") },
    encoding: "utf8",
  });
  assert.equal(completed.status, 0, completed.stderr || completed.stdout);
}

const candidateContract = json(candidateContractPath);
const inventoryContract = json(inventoryContractPath);
const candidateAudit = json(candidateAuditPath);
const inventory = json(inventoryPath);
const expectedFamilies = [
  "SHFE.au",
  "SHFE.ag",
  "CZCE.TA",
  "CZCE.MA",
  "SHFE.cu",
  "DCE.i",
];
const expectedCadences = ["daily", "hour", "min15", "min5"];
const expectedOptionFiles = {
  "SHFE.au": 1768,
  "SHFE.ag": 3170,
  "CZCE.TA": 379,
  "CZCE.MA": 438,
  "SHFE.cu": 1490,
  "DCE.i": 214,
};

assert.equal(
  candidateContract.schema_version,
  "pa_feitian_phase1_candidate_interface_audit_contract_v1",
);
assert.equal(
  candidateAudit.schema_version,
  "pa_feitian_phase1_candidate_interface_audit_v1",
);
assert.equal(
  inventoryContract.schema_version,
  "pa_feitian_phase1_data_capability_contract_v1",
);
assert.equal(
  inventory.schema_version,
  "pa_feitian_phase1_data_capability_inventory_v1",
);
assert.equal(candidateAudit.issue_number, 43);
assert.equal(inventory.issue_number, 43);
assert.equal(candidateAudit.audit_as_of_local_date, "2026-07-30");
assert.equal(inventory.audit_as_of_local_date, "2026-07-30");
assert.deepEqual(
  candidateAudit.decision_surface.map((row) => row.instrument_family),
  expectedFamilies,
);
assert.deepEqual(
  inventory.decision_surface.map((row) => row.instrument_family),
  expectedFamilies,
);
assert.deepEqual(inventory.frozen_experiment.universe, ["SHFE.ag", "SHFE.au"]);
assert.equal(candidateAudit.contract.sha256, digest(bytes(candidateContractPath)));
assert.equal(inventory.contract.sha256, digest(bytes(inventoryContractPath)));
assert.equal(candidateAudit.source.runtime_binding, "QUANT_DATA_ROOT");
assert.equal(candidateAudit.source.access, "read_only");
assert.equal(candidateAudit.source.source_refresh_performed, false);
assert.equal(
  candidateAudit.source.filesystem_timestamps_used_as_freshness,
  false,
);
assert.equal(candidateAudit.source.matched_candidate_files, 31141);
assert.equal(
  inventory.candidate_interface_evidence.sha256,
  digest(bytes(candidateAuditPath)),
);
assert.equal(
  inventory.candidate_interface_evidence.source_inventory_sha256,
  candidateAudit.source.inventory_sha256,
);

for (const family of candidateAudit.decision_surface) {
  assert.deepEqual(
    family.cadences.map((row) => row.cadence),
    expectedCadences,
  );
  for (const cadence of family.cadences) {
    const underlying = cadence.interfaces.underlying;
    const option = cadence.interfaces.option_premium;
    assert.ok(underlying.matched_files > 0, `${family.instrument_family} underlying`);
    assert.equal(
      option.matched_files,
      expectedOptionFiles[family.instrument_family],
      `${family.instrument_family} ${cadence.cadence} option file count`,
    );
    assert.equal(underlying.read_error_files, 0);
    assert.equal(option.read_error_files, 0);
    assert.equal(underlying.timestamp_quality.duplicate_rows, 0);
    assert.equal(option.timestamp_quality.duplicate_rows, 0);
    assert.equal(option.freshness.status, "stale");
    assert.equal(option.liquidity_proxy.minimum_pass_rate, null);
    assert.equal(option.liquidity_proxy.ranking_or_outcomes_used, false);
  }
}

assert.equal(inventory.research_boundary.explicit_candidate_interface_audited, true);
assert.equal(inventory.research_boundary.candidate_interface_access, "read_only");
assert.equal(inventory.research_boundary.source_refresh_performed, false);
assert.equal(inventory.research_boundary.strategy_outcomes_accessed, false);
assert.equal(inventory.decision.status, "data_blocked");
assert.equal(inventory.decision.usable_family_count, 0);
assert.deepEqual(inventory.decision.usable_families, []);
assert.equal(inventory.decision.p1_exp_001_action, "stop_as_data_blocked");
assert.equal(inventory.decision.issue_45_may_start_outcome_work, false);
assert.ok(
  inventory.decision_surface.every(
    (row) => row.usable_for_p1_exp_001 === false && row.fail_closed_reason.length > 0,
  ),
);

const publicBytes = Buffer.concat([
  bytes(candidateAuditPath),
  bytes(inventoryPath),
  bytes(resolve(packetDir, "README.md")),
]);
const publicText = publicBytes.toString("utf8");
const localPathPattern = new RegExp(
  String.raw`\/(?:${["home", "mnt", "Users"].join("|")})\/`,
);
assert.doesNotMatch(publicText, localPathPattern, "public packet local path");
assert.doesNotMatch(publicText, /\.parquet|\.csv/i, "public packet source filename");
assert.doesNotMatch(
  publicText,
  /\b(?:SHFE|CZCE|DCE)\.[A-Za-z]+\d/,
  "public packet raw contract identifier",
);
assert.doesNotMatch(
  publicText,
  /(?:api[_-]?key|access[_-]?token|private[_-]?key|password)\s*[:=]/i,
  "public packet credential",
);

const temporary = mkdtempSync(join(tmpdir(), "pa-feitian-data-capability-"));
try {
  if (process.env.QUANT_DATA_ROOT) {
    const rebuiltCandidate = join(temporary, "candidate_interface_audit_v1.json");
    runPython([
      "src/scripts/build_pa_feitian_candidate_interface_audit.py",
      "--contract",
      candidateContractPath,
      "--data-root",
      process.env.QUANT_DATA_ROOT,
      "--output",
      rebuiltCandidate,
      "--workers",
      process.env.PA_FEITIAN_WORKERS || "8",
    ]);
    assert.deepEqual(bytes(rebuiltCandidate), bytes(candidateAuditPath));
  }

  const rebuiltInventory = join(
    temporary,
    "candidate_capability_inventory_v1.json",
  );
  runPython([
    "src/scripts/build_pa_feitian_data_capability_inventory.py",
    "--contract",
    inventoryContractPath,
    "--repo-root",
    repoRoot,
    "--output",
    rebuiltInventory,
  ]);
  assert.deepEqual(bytes(rebuiltInventory), bytes(inventoryPath));
} finally {
  rmSync(temporary, { recursive: true, force: true });
}

console.log(JSON.stringify({
  ok: true,
  issue: 43,
  status: inventory.decision.status,
  usable_family_count: inventory.decision.usable_family_count,
  matched_candidate_files: candidateAudit.source.matched_candidate_files,
  candidate_audit_sha256: digest(bytes(candidateAuditPath)),
  inventory_sha256: digest(bytes(inventoryPath)),
}));
