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
const sourcePath = "doc/pa-replication/feitian-option-decision-tree-design-2026-06-17.md";
const expectedLocators = [
  `trade-philosopher:${sourcePath}#L33`,
  `trade-philosopher:${sourcePath}#L34`,
  `trade-philosopher:${sourcePath}#L30-L32`,
  `trade-philosopher:${sourcePath}#L36-L37;${sourcePath}#L57-L62;${sourcePath}#L127-L128`,
  `trade-philosopher:${sourcePath}#L43-L44;${sourcePath}#L57-L62;${sourcePath}#L66-L74;${sourcePath}#L127-L128`,
  `trade-philosopher:${sourcePath}#L38-L42;${sourcePath}#L128-L129`,
  `trade-philosopher:${sourcePath}#L39-L42;${sourcePath}#L128-L129`,
  `trade-philosopher:${sourcePath}#L35-L44;${sourcePath}#L57-L62`,
  `trade-philosopher:${sourcePath}#L37-L45`,
  `trade-philosopher:${sourcePath}#L46-L55;${sourcePath}#L119-L129`
];

function validateSourceBindings(currentLedger) {
  assert.deepEqual(currentLedger.nodes.map((node) => node.node_id), expectedLedgerIds, "exact ledger node order/set");
  assert.deepEqual(currentLedger.nodes.map((node) => node.evidence.locator), expectedLocators, "exact source locators");
  assert.equal(new Set(expectedLedgerIds).size, 10);
  assert.ok(currentLedger.nodes.every((node) => node.critical_to_construct), "all ten nodes are critical");
  assert.ok(currentLedger.nodes.every((node) => node.abstention_rule.length > 0), "every node fails closed");
  assert.ok(currentLedger.nodes.every((node) => node.evidence.file_sha256 === "2ea78aa6e6addc24bbb132dc2d104d182ce24060e6a8be72ad120063fa4ed263"));
  assert.ok(currentLedger.nodes.every((node) => node.evidence.repository_revision === "715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a"));
  for (const node of currentLedger.nodes) {
    if (node.status === "source_authorized") {
      assert.equal(node.evidence.authorization_class, "explicit_source_authorization", `${node.node_id}: authorization class`);
    }
    assert.notEqual(node.status, "method_constraint", `${node.node_id}: critical method proxy prohibited`);
  }
}

validateSourceBindings(ledger);

const expectedDagBindings = [
  ["DAG-01-UNDERLYING-DIRECTION", "SF-01-UNDERLYING-DIRECTION", "perception"],
  ["DAG-02-OPTION-CONTEXT", "SF-02-OPTION-CONTRACT", "decision"],
  ["DAG-03-DAILY-EVENT", "SF-03-DAILY-CHART", "event"],
  ["DAG-04-DD-GEOMETRY", "SF-04-DD-LOW-LINE", "perception"],
  ["DAG-05-HIGH-LINE-GEOMETRY", "SF-05-DESCENDING-HIGH-LINE", "perception"],
  ["DAG-06-ONE-B-TWO-B", "SF-06-ONE-B-TWO-B", "perception"],
  ["DAG-07-HOLISTIC-QUALITY", "SF-07-HOLISTIC-QUALITY", "perception"],
  ["DAG-08-ENTRY-PATH", "SF-08-ENTRY-ORDERING", "decision"],
  ["DAG-09-INVALIDATION", "SF-09-STRUCTURAL-INVALIDATION", "decision"],
  ["DAG-10-MANAGEMENT", "SF-10-PREMIUM-MANAGEMENT", "decision"],
  ["DAG-11-OUTCOME-OBSERVATION", "SF-10-PREMIUM-MANAGEMENT", "outcome"]
];
const expectedDagEdges = [
  ["DAG-01-UNDERLYING-DIRECTION", "DAG-02-OPTION-CONTEXT"],
  ["DAG-02-OPTION-CONTEXT", "DAG-03-DAILY-EVENT"],
  ["DAG-03-DAILY-EVENT", "DAG-04-DD-GEOMETRY"],
  ["DAG-03-DAILY-EVENT", "DAG-05-HIGH-LINE-GEOMETRY"],
  ["DAG-04-DD-GEOMETRY", "DAG-06-ONE-B-TWO-B"],
  ["DAG-05-HIGH-LINE-GEOMETRY", "DAG-06-ONE-B-TWO-B"],
  ["DAG-06-ONE-B-TWO-B", "DAG-07-HOLISTIC-QUALITY"],
  ["DAG-07-HOLISTIC-QUALITY", "DAG-08-ENTRY-PATH"],
  ["DAG-08-ENTRY-PATH", "DAG-09-INVALIDATION"],
  ["DAG-09-INVALIDATION", "DAG-10-MANAGEMENT"],
  ["DAG-10-MANAGEMENT", "DAG-11-OUTCOME-OBSERVATION"]
];

