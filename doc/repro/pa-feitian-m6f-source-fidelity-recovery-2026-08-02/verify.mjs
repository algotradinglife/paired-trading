#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const evidenceHeadMode = process.argv.includes("--evidence-head");
const negativeMode = process.argv.includes("--negative");

const names = {
  construct: "construct_dag_v1.json",
  contamination: "contamination_ledger_v1.jsonl",
  ledger: "source_fidelity_ledger_v1.json",
  manifest: "artifact_manifest_v1.json",
  measurement: "measurement_readiness_v1.json",
  readme: "README.md",
  receipt: "independent-evidence-validation-receipt.md",
  reserve: "confirmation_reserve_contract_v1.json",
  schema: "schema_v1.json",
  verify: "verify.mjs"
};

const manifestScope = [
  names.construct,
  names.contamination,
  names.measurement,
  names.reserve,
  names.schema,
  names.ledger,
  names.verify
].sort();

function bytes(name) {
  return readFileSync(join(here, name));
}

function text(name) {
  return bytes(name).toString("utf8");
}

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, sortKeys(value[key])])
    );
  }
  return value;
}

function canonicalCompact(value) {
  return JSON.stringify(sortKeys(value));
}

function parseCanonicalJson(name) {
  const raw = text(name);
  assert.ok(!raw.startsWith("\ufeff"), `${name}: UTF-8 BOM is forbidden`);
  assert.ok(!raw.includes("\r"), `${name}: CR is forbidden`);
  const value = JSON.parse(raw);
  assert.equal(raw, `${JSON.stringify(sortKeys(value), null, 2)}\n`, `${name}: noncanonical JSON bytes`);
  return value;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

const schema = parseCanonicalJson(names.schema);
assert.equal(schema.$schema, "https://json-schema.org/draft/2020-12/schema");
assert.equal(schema.$id, "https://github.com/algotradinglife/paired-trading/schema/pa-feitian-m6f-source-fidelity-recovery-v1.json");

function matchesType(value, type) {
  if (type === "null") return value === null;
  if (type === "array") return Array.isArray(value);
  if (type === "object") return value !== null && typeof value === "object" && !Array.isArray(value);
  if (type === "integer") return Number.isInteger(value);
  return typeof value === type;
}

function resolveRef(ref) {
  assert.match(ref, /^#\/\$defs\/[A-Za-z0-9_]+$/, `unsupported schema ref ${ref}`);
  const key = ref.split("/").at(-1);
  assert.ok(schema.$defs[key], `missing schema definition ${key}`);
  return schema.$defs[key];
}

function validate(value, rule, location = "$") {
  if (rule.$ref) return validate(value, resolveRef(rule.$ref), location);
  if (Object.hasOwn(rule, "const")) assert.deepEqual(value, rule.const, `${location}: const`);
  if (rule.enum) assert.ok(rule.enum.includes(value), `${location}: enum`);
  if (rule.type) {
    const types = Array.isArray(rule.type) ? rule.type : [rule.type];
    assert.ok(types.some((type) => matchesType(value, type)), `${location}: type ${types.join("|")}`);
  }
  if (typeof value === "string" && rule.pattern) {
    assert.match(value, new RegExp(rule.pattern), `${location}: pattern`);
  }
  if (typeof value === "number" && rule.minimum !== undefined) {
    assert.ok(value >= rule.minimum, `${location}: minimum`);
  }
  if (Array.isArray(value)) {
    if (rule.minItems !== undefined) assert.ok(value.length >= rule.minItems, `${location}: minItems`);
    if (rule.maxItems !== undefined) assert.ok(value.length <= rule.maxItems, `${location}: maxItems`);
    if (rule.items) value.forEach((item, index) => validate(item, rule.items, `${location}[${index}]`));
  }
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    for (const required of rule.required ?? []) {
      assert.ok(Object.hasOwn(value, required), `${location}: missing ${required}`);
    }
    if (rule.additionalProperties === false) {
      const allowed = new Set(Object.keys(rule.properties ?? {}));
      for (const key of Object.keys(value)) assert.ok(allowed.has(key), `${location}: extra ${key}`);
    }
    for (const [key, child] of Object.entries(rule.properties ?? {})) {
      if (Object.hasOwn(value, key)) validate(value[key], child, `${location}.${key}`);
    }
  }
}

const ledger = parseCanonicalJson(names.ledger);
const construct = parseCanonicalJson(names.construct);
const measurement = parseCanonicalJson(names.measurement);
const reserve = parseCanonicalJson(names.reserve);
const manifest = parseCanonicalJson(names.manifest);

validate(ledger, schema.$defs.source_fidelity_ledger, "ledger");
validate(construct, schema.$defs.construct_dag, "construct");
validate(measurement, schema.$defs.measurement_readiness, "measurement");
validate(reserve, schema.$defs.confirmation_reserve_contract, "reserve");
validate(manifest, schema.$defs.artifact_manifest, "manifest");

const expectedLedgerIds = [
  "SF-01-UNDERLYING-DIRECTION",
  "SF-02-OPTION-CONTRACT",
  "SF-03-DAILY-CHART",
  "SF-04-DD-LOW-LINE",
  "SF-05-DESCENDING-HIGH-LINE",
  "SF-06-ONE-B-TWO-B",
  "SF-07-HOLISTIC-QUALITY",
  "SF-08-ENTRY-ORDERING",
  "SF-09-STRUCTURAL-INVALIDATION",
  "SF-10-PREMIUM-MANAGEMENT"
];
assert.deepEqual(ledger.nodes.map((node) => node.node_id), expectedLedgerIds, "exact ledger node order/set");
assert.equal(new Set(expectedLedgerIds).size, 10);
assert.ok(ledger.nodes.every((node) => node.critical_to_construct), "all ten nodes are critical");
assert.ok(ledger.nodes.every((node) => node.abstention_rule.length > 0), "every node fails closed");
assert.ok(ledger.nodes.every((node) => node.evidence.file_sha256 === "2ea78aa6e6addc24bbb132dc2d104d182ce24060e6a8be72ad120063fa4ed263"));
assert.ok(ledger.nodes.every((node) => node.evidence.repository_revision === "715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a"));
assert.ok(ledger.nodes.every((node) => node.evidence.locator.startsWith("trade-philosopher:doc/")));
for (const node of ledger.nodes) {
  if (node.status === "source_authorized") {
    assert.equal(node.evidence.authorization_class, "explicit_source_authorization", `${node.node_id}: authorization class`);
  }
  assert.notEqual(node.status, "method_constraint", `${node.node_id}: critical method proxy prohibited`);
}

const ledgerIds = new Set(expectedLedgerIds);
const dagIds = new Set(construct.nodes.map((node) => node.node_id));
const boundLedgerIds = new Set(construct.nodes.map((node) => node.ledger_node_id));
assert.deepEqual(construct.plane_order, ["event", "perception", "decision", "outcome"]);
assert.deepEqual(new Set(construct.nodes.map((node) => node.plane)), new Set(construct.plane_order), "four planes are distinct and present");
assert.deepEqual(boundLedgerIds, ledgerIds, "DAG binds every ledger node");
assert.ok(construct.nodes.every((node) => ["deterministic_rule", "source_authorized_protocol", "fail_closed"].includes(node.readiness)));
for (const edge of construct.edges) {
  assert.ok(dagIds.has(edge.from), `unknown edge source ${edge.from}`);
  assert.ok(dagIds.has(edge.to), `unknown edge target ${edge.to}`);
}
const indegree = new Map([...dagIds].map((id) => [id, 0]));
for (const edge of construct.edges) indegree.set(edge.to, indegree.get(edge.to) + 1);
const queue = [...indegree].filter(([, degree]) => degree === 0).map(([id]) => id);
let visited = 0;
while (queue.length) {
  const id = queue.shift();
  visited += 1;
  for (const edge of construct.edges.filter((candidate) => candidate.from === id)) {
    indegree.set(edge.to, indegree.get(edge.to) - 1);
    if (indegree.get(edge.to) === 0) queue.push(edge.to);
  }
}
assert.equal(visited, dagIds.size, "construct graph must be acyclic");

assert.deepEqual(measurement.fields.map((field) => field.node_id), expectedLedgerIds, "measurement node order/set");
assert.equal(new Set(measurement.fields.map((field) => field.field_id)).size, expectedLedgerIds.length);
assert.ok(measurement.fields.every((field) => field.required_fields.length > 0));
for (const field of measurement.fields) {
  for (const key of [
    "available_at_and_decision_cutoff",
    "bar_open_and_end_semantics",
    "exchange_timezone_and_session",
    "expiry_and_roll_mapping",
    "fail_closed_behavior",
    "missing_and_rejected_row_accounting",
    "option_lifecycle_and_selection_state",
    "premium_price_basis",
    "provenance_and_replay_binding",
    "source_class"
  ]) assert.ok(field[key].length > 0, `${field.field_id}: ${key}`);
}

const contaminationRaw = text(names.contamination);
assert.ok(!contaminationRaw.startsWith("\ufeff"));
assert.ok(!contaminationRaw.includes("\r"));
assert.ok(contaminationRaw.endsWith("\n"));
const contamination = contaminationRaw.trimEnd().split("\n").map((line, index) => {
  const entry = JSON.parse(line);
  assert.equal(line, canonicalCompact(entry), `contamination line ${index + 1}: canonical JSONL`);
  validate(entry, schema.$defs.contamination_entry, `contamination[${index}]`);
  return entry;
});
assert.equal(contamination.length, 8);
let priorHash = "0".repeat(64);
let priorTimestamp = "";
for (const [index, entry] of contamination.entries()) {
  assert.equal(entry.sequence, index + 1, `${entry.entry_id}: sequence`);
  assert.equal(entry.entry_id, `CONTAM-${String(index + 1).padStart(4, "0")}`);
  assert.equal(entry.prior_entry_sha256, priorHash, `${entry.entry_id}: prior hash`);
  const unhashed = clone(entry);
  delete unhashed.entry_sha256;
  assert.equal(entry.entry_sha256, digest(canonicalCompact(unhashed)), `${entry.entry_id}: entry hash`);
  assert.ok(entry.timestamp >= priorTimestamp, `${entry.entry_id}: monotonic timestamp`);
  priorHash = entry.entry_sha256;
  priorTimestamp = entry.timestamp;
}
const contaminationIds = new Set(contamination.map((entry) => entry.entry_id));
for (const node of ledger.nodes) {
  assert.ok(node.contamination_entry_ids.length > 0, `${node.node_id}: contamination binding`);
  for (const id of node.contamination_entry_ids) assert.ok(contaminationIds.has(id), `${node.node_id}: unknown contamination id ${id}`);
}
const m6rEntry = contamination.find((entry) => entry.entry_id === "CONTAM-0003");
assert.match(m6rEntry.evidence_id, /72-episodes-no_candidate/);
assert.match(m6rEntry.permitted_use, /not_inspected_or_used_for_confirmation/);

assert.equal(reserve.eligibility_rule_sha256, digest(reserve.eligibility_rule));
assert.equal(reserve.exclusion_set_sha256, digest(reserve.exclusion_rule));
assert.match(reserve.exclusion_rule, /all 72 M6R episode IDs/);
assert.equal(reserve.access_log_locator, names.contamination);
if (reserve.status === "sealed") {
  assert.equal(reserve.mechanically_enforceable, true);
  assert.match(reserve.sealed_at, /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/);
} else {
  assert.equal(reserve.mechanically_enforceable, false);
  assert.equal(reserve.sealed_at, null);
  assert.equal(reserve.terminal_effect, "readiness_cannot_pass");
}

function recomputeTerminal(currentLedger, currentMeasurement, currentReserve) {
  if (currentMeasurement.open_external_dependency !== null) return "source_fidelity_recovery_blocked";
  const unresolvedCritical = currentLedger.nodes.some(
    (node) => node.critical_to_construct && !["source_pinned", "source_authorized"].includes(node.status)
  );
  const incompleteCriticalProtocol = currentLedger.nodes.some((node) => {
    if (!node.critical_to_construct) return false;
    const bindings = construct.nodes.filter((candidate) => candidate.ledger_node_id === node.node_id);
    return !bindings.some((binding) => ["deterministic_rule", "source_authorized_protocol"].includes(binding.readiness));
  });
  if (unresolvedCritical || incompleteCriticalProtocol) return "source_fidelity_unrecoverable_construct";
  if (currentMeasurement.measurement_result !== "pass") return "source_fidelity_measurement_failure";
  if (!currentReserve.mechanically_enforceable || currentReserve.status !== "sealed") return "source_fidelity_measurement_failure";
  return "source_fidelity_ready_for_preregistration_design";
}

const recomputedTerminal = recomputeTerminal(ledger, measurement, reserve);
assert.equal(recomputedTerminal, "source_fidelity_unrecoverable_construct");
assert.equal(ledger.terminal_result, recomputedTerminal);
assert.equal(construct.terminal_result, recomputedTerminal);
assert.equal(measurement.terminal_result, recomputedTerminal);

assert.deepEqual(manifest.entries.map((entry) => entry.path).sort(), manifestScope);
assert.deepEqual(manifest.hash_scope_exclusions, [names.manifest, names.readme, names.receipt]);
for (const entry of manifest.entries) {
  const raw = bytes(entry.path);
  assert.equal(entry.byte_length, raw.byteLength, `${entry.path}: byte length`);
  assert.equal(entry.sha256, digest(raw), `${entry.path}: raw-byte hash`);
}
const readme = text(names.readme);
const manifestBinding = readme.match(/Manifest SHA-256: `([0-9a-f]{64})`/);
assert.ok(manifestBinding, "README manifest binding");
assert.equal(manifestBinding[1], digest(bytes(names.manifest)), "README manifest hash");
assert.match(readme, /source_fidelity_unrecoverable_construct/);
assert.match(readme, /PI may not open\s+a (?:separate )?preregistration-design Issue/);

const actualFiles = readdirSync(here).sort();
const evidenceHeadFiles = Object.values(names).filter((name) => name !== names.receipt).sort();
const finalFiles = Object.values(names).sort();
assert.deepEqual(actualFiles, evidenceHeadMode ? evidenceHeadFiles : finalFiles, "exact package membership");
if (!evidenceHeadMode) {
  assert.ok(existsSync(join(here, names.receipt)), "independent receipt required at final head");
  const receipt = text(names.receipt);
  assert.match(receipt, /\[ENGINEERING VALIDATION\]\[PASS\]/);
  assert.match(receipt, /Exact HEAD: [0-9a-f]{40}/);
  assert.match(receipt, /Issue: 77/);
  assert.match(receipt, /Mutations: none/);
  assert.match(receipt, /Findings: none/);
}

const publicText = actualFiles.map((name) => text(name)).join("\n");
for (const [label, pattern] of [
  ["absolute local path", /\/(?:home|Users)\/[A-Za-z0-9._-]+\//],
  ["private key", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
  ["GitHub token", /gh[oprsu]_[A-Za-z0-9_]{20,}/],
  ["OpenAI token", /sk-[A-Za-z0-9]{20,}/],
  ["credential assignment", /(?:password|secret|token)\s*[:=]\s*["'][^"']{8,}["']/i],
  ["licensed row payload", /"(?:open|high|low|close|volume)"\s*:\s*-?[0-9]+(?:\.[0-9]+)?/]
]) assert.doesNotMatch(publicText, pattern, `public-safe scan: ${label}`);
for (const prohibitedClaim of [
  ["authentic", "feitian", "supported"].join("_"),
  ["strategy", "validated"].join("_"),
  ["profitability", "supported"].join("_"),
  ["m7", "authorized"].join("_"),
  ["experiment", "authorized"].join("_"),
  ["trader", "gt", "confirmed"].join("_")
]) assert.ok(!publicText.toLowerCase().includes(prohibitedClaim), `forbidden claim ${prohibitedClaim}`);

if (negativeMode) {
  assert.throws(() => {
    const mutated = clone(ledger);
    mutated.unexpected = true;
    validate(mutated, schema.$defs.source_fidelity_ledger, "negative.extra_key");
  }, /extra unexpected/);
  assert.throws(() => {
    const mutated = clone(ledger.nodes[0]);
    mutated.status = "source_authorized";
    assert.equal(mutated.evidence.authorization_class, "explicit_source_authorization");
  });
  assert.throws(() => {
    const mutated = clone(contamination[3]);
    mutated.permitted_use = "mutated";
    const unhashed = clone(mutated);
    delete unhashed.entry_sha256;
    assert.equal(mutated.entry_sha256, digest(canonicalCompact(unhashed)));
  });
  assert.throws(() => {
    const mutated = clone(construct);
    mutated.nodes = mutated.nodes.filter((node) => node.plane !== "outcome");
    assert.deepEqual(new Set(mutated.nodes.map((node) => node.plane)), new Set(mutated.plane_order));
  });
  assert.throws(() => {
    const mutated = clone(reserve);
    mutated.status = "sealed";
    assert.equal(mutated.mechanically_enforceable, true);
  });
  assert.throws(() => {
    assert.equal("source_fidelity_ready_for_preregistration_design", recomputedTerminal);
  });
  console.log("negative mutations: PASS (6/6 rejected)");
}

console.log(`M6F source-fidelity verification: PASS (${recomputedTerminal}; ${evidenceHeadMode ? "evidence-head" : "final-head"})`);
