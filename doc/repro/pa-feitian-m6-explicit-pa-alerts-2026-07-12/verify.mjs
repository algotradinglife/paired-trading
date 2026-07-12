#!/usr/bin/env node

import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../../");
const contractRel = "docs/research/pa-feitian-m6-explicit-pa-alert-materialization-contract-v1.json";
const artifactRel = "doc/repro/pa-feitian-m6-explicit-pa-alerts-2026-07-12/explicit_pa_alert_corpus_v1.json";
const contractPath = path.join(root, contractRel);
const artifactPath = path.join(root, artifactRel);
const freezeCommit = "a63cdec3ec82b1b2a475ce561626310ca6c1a1cc";

const readJson = (value) => JSON.parse(fs.readFileSync(value, "utf8"));
const sha256 = (value) => `sha256:${crypto.createHash("sha256").update(fs.readFileSync(value)).digest("hex")}`;
const git = (...args) => execFileSync("git", args, {
  cwd: root,
  encoding: "utf8",
  stdio: ["ignore", "pipe", "ignore"],
}).trim();

const contract = readJson(contractPath);
const artifact = readJson(artifactPath);

assert.equal(contract.schema_version, "pa_feitian_m6_explicit_pa_alert_materialization_contract_v1");
assert.equal(contract.hermes_task, "t_1bf2484e");
assert.equal(contract.frozen_before_historical_scan, true);
assert.equal(contract.research_mode, "retrospective_finalized");
assert.equal(sha256(contractPath), "sha256:e4ba463a12d96a2e23843d7d8e44be35a7758a3f034c353ea72495d8c8a6382e");
assert.equal(git("rev-parse", freezeCommit), freezeCommit);
assert.doesNotThrow(() => git("cat-file", "-e", `${freezeCommit}:${contractRel}`));
assert.throws(() => git("cat-file", "-e", `${freezeCommit}:${artifactRel}`));

assert.equal(sha256(path.join(root, contract.input_binding.path)), contract.input_binding.sha256);
assert.equal(
  sha256(path.join(root, contract.input_binding.contract.path)),
  contract.input_binding.contract.sha256,
);
assert.equal(
  git("rev-parse", contract.authoritative_strategy.revision),
  contract.authoritative_strategy.revision,
);
for (const source of contract.authoritative_strategy.source_files) {
  assert.equal(sha256(path.join(root, source.path)), source.sha256);
  assert.equal(git("hash-object", source.path), source.git_blob);
  assert.equal(
    git("rev-parse", `${contract.authoritative_strategy.revision}:${source.path}`),
    source.git_blob,
  );
}

assert.equal(artifact.schema_version, "pa_feitian_m6_explicit_pa_alert_corpus_v1");
assert.equal(artifact.hermes_task, "t_1bf2484e");
assert.equal(artifact.research_mode, "retrospective_finalized");
assert.equal(artifact.contract.sha256, sha256(contractPath));
assert.equal(artifact.input.sha256, contract.input_binding.sha256);
assert.equal(sha256(artifactPath), "sha256:f993eb8ff11afcd1edd673f4c21f5a4334dcdb086c53410c7eef62a84633cbe2");
assert.equal(artifact.coverage.input_records, 670);
assert.deepEqual(artifact.coverage.input_records_by_product, { ag: 337, au: 333 });
assert.equal(artifact.coverage.alerts, 11);
assert.deepEqual(artifact.coverage.alerts_by_product, { ag: 4, au: 7 });
assert.equal(artifact.alerts.length, 11);

const alertFields = [...contract.output_contract.alert_fields].sort();
const identities = new Set();
let previous = null;
for (const alert of artifact.alerts) {
  assert.deepEqual(Object.keys(alert).sort(), alertFields);
  assert.equal(alert.strategy_rule_id, "pa_h2_bottom_daily_au_ag_v1");
  assert.ok(["au", "ag"].includes(alert.product));
  assert.equal(alert.cadence, "D");
  assert.equal(alert.pattern, "h2_bottom");
  assert.equal(alert.pa_direction, "bottom");
  assert.equal(alert.strategy_direction, "long");
  assert.ok(Date.parse(alert.bar_timestamp_utc) <= Date.parse(alert.decision_ts_utc));
  assert.ok(!identities.has(alert.alert_id));
  identities.add(alert.alert_id);
  const order = `${alert.decision_ts_utc}\0${alert.product}\0${alert.alert_id}`;
  if (previous !== null) assert.ok(previous <= order);
  previous = order;
}

assert.equal(contract.guardrails.diagnostic_inference, false);
assert.equal(contract.guardrails.option_or_premium_path_reading, false);
assert.equal(contract.guardrails.feitian_or_dd_line_confirmation, false);
assert.equal(contract.guardrails.outcomes_or_performance, false);
assert.equal(contract.guardrails.m7, false);
assert.equal(contract.guardrails.m8, false);
assert.equal(contract.guardrails.execution, false);
assert.equal(contract.output_contract.raw_market_rows, false);
assert.equal(contract.output_contract.diagnostic_fields, false);
assert.equal(contract.output_contract.performance_fields, false);

const serialized = fs.readFileSync(artifactPath, "utf8");
assert.doesNotMatch(serialized, /\/(?:home|Users)\//);
assert.doesNotMatch(serialized, /(?:api[_-]?key|access[_-]?token|secret)/i);

const python = process.env.PA_FEITIAN_PYTHON ?? "python3";
execFileSync(
  python,
  [
    "src/scripts/verify_pa_feitian_explicit_pa_alerts.py",
    "--repo-root", ".",
    "--contract", contractRel,
    "--artifact", artifactRel,
  ],
  {
    cwd: root,
    env: { ...process.env, PYTHONPATH: "src" },
    stdio: "inherit",
  },
);

console.log("explicit PA alert verification passed");