function validateConstructBindings(currentConstruct) {
  assert.deepEqual(
    currentConstruct.nodes.map((node) => [node.node_id, node.ledger_node_id, node.plane]),
    expectedDagBindings,
    "exact staged DAG node order/bindings/planes"
  );
  assert.deepEqual(currentConstruct.edges.map((edge) => [edge.from, edge.to]), expectedDagEdges, "exact staged DAG edges");
  assert.deepEqual(currentConstruct.plane_order, ["event", "perception", "decision", "outcome"]);
  assert.deepEqual(new Set(currentConstruct.nodes.map((node) => node.plane)), new Set(currentConstruct.plane_order), "four planes are distinct and present");
  assert.deepEqual(new Set(currentConstruct.nodes.map((node) => node.ledger_node_id)), new Set(expectedLedgerIds), "DAG binds every ledger node");
  assert.ok(currentConstruct.nodes.every((node) => ["deterministic_rule", "source_authorized_protocol", "fail_closed"].includes(node.readiness)));
}

validateConstructBindings(construct);

const expectedMeasurementIds = [
  "MEAS-01-UNDERLYING-DIRECTION",
  "MEAS-02-OPTION-CONTRACT",
  "MEAS-03-DAILY-OPTION-CANDLE",
  "MEAS-04-DD-GEOMETRY",
  "MEAS-05-DESCENDING-HIGH-GEOMETRY",
  "MEAS-06-ONE-B-TWO-B",
  "MEAS-07-HOLISTIC-QUALITY",
  "MEAS-08-ENTRY-DECISION",
  "MEAS-09-STRUCTURAL-INVALIDATION",
  "MEAS-10-PREMIUM-MANAGEMENT"
];

function deriveMeasurementResult(currentMeasurement) {
  const statuses = currentMeasurement.fields.map((field) => field.readiness_status);
  if (currentMeasurement.open_external_dependency !== null) {
    assert.ok(statuses.includes("blocked"), "open dependency requires a blocked measurement field");
    return "blocked";
  }
  assert.ok(!statuses.includes("blocked"), "blocked field requires an open dependency");
  return statuses.every((status) => ["pass", "not_applicable"].includes(status)) ? "pass" : "fail";
}

