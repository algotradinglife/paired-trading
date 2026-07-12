#!/usr/bin/env node

import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../../");
const contractRel = "docs/research/pa-feitian-m6-bare-k-premium-path-protocol-v1.json";
const evidenceRel = "doc/repro/pa-feitian-m6-bare-k-protocol-2026-07-12/bare_k_protocol_evidence_v1.json";
const contractPath = path.join(root, contractRel);
const evidencePath = path.join(root, evidenceRel);
const freezeCommit = "eb29562d9b04bdd512616770dca00cbde5b92dc6";

const readJson = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const sha256 = (p) => `sha256:${crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex")}`;
const git = (...args) => execFileSync("git", args, {
  cwd: root,
  encoding: "utf8",
  stdio: ["ignore", "pipe", "ignore"],
}).trim();

const contract = readJson(contractPath);
const evidence = readJson(evidencePath);

assert.equal(contract.schema_version, "pa_feitian_m6_bare_k_premium_path_protocol_v1");
assert.equal(contract.hermes_task, "t_49902c76");
assert.equal(contract.frozen_before_external_research_or_data_inspection, true);
assert.equal(contract.research_mode, "retrospective_finalized_protocol_only");
assert.equal(sha256(contractPath), "sha256:8934b1c301a9e25adf6e00c9f2328c542e2f02e24efdb8b87d48b3c65f8d6dc8");
assert.equal(evidence.contract.sha256, sha256(contractPath));
assert.equal(evidence.contract.freeze_commit, freezeCommit);
assert.equal(git("rev-parse", freezeCommit), freezeCommit);
assert.doesNotThrow(() => git("cat-file", "-e", `${freezeCommit}:${contractRel}`));
assert.throws(() => git("cat-file", "-e", `${freezeCommit}:${evidenceRel}`));

const expectedInputs = new Map([
  ["public://paired-trading/m6/underlying-signal-corpus-v1", "sha256:cb3407910dd15f4327a2465da3a00d6797f81fd9124066695887ddb53d3bf080"],
  ["public://paired-trading/m6/liquid-premium-eligibility-evidence-v1", "sha256:4ac7519fafe713a6f74e079d80acb7e4c2cce885ae946ac8083df95e0a6e7ab4"],
]);
for (const binding of contract.input_bindings) {
  assert.equal(binding.sha256, expectedInputs.get(binding.alias));
  assert.equal(binding.required_label, "retrospective_finalized");
}
for (const verified of evidence.bound_input_verification) {
  assert.equal(verified.expected_sha256, expectedInputs.get(verified.alias));
  assert.equal(verified.observed_sha256, verified.expected_sha256);
  assert.equal(verified.hash_verified, true);
  assert.equal(verified.label_verified, "retrospective_finalized");
}

assert.equal(contract.alert_and_side_rules.pa_alert_is_not_bare_k_confirmation, true);
assert.equal(contract.alert_and_side_rules.direction_side_mapping.bottom_or_bullish, "C");
assert.equal(contract.alert_and_side_rules.direction_side_mapping.top_or_bearish, "P");
assert.equal(contract.input_boundary.aggregate_eligibility_counts_do_not_prove_unit_membership, true);
assert.equal(contract.rule_recovery_gate.default_state, "blocked_authentic_rule_unrecovered");
assert.equal(evidence.source_research_audit.rule_recovery_state, "blocked_authentic_rule_unrecovered");
assert.equal(evidence.protocol_state_summary.confirmed_bare_k_reachable, false);
assert.equal(contract.guardrails.proxy_or_imputation, false);
assert.equal(contract.guardrails.outcomes_or_performance, false);
assert.equal(contract.output_contract.performance_fields, false);
assert.equal(contract.output_contract.selection_artifact, false);

