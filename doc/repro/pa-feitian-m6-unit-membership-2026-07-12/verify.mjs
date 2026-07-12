#!/usr/bin/env node

import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../..");
const contractPath = path.join(
  repo,
  "docs/research/pa-feitian-m6-liquid-premium-membership-contract-v1.json",
);
const eligibilityContractPath = path.join(
  repo,
  "docs/research/pa-feitian-m6-liquid-premium-eligibility-contract-v1.json",
);
const eligibilityEvidencePath = path.join(
  repo,
  "doc/repro/pa-feitian-m6-liquid-premium-2026-07-12/liquid_premium_evidence_v1.json",
);
const artifactPath = path.join(here, "liquid_premium_membership_v1.json");

function readJson(filename) {
  return JSON.parse(fs.readFileSync(filename, "utf8"));
}

function sha256(filename) {
  return `sha256:${crypto.createHash("sha256").update(fs.readFileSync(filename)).digest("hex")}`;
}

function decimalParts(value) {
  const [integer, fraction = ""] = value.split(".");
  return [BigInt(integer + fraction), BigInt(10) ** BigInt(fraction.length)];
}

function compareDecimal(left, right) {
  const [ln, ld] = decimalParts(left);
  const [rn, rd] = decimalParts(right);
  const difference = ln * rd - rn * ld;
  return difference < 0n ? -1 : difference > 0n ? 1 : 0;
}

function compareText(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function compareMembers(left, right) {
  return (
    compareText(left.local_date, right.local_date) ||
    compareText(left.product, right.product) ||
    Number(left.underlying_month) - Number(right.underlying_month) ||
    (left.option_type === "C" ? 0 : 1) - (right.option_type === "C" ? 0 : 1) ||
    compareDecimal(left.strike, right.strike) ||
    (left.cadence === "min5" ? 0 : 1) - (right.cadence === "min5" ? 0 : 1) ||
    compareText(left.source_alias, right.source_alias)
  );
}

const contract = readJson(contractPath);
const artifact = readJson(artifactPath);
assert.equal(contract.schema_version, "pa_feitian_m6_liquid_premium_membership_contract_v1");
assert.equal(contract.hermes_task, "t_02ba3dea");
assert.equal(contract.frozen_before_external_option_data_inspection, true);
assert.equal(contract.frozen_boundary.finalized_vintage, true);
assert.equal(contract.frozen_boundary.historical_bid_ask_required, false);
assert.equal(contract.frozen_boundary.contract_delta_required, false);
assert.equal(contract.frozen_boundary.exact_expiry_or_dte_required, false);
assert.equal(contract.membership_output.premium_paths, false);
assert.equal(contract.membership_output.performance_fields, false);
assert.equal(contract.data_access_policy.recursive_discovery, false);
assert.equal(contract.coverage_and_missing_semantics.partial_output, false);

assert.equal(contract.bound_inputs[0].sha256, sha256(eligibilityContractPath));
assert.equal(contract.bound_inputs[1].sha256, sha256(eligibilityEvidencePath));
assert.equal(artifact.contract.sha256, sha256(contractPath));
assert.equal(artifact.contract.freeze_commit, "e81d283fac967db06932cd2bc3bdf5eeab8e8ef4");
assert.equal(artifact.contract.frozen_before_external_option_data_inspection, true);
assert.deepEqual(artifact.bound_inputs, contract.bound_inputs);
assert.equal(artifact.schema_version, "pa_feitian_m6_liquid_premium_membership_v1");
assert.equal(artifact.hermes_task, "t_02ba3dea");
assert.equal(artifact.label, "retrospective_finalized");
assert.equal(artifact.decision_cutoff.inclusive_local_time, "15:00:00");
assert.equal(artifact.decision_cutoff.post_cutoff_rows_excluded_before_eligibility, true);

const memberFields = [
  "product",
  "local_date",
  "underlying_month",
  "option_type",
  "strike",
  "cadence",
  "source_alias",
];
assert.deepEqual(artifact.member_fields, memberFields);
assert.equal(artifact.members.length, 47079);
const expectedCounts = new Map(
  contract.data_access_policy.expected_inventories.map((row) => [
    `${row.product}/${row.cadence}`,
    row.expected_eligible_units,
  ]),
);
for (const row of artifact.coverage) {
  assert.equal(row.inventory_state, "verified_complete");
  assert.equal(row.eligible_units, expectedCounts.get(`${row.product}/${row.cadence}`));
  assert.equal(row.eligible_units + row.ineligible_units, row.contract_date_units);
  assert.match(row.source_content_manifest_sha256, /^sha256:[0-9a-f]{64}$/);
}

const identities = new Set();
for (let index = 0; index < artifact.members.length; index += 1) {
  const member = artifact.members[index];
  assert.deepEqual(Object.keys(member).sort(), [...memberFields].sort());
  assert.match(member.product, /^(au|ag)$/);
  assert.match(member.local_date, /^20[0-9]{2}-[0-9]{2}-[0-9]{2}$/);
  assert.match(member.underlying_month, /^[0-9]{4}$/);
  assert.match(member.option_type, /^(C|P)$/);
  assert.match(member.strike, /^[0-9]+(?:\.[0-9]+)?$/);
  assert.match(member.cadence, /^(min5|min15)$/);
  assert.match(member.source_alias, /^external:\/\/quant-data\/(min5|min15)\/SHFE\.(au|ag)-options$/);
  const identity = memberFields.map((field) => member[field]).join("\u0000");
  assert.equal(identities.has(identity), false, `duplicate member at ${index}`);
  identities.add(identity);
  if (index > 0) assert.equal(compareMembers(artifact.members[index - 1], member) < 0, true);
}

const encoded = JSON.stringify(artifact);
for (const forbidden of [
  "/home/",
  "/mnt/",
  "\\Users\\",
  "AKIA",
  "selected_contract",
  '"open":',
  '"high":',
  '"low":',
  '"close":',
  '"price":',
  '"pnl":',
  '"win_rate":',
]) {
  assert.equal(encoded.includes(forbidden), false, `forbidden public content: ${forbidden}`);
}

if (process.env.PA_FEITIAN_REGENERATE === "1") {
  for (const name of ["QUANT_DATA_ROOT", "PA_FEITIAN_PYTHON"]) {
    assert.ok(process.env[name], `${name} is required`);
  }
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "paft-unit-membership-"));
  const regenerated = path.join(temporary, "membership.json");
  const result = spawnSync(
    process.env.PA_FEITIAN_PYTHON,
    [
      path.join(repo, "src/scripts/build_pa_feitian_liquid_premium_membership.py"),
      "--contract",
      contractPath,
      "--eligibility-contract",
      eligibilityContractPath,
      "--data-root",
      process.env.QUANT_DATA_ROOT,
      "--repo-root",
      repo,
      "--output",
      regenerated,
      "--workers",
      process.env.PA_FEITIAN_WORKERS || "8",
    ],
    {
      cwd: repo,
      env: { ...process.env, PYTHONPATH: path.join(repo, "src") },
      encoding: "utf8",
    },
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.deepEqual(fs.readFileSync(regenerated), fs.readFileSync(artifactPath));
  fs.rmSync(temporary, { recursive: true, force: true });
}

console.log("verified PA/Feitian M6 liquid-premium unit membership boundary");