function validateMeasurementBindings(currentMeasurement) {
  assert.deepEqual(currentMeasurement.fields.map((field) => field.node_id), expectedLedgerIds, "measurement node order/set");
  assert.deepEqual(currentMeasurement.fields.map((field) => field.field_id), expectedMeasurementIds, "measurement field order/set");
  assert.deepEqual(
    currentMeasurement.fields.map((field) => field.evidence_locator),
    expectedLedgerIds.map((nodeId) => `${names.ledger}#${nodeId}`),
    "exact measurement-to-ledger locators"
  );
  assert.equal(new Set(currentMeasurement.fields.map((field) => field.field_id)).size, expectedLedgerIds.length);
  assert.ok(currentMeasurement.fields.every((field) => field.required_fields.length > 0));
  for (const field of currentMeasurement.fields) {
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
  assert.equal(currentMeasurement.measurement_result, deriveMeasurementResult(currentMeasurement), "derived measurement aggregate");
}

validateMeasurementBindings(measurement);

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
const expectedContaminationSequence = [
  ["CONTAM-0001", "known_prior_conclusion_exposure", "P1-EXP-002-stop_p1_exp_002"],
  ["CONTAM-0002", "known_prior_proxy_exposure", "M6-operationalized_hypothesis_not_authentic"],
  ["CONTAM-0003", "known_prior_discovery_conclusion_exposure", "M6R-72-episodes-no_candidate"],
  ["CONTAM-0004", "known_prior_method_decision_exposure", "M6M-method_reconciled_recommend_path"],
  ["CONTAM-0005", "pinned_source_recovery_evidence", "trade-philosopher-715ffec-source-narrative"],
  ["CONTAM-0006", "pinned_method_constraint_evidence", "trade-philosopher-5802d0f-and-7691c31-method-sources"],
  ["CONTAM-0007", "governance_evidence", "paired-trading-main-4fa3dc4-governance"],
  ["CONTAM-0008", "boundary_and_reserve_audit", "M6F-no-new-authorization-no-sealed-reserve"]
];

function validateContaminationRequirements(currentContamination) {
  assert.deepEqual(
    currentContamination.map((entry) => [entry.entry_id, entry.access_class, entry.evidence_id]),
    expectedContaminationSequence,
    "complete contamination evidence sequence"
  );
}

validateContaminationRequirements(contamination);
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

const expectedVisibleReserveMetadata = [
  "reserve_id",
  "eligibility_rule_sha256",
  "exclusion_set_sha256",
  "custodian_role",
  "sealed_at",
  "release_authority_role",
  "required_releasing_issue_type",
  "access_log_locator"
];

function validateReserveState(currentReserve) {
  assert.equal(currentReserve.eligibility_rule_sha256, digest(currentReserve.eligibility_rule));
  assert.equal(currentReserve.exclusion_set_sha256, digest(currentReserve.exclusion_rule));
  assert.match(currentReserve.exclusion_rule, /all 72 M6R episode IDs/);
  assert.equal(currentReserve.access_log_locator, names.contamination);
  assert.deepEqual(currentReserve.permitted_metadata_visible_to_strategy, expectedVisibleReserveMetadata);
  if (currentReserve.status === "sealed") {
    assert.equal(currentReserve.mechanically_enforceable, true);
    assert.ok(["data_custodian", "pi_approved_external_custodian"].includes(currentReserve.custodian_role), "sealed reserve needs a PI-approved non-Strategy custodian");
    assert.match(currentReserve.sealed_at, /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/);
    assert.equal(currentReserve.terminal_effect, "none");
  } else {
    assert.equal(currentReserve.custodian_role, "unassigned_pi_approved_non_strategy_custodian");
    assert.equal(currentReserve.mechanically_enforceable, false);
    assert.equal(currentReserve.sealed_at, null);
    assert.equal(currentReserve.terminal_effect, "readiness_cannot_pass");
  }
}

validateReserveState(reserve);

function recomputeTerminal(currentLedger, currentConstruct, currentMeasurement, currentReserve) {
  if (currentMeasurement.open_external_dependency !== null) return "source_fidelity_recovery_blocked";
  const unresolvedCritical = currentLedger.nodes.some(
    (node) => node.critical_to_construct && !["source_pinned", "source_authorized"].includes(node.status)
  );
  const incompleteCriticalProtocol = currentLedger.nodes.some((node) => {
    if (!node.critical_to_construct) return false;
    const bindings = currentConstruct.nodes.filter((candidate) => candidate.ledger_node_id === node.node_id);
    return !bindings.some((binding) => ["deterministic_rule", "source_authorized_protocol"].includes(binding.readiness));
  });
  if (unresolvedCritical || incompleteCriticalProtocol) return "source_fidelity_unrecoverable_construct";
  if (deriveMeasurementResult(currentMeasurement) !== "pass") return "source_fidelity_measurement_failure";
  if (!currentReserve.mechanically_enforceable || currentReserve.status !== "sealed") return "source_fidelity_measurement_failure";
  return "source_fidelity_ready_for_preregistration_design";
}

const recomputedTerminal = recomputeTerminal(ledger, construct, measurement, reserve);
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
    const mutated = clone(ledger);
    mutated.nodes[0].status = "source_authorized";
    validateSourceBindings(mutated);
  });
  assert.throws(() => {
    const mutated = clone(ledger);
    mutated.nodes[0].evidence.locator = `trade-philosopher:${sourcePath}#L20-L22`;
    validateSourceBindings(mutated);
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
    validateConstructBindings(mutated);
  });
  assert.throws(() => {
    const mutated = clone(construct);
    mutated.edges[0] = { from: "DAG-03-DAILY-EVENT", to: "DAG-02-OPTION-CONTEXT" };
    validateConstructBindings(mutated);
  });
  assert.throws(() => {
    const mutated = clone(measurement);
    mutated.measurement_result = "pass";
    validateMeasurementBindings(mutated);
  });
  assert.throws(() => {
    const mutated = clone(measurement);
    mutated.fields[0].evidence_locator = `${names.ledger}#SF-02-OPTION-CONTRACT`;
    validateMeasurementBindings(mutated);
  });
  assert.throws(() => {
    const mutated = clone(contamination);
    mutated.splice(4, 1);
    validateContaminationRequirements(mutated);
  });
  assert.throws(() => {
    const mutated = clone(reserve);
    mutated.status = "sealed";
    mutated.mechanically_enforceable = true;
    mutated.sealed_at = "2026-08-02T07:00:00Z";
    mutated.terminal_effect = "none";
    validateReserveState(mutated);
  });
  assert.throws(() => {
    assert.equal("source_fidelity_ready_for_preregistration_design", recomputedTerminal);
  });
  console.log("negative mutations: PASS (11/11 rejected)");
}

console.log(`M6F source-fidelity verification: PASS (${recomputedTerminal}; ${evidenceHeadMode ? "evidence-head" : "final-head"})`);
