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
  "docs/research/pa-feitian-m6-liquid-premium-eligibility-contract-v1.json",
);
const evidencePath = path.join(here, "liquid_premium_evidence_v1.json");

function readJson(filename) {
  return JSON.parse(fs.readFileSync(filename, "utf8"));
}

function sha256(filename) {
  return `sha256:${crypto.createHash("sha256").update(fs.readFileSync(filename)).digest("hex")}`;
}

function walkKeys(value, output = []) {
  if (Array.isArray(value)) {
    for (const child of value) walkKeys(child, output);
  } else if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      output.push(key.toLowerCase());
      walkKeys(child, output);
    }
  }
  return output;
}

const contract = readJson(contractPath);
const evidence = readJson(evidencePath);

assert.equal(contract.hermes_task, "t_3bf64f0c");
assert.equal(contract.frozen_before_external_data_inspection, true);
assert.equal(contract.boundary_correction.historical_bid_ask_required, false);
assert.equal(contract.boundary_correction.contract_delta_required, false);
assert.equal(contract.guardrails.strategy_performance_evaluation, false);
assert.equal(contract.guardrails.m7, false);

assert.equal(evidence.schema_version, "pa_feitian_m6_liquid_premium_evidence_v1");
assert.equal(evidence.hermes_task, "t_3bf64f0c");
assert.equal(evidence.label, "retrospective_finalized");
assert.equal(evidence.contract.sha256, sha256(contractPath));
assert.deepEqual(
  evidence.coverage.map(({ product, cadence }) => [product, cadence]),
  [
    ["au", "min5"],
    ["ag", "min5"],
    ["au", "min15"],
    ["ag", "min15"],
  ],
);
for (const row of evidence.coverage) {
  assert.equal(row.eligible_units + row.ineligible_units, row.contract_date_units);
  assert.equal(row.source_files > 0, true);
  assert.equal(row.source_rows_at_or_before_cutoff > 0, true);
}
assert.equal(evidence.classification.thresholds_frozen_before_source_inspection, true);
assert.equal(evidence.classification.thresholds_chosen_from_outcomes, false);
assert.equal(evidence.classification.quote_or_greeks_dependency, "none");
assert.equal(evidence.promotion.exploratory_liquid_premium_ohlc_lane, true);
for (const [name, promoted] of Object.entries(evidence.promotion)) {
  if (name !== "exploratory_liquid_premium_ohlc_lane" && name !== "next_gate") {
    assert.equal(promoted, false, `${name} must remain blocked`);
  }
}

const forbiddenKeys = new Set([
  "candidate",
  "delta",
  "entry",
  "exit",
  "fill",
  "gamma",
  "pnl",
  "profit",
  "recommendation",
  "selected_contract",
  "selection",
  "slippage",
  "spread",
  "theta",
  "trade",
  "vega",
  "win_rate",
]);
assert.deepEqual([...new Set(walkKeys(evidence).filter((key) => forbiddenKeys.has(key)))], []);
const encoded = JSON.stringify(evidence);
assert.equal(encoded.includes("/mnt/"), false);
assert.equal(encoded.includes("\\Users\\"), false);
assert.equal(encoded.includes(os.homedir()), false);

if (process.env.PA_FEITIAN_REGENERATE === "1") {
  const required = [
    "QUANT_DATA_ROOT",
    "QUANT_REPO",
    "PA_FEITIAN_PYTHON",
  ];
  for (const name of required) assert.ok(process.env[name], `${name} is required`);
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "paft-liquid-premium-"));
  const regenerated = path.join(temporary, "evidence.json");
  const result = spawnSync(
    process.env.PA_FEITIAN_PYTHON,
    [
      path.join(repo, "src/scripts/build_pa_feitian_liquid_premium_evidence.py"),
      "--contract",
      contractPath,
      "--data-root",
      process.env.QUANT_DATA_ROOT,
      "--quant-repo",
      process.env.QUANT_REPO,
      "--paired-repo",
      repo,
      "--output",
      regenerated,
    ],
    {
      cwd: repo,
      env: { ...process.env, PYTHONPATH: path.join(repo, "src") },
      encoding: "utf8",
    },
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.deepEqual(fs.readFileSync(regenerated), fs.readFileSync(evidencePath));
  fs.rmSync(temporary, { recursive: true, force: true });
}

console.log("verified PA/Feitian M6 liquid-premium evidence boundary");