const cutoff = Date.parse("2025-01-02T07:00:00Z");
const prefix = (rows) => rows.filter((r) => Date.parse(r.ts) <= cutoff);
const original = [{ ts: "2025-01-02T06:55:00Z", close: 10 }];
const appended = [...original, { ts: "2025-01-02T07:05:00Z", close: 999999 }];
assert.deepEqual(prefix(appended), prefix(original), "post-cutoff append changed the consumed prefix");
assert.throws(
  () => {
    for (const row of appended) assert.ok(Date.parse(row.ts) <= cutoff, "post-cutoff row consumed");
  },
  /post-cutoff row consumed/,
);

const classify = ({ explicitAlert, direction, unitMembership, requiredBar, authenticRule, predicatesPass }) => {
  if (!explicitAlert) return "blocked_missing_explicit_pa_alert";
  if (!["bottom_or_bullish", "top_or_bearish"].includes(direction)) return "abstain_direction";
  if (!unitMembership) return "blocked_missing_unit_membership";
  if (!requiredBar) return "abstain_missing_required_bar";
  if (!authenticRule) return "blocked_authentic_rule_unrecovered";
  return predicatesPass ? "confirmed_bare_k" : "alert_only";
};
assert.equal(classify({}), "blocked_missing_explicit_pa_alert");
assert.equal(classify({ explicitAlert: true, direction: "flat" }), "abstain_direction");
assert.equal(classify({ explicitAlert: true, direction: "bottom_or_bullish" }), "blocked_missing_unit_membership");
assert.equal(classify({ explicitAlert: true, direction: "bottom_or_bullish", unitMembership: true }), "abstain_missing_required_bar");
assert.equal(classify({ explicitAlert: true, direction: "bottom_or_bullish", unitMembership: true, requiredBar: true }), "blocked_authentic_rule_unrecovered");

const cadenceRank = new Map([["min5", 0], ["min15", 1]]);
const units = [
  { decision: "2025-01-02T07:00:00Z", product: "ag", alert: "a", month: 2506, side: "C", strike: 8000, cadence: "min15", source: "b" },
  { decision: "2025-01-02T07:00:00Z", product: "ag", alert: "a", month: 2506, side: "C", strike: 8000, cadence: "min5", source: "b" },
  { decision: "2025-01-02T07:00:00Z", product: "ag", alert: "a", month: 2506, side: "C", strike: 7900, cadence: "min5", source: "a" },
];
const order = (a, b) =>
  a.decision.localeCompare(b.decision) || a.product.localeCompare(b.product) || a.alert.localeCompare(b.alert) ||
  a.month - b.month || a.side.localeCompare(b.side) || a.strike - b.strike ||
  cadenceRank.get(a.cadence) - cadenceRank.get(b.cadence) || a.source.localeCompare(b.source);
assert.deepEqual(units.toSorted(order).map((u) => `${u.strike}:${u.cadence}`), ["7900:min5", "8000:min5", "8000:min15"]);

const serialized = fs.readFileSync(evidencePath, "utf8");
assert.doesNotMatch(serialized, /\/(?:home|Users)\//);
assert.doesNotMatch(serialized, /drwho1985/i);
assert.ok(evidence.source_research_audit.sources.every((s) => s.alias.startsWith("public://") && /^sha256:[0-9a-f]{64}$/.test(s.sha256)));
const genericCandleSource = evidence.source_research_audit.sources.find(
  (s) => s.alias === "public://trade-philosopher/prompts/pa/文件16-K线信号识别.txt",
);
assert.ok(genericCandleSource, "generic candlestick source alias must match its actual filename");
assert.equal(genericCandleSource.sha256, "sha256:aa1b0a6dbb894c2dbf20f0e4430807d8e13ccdfed9dd7789a1fe9563ec916a2d");
assert.equal(evidence.guardrails.premium_rows_or_paths_read, false);
assert.equal(evidence.guardrails.performance_result, false);
assert.equal(evidence.guardrails.selection_artifact, false);
assert.equal(evidence.guardrails.proxy_or_imputation, false);

console.log("bare-K protocol verification passed");
