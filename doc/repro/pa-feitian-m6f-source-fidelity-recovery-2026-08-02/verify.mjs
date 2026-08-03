#!/usr/bin/env node

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const evidenceHeadMode = process.argv.includes("--evidence-head");
const negativeMode = process.argv.includes("--negative");
const dataCapabilityReceiptPath = "../pa-feitian-m6f-causal-measurement-capability-2026-08-02/causal_measurement_capability_receipt_v1.json";
const dataCapabilityReceiptSha256 = "3b706bd7e5d2c5a488d1f580c947c3676f9762ea7c44b7ea65082b5c9929568f";
const reservePackagePath = "../pa-feitian-m6f-confirmation-reserve-2026-08-02";
const reserveReceiptName = "confirmation_reserve_custody_receipt_v2.json";
const reserveReceiptSha256 = "1a4baa1a72d5c7090397f2619429308679d9efa0d25c38dc50207c01da072610";
const reserveManifestName = "artifact_manifest_v1.json";
const reserveManifestSha256 = "0ff05ae1e3cc309ab4e903e42ca6bec004de0b7b06e6f72b03f16685f96e6b0f";
const reserveAttestationName = "independent_non_overlap_verification_attestation_v1.json";
const reserveAttestationSha256 = "d1929acdea17db8c7dc25458b179959fe0044d7e1e7d51dd95630aff4cb4e062";
const reserveVerifierName = "verify.mjs";
const reserveVerifierSha256 = "e79388b32f371d17e4226ba76b94858e69caa534240612392a2aae99e5c12c7d";
const acceptedReserveAccessLogLocator = "custody://data-owner/M6F-CONFIRMATION-RESERVE-V1/append-only-access-log-v1.jsonl";

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
  sourceReceipt: "source_author_provenance_receipt_v1.json",
  verify: "verify.mjs"
};

const manifestScope = [
  names.construct,
  names.contamination,
  names.measurement,
  names.reserve,
  names.schema,
  names.sourceReceipt,
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
  if (rule.oneOf) {
    let matches = 0;
    for (const candidate of rule.oneOf) {
      try {
        validate(value, candidate, location);
        matches += 1;
      } catch {
        // A oneOf candidate is allowed to fail; exactly one must pass.
      }
    }
    assert.equal(matches, 1, `${location}: oneOf`);
  }
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

function validateTimestamp(value, location) {
  assert.match(value, /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/, `${location}: timestamp syntax`);
  const parsed = new Date(value);
  assert.ok(!Number.isNaN(parsed.valueOf()), `${location}: timestamp parse`);
  assert.equal(parsed.toISOString().replace(".000Z", "Z"), value, `${location}: calendar-valid UTC timestamp`);
}

const ledger = parseCanonicalJson(names.ledger);
const construct = parseCanonicalJson(names.construct);
const measurement = parseCanonicalJson(names.measurement);
const reserve = parseCanonicalJson(names.reserve);
const sourceReceipt = parseCanonicalJson(names.sourceReceipt);
const manifest = parseCanonicalJson(names.manifest);

validate(ledger, schema.$defs.source_fidelity_ledger, "ledger");
validate(construct, schema.$defs.construct_dag, "construct");
validate(measurement, schema.$defs.measurement_readiness, "measurement");
validate(reserve, schema.$defs.confirmation_reserve_contract, "reserve");
validate(sourceReceipt, schema.$defs.source_author_provenance_receipt, "sourceReceipt");
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
const expectedSourceAuthorizationNodeIds = expectedLedgerIds.filter((nodeId) => nodeId !== "SF-03-DAILY-CHART");
const sourceReceiptSha256 = "28ffe0ac718eebb5453f60daf862bdd9961c7d74c2abba2ca987f9ec02f9cbb5";
const protocolBodySha256 = "dfd44c8eb6127a9dfaf6a872811144acd74e011add4e88d29bc002b5db635d83";
const protocolLocator = "https://github.com/algotradinglife/paired-trading/issues/77#issuecomment-5156155428";

function validateSourceReceipt(currentReceipt) {
  assert.equal(bytes(names.sourceReceipt).byteLength, 1653, "canonical source receipt byte length");
  assert.equal(digest(bytes(names.sourceReceipt)), sourceReceiptSha256, "canonical source receipt raw-byte hash");
  assert.equal(currentReceipt.approved_protocol.body_sha256, protocolBodySha256, "approved protocol body hash");
  assert.equal(currentReceipt.approved_protocol.body_utf8_byte_length, 2874, "approved protocol UTF-8 byte length");
  assert.equal(currentReceipt.approved_protocol.github_comment_id, 5156155428);
  assert.equal(currentReceipt.approved_protocol.locator, protocolLocator);
  assert.equal(currentReceipt.approved_protocol.created_at, "2026-08-02T07:17:40Z");
  assert.equal(currentReceipt.approved_protocol.updated_at, "2026-08-02T07:17:40Z");
  assert.equal(currentReceipt.authorization_class, "explicit_source_authorization");
  assert.equal(currentReceipt.authorization_received_at, "2026-08-02T07:23:23Z");
  assert.equal(currentReceipt.authorization_scope.approved_disposition, "prospective_source_authorized_annotation_adjudication_protocol");
  assert.deepEqual(currentReceipt.authorization_scope.approved_nodes, expectedSourceAuthorizationNodeIds);
  assert.equal(currentReceipt.authorization_scope.source_author_amendments, "none");
  assert.deepEqual(currentReceipt.public_safety, {
    identity: "withheld",
    raw_transcript: "not_recorded",
    sensitive_contact_detail: "not_recorded"
  });
  validateTimestamp(currentReceipt.authorization_received_at, "sourceReceipt.authorization_received_at");
  validateTimestamp(currentReceipt.approved_protocol.created_at, "sourceReceipt.approved_protocol.created_at");
  validateTimestamp(currentReceipt.approved_protocol.updated_at, "sourceReceipt.approved_protocol.updated_at");
}

validateSourceReceipt(sourceReceipt);

function validateSourceBindings(currentLedger) {
  validateTimestamp(currentLedger.acquisition_cutoff, "ledger.acquisition_cutoff");
  assert.equal(currentLedger.acquisition_cutoff, "2026-08-02T07:23:38Z", "exact PI provenance cutoff");
  assert.deepEqual(currentLedger.nodes.map((node) => node.node_id), expectedLedgerIds, "exact ledger node order/set");
  assert.deepEqual(currentLedger.nodes.map((node) => node.evidence.locator), expectedLocators, "exact source locators");
  assert.equal(new Set(expectedLedgerIds).size, 10);
  assert.ok(currentLedger.nodes.every((node) => node.critical_to_construct), "all ten nodes are critical");
  assert.ok(currentLedger.nodes.every((node) => node.abstention_rule.length > 0), "every node fails closed");
  assert.ok(currentLedger.nodes.every((node) => node.evidence.file_sha256 === "2ea78aa6e6addc24bbb132dc2d104d182ce24060e6a8be72ad120063fa4ed263"));
  assert.ok(currentLedger.nodes.every((node) => node.evidence.repository_revision === "715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a"));
  for (const node of currentLedger.nodes) {
    validateTimestamp(node.acquisition_or_authorization_at, `${node.node_id}.acquisition_or_authorization_at`);
    const isAuthorized = expectedSourceAuthorizationNodeIds.includes(node.node_id);
    assert.equal(
      node.acquisition_or_authorization_at,
      isAuthorized ? "2026-08-02T07:23:23Z" : "2026-08-02T07:13:30Z",
      `${node.node_id}: exact acquisition/authorization time`
    );
    assert.ok(
      new Date(node.acquisition_or_authorization_at) <= new Date(currentLedger.acquisition_cutoff),
      `${node.node_id}: acquisition/authorization must not follow cutoff`
    );
    assert.equal(node.status, isAuthorized ? "source_authorized" : "source_pinned", `${node.node_id}: exact source status`);
    if (isAuthorized) {
      assert.equal(node.authorization.authorization_class, "explicit_source_authorization", `${node.node_id}: authorization class`);
      assert.equal(node.authorization.authorization_received_at, sourceReceipt.authorization_received_at, `${node.node_id}: authorization time`);
      assert.equal(node.authorization.approved_disposition, sourceReceipt.authorization_scope.approved_disposition, `${node.node_id}: disposition`);
      assert.equal(node.authorization.protocol_body_sha256, protocolBodySha256, `${node.node_id}: protocol body hash`);
      assert.equal(node.authorization.protocol_locator, protocolLocator, `${node.node_id}: protocol locator`);
      assert.equal(node.authorization.receipt_path, names.sourceReceipt, `${node.node_id}: receipt path`);
      assert.equal(node.authorization.receipt_sha256, sourceReceiptSha256, `${node.node_id}: receipt hash`);
    } else {
      assert.equal(node.authorization, null, `${node.node_id}: source-pinned node has no protocol authorization`);
    }
    assert.notEqual(node.status, "method_constraint", `${node.node_id}: critical method proxy prohibited`);
  }
}

validateSourceBindings(ledger);

function validateSourceAuthorizationDependency(currentLedger) {
  const dependency = currentLedger.source_authorization_dependency;
  assert.equal(dependency.dependency_id, "M6F-SOURCE-AUTH-01");
  assert.deepEqual(dependency.requested_node_ids, expectedSourceAuthorizationNodeIds);
  assert.equal(dependency.request_body_sha256, "18eff5f6dbe6d90e8e36e261782ae8c784152d130dee95438acef9f6167f225f");
  assert.equal(dependency.request_locator, "https://github.com/algotradinglife/paired-trading/issues/77#issuecomment-5156135931");
  validateTimestamp(dependency.opened_at, "source_authorization_dependency.opened_at");
  assert.equal(dependency.opened_at, "2026-08-02T07:13:41Z", "source request external comment creation time");
  assert.equal(dependency.status, "closed_authorized", "source authorization dependency must bind the accepted closure");
  assert.notEqual(dependency.closed_evidence, null, "closed source dependency requires closure evidence");
  validate(dependency.closed_evidence, schema.$defs.source_authorization_closure_evidence, "source_authorization_dependency.closed_evidence");
  assert.equal(dependency.closed_evidence.authorization_class, "explicit_source_authorization");
  assert.equal(dependency.closed_evidence.authorization_received_at, sourceReceipt.authorization_received_at);
  assert.equal(dependency.closed_evidence.file_sha256, sourceReceiptSha256);
  assert.equal(dependency.closed_evidence.locator, names.sourceReceipt);
  assert.equal(dependency.closed_evidence.recorded_at, "2026-08-02T07:23:38Z");
  validateTimestamp(dependency.closed_evidence.authorization_received_at, "source_authorization_dependency.closed_evidence.authorization_received_at");
  validateTimestamp(dependency.closed_evidence.recorded_at, "source_authorization_dependency.closed_evidence.recorded_at");
}

validateSourceAuthorizationDependency(ledger);

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
const expectedDagReadiness = [
  "source_authorized_protocol",
  "source_authorized_protocol",
  "deterministic_rule",
  "source_authorized_protocol",
  "source_authorized_protocol",
  "source_authorized_protocol",
  "source_authorized_protocol",
  "source_authorized_protocol",
  "source_authorized_protocol",
  "source_authorized_protocol",
  "fail_closed"
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
  assert.deepEqual(currentConstruct.nodes.map((node) => node.readiness), expectedDagReadiness, "exact DAG readiness bindings");
  const management = currentConstruct.nodes.find((node) => node.node_id === "DAG-10-MANAGEMENT");
  const outcome = currentConstruct.nodes.find((node) => node.node_id === "DAG-11-OUTCOME-OBSERVATION");
  assert.equal(management.plane, "decision");
  assert.equal(management.readiness, "source_authorized_protocol", "SF-10 authorizes only causal management actions");
  assert.equal(outcome.plane, "outcome");
  assert.equal(outcome.readiness, "fail_closed", "future outcome observation is outside the source-authorized protocol");
  assert.notEqual(outcome.readiness, management.readiness, "decision authorization cannot inflate outcome-plane authority");
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
const expectedExternalDependencies = [
  {
    closure_evidence: {
      acceptance_locator: "https://github.com/algotradinglife/paired-trading/issues/79#issuecomment-5156979858",
      accepted_at: "2026-08-02T09:52:11Z",
      artifact_locator: "doc/repro/pa-feitian-m6f-causal-measurement-capability-2026-08-02/causal_measurement_capability_receipt_v1.json",
      artifact_sha256: dataCapabilityReceiptSha256,
      contamination_entry_id: "CONTAM-0015",
      manifest_sha256: "504f488d2168d537cc21a68812252fb94d87288a818357a04cfa9545774e7faa",
      merged_revision: "8f2c5fb54160a1c61ef6db13d6048e690eb560b1",
      result: "fail"
    },
    contract_locator: "https://github.com/algotradinglife/paired-trading/issues/79#issuecomment-5156235447",
    dependency_class: "measurement_capability",
    dependency_id: "M6F-DATA-CAPABILITY-01",
    issue: 79,
    locator: "https://github.com/algotradinglife/paired-trading/issues/79",
    owner_role: "data",
    status: "closed_failed"
  },
  {
    closure_evidence: {
      acceptance_locator: "https://github.com/algotradinglife/paired-trading/issues/80#issuecomment-5157958443",
      accepted_at: "2026-08-02T12:44:53Z",
      accepted_head: "81ef05de9a71dfb332fa28f86e2702c5a5252a66",
      artifact_locator: "doc/repro/pa-feitian-m6f-confirmation-reserve-2026-08-02/confirmation_reserve_custody_receipt_v2.json",
      artifact_sha256: reserveReceiptSha256,
      contamination_entry_id: "CONTAM-0016",
      independent_attestation_sha256: reserveAttestationSha256,
      manifest_sha256: reserveManifestSha256,
      merged_revision: "5da299892514c7ca2d7bf1c77baba32f9df9753b",
      result: "pass"
    },
    contract_locator: "https://github.com/algotradinglife/paired-trading/issues/80#issuecomment-5156235454",
    dependency_class: "confirmation_reserve",
    dependency_id: "M6F-CONFIRMATION-RESERVE-01",
    issue: 80,
    locator: "https://github.com/algotradinglife/paired-trading/issues/80",
    owner_role: "data",
    status: "closed_accepted"
  }
];

function deriveMeasurementResult(currentMeasurement) {
  const statuses = currentMeasurement.fields.map((field) => field.readiness_status);
  const capabilityOpen = currentMeasurement.external_dependencies.some(
    (dependency) => dependency.dependency_id === "M6F-DATA-CAPABILITY-01" && dependency.status === "open"
  );
  if (capabilityOpen) {
    assert.ok(statuses.every((status) => status === "blocked"), "open Data capability dependency requires all measurement fields to remain blocked");
    return "blocked";
  }
  assert.ok(!statuses.includes("blocked"), "blocked field requires the open Data capability dependency");
  return statuses.every((status) => ["pass", "not_applicable"].includes(status)) ? "pass" : "fail";
}

function validateExternalDependencyStates(currentMeasurement) {
  const openDependencyIds = currentMeasurement.external_dependencies
    .filter((dependency) => dependency.status === "open")
    .map((dependency) => dependency.dependency_id);
  assert.deepEqual(currentMeasurement.open_external_dependencies, openDependencyIds, "external dependency status aggregate");
  for (const dependency of currentMeasurement.external_dependencies) {
    if (dependency.status === "open") {
      assert.equal(dependency.closure_evidence, null, `${dependency.dependency_id}: open dependency cannot have closure evidence`);
    } else if (dependency.status === "closed_accepted") {
      assert.notEqual(dependency.closure_evidence, null, `${dependency.dependency_id}: accepted closure evidence required`);
      assert.equal(dependency.closure_evidence.result, "pass", `${dependency.dependency_id}: accepted result`);
    } else {
      assert.equal(dependency.status, "closed_failed");
      assert.notEqual(dependency.closure_evidence, null, `${dependency.dependency_id}: closed-negative evidence required`);
      assert.ok(["fail", "unavailable"].includes(dependency.closure_evidence.result), `${dependency.dependency_id}: closed-negative result`);
    }
  }
}

function validateMeasurementBindings(currentMeasurement, currentLedger = ledger) {
  assert.deepEqual(currentMeasurement.fields.map((field) => field.node_id), expectedLedgerIds, "measurement node order/set");
  assert.deepEqual(currentMeasurement.fields.map((field) => field.field_id), expectedMeasurementIds, "measurement field order/set");
  assert.deepEqual(
    currentMeasurement.fields.map((field) => field.evidence_locator),
    expectedLedgerIds.map((nodeId) => `${names.ledger}#${nodeId}`),
    "exact measurement-to-ledger locators"
  );
  validateExternalDependencyStates(currentMeasurement);
  assert.equal(new Set(currentMeasurement.fields.map((field) => field.field_id)).size, expectedLedgerIds.length);
  assert.ok(currentMeasurement.fields.every((field) => field.required_fields.length > 0));
  assert.deepEqual(currentMeasurement.external_dependencies, expectedExternalDependencies, "exact named external dependency contracts");
  assert.deepEqual(
    currentMeasurement.open_external_dependencies,
    expectedExternalDependencies.filter((dependency) => dependency.status === "open").map((dependency) => dependency.dependency_id)
  );
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
  assert.equal(currentLedger.source_authorization_dependency.status, "closed_authorized");
  for (const field of currentMeasurement.fields) {
    assert.equal(field.readiness_status, "fail", `${field.field_id}: accepted Data capability receipt is closed-negative`);
  }
  const receiptBytes = readFileSync(join(here, dataCapabilityReceiptPath));
  assert.equal(receiptBytes.byteLength, 116238, "accepted Data receipt byte length");
  assert.equal(digest(receiptBytes), dataCapabilityReceiptSha256, "accepted Data receipt raw-byte hash");
  const receipt = JSON.parse(receiptBytes.toString("utf8"));
  assert.equal(receipt.dependency_id, "M6F-DATA-CAPABILITY-01");
  assert.equal(receipt.issue_number, 79);
  assert.equal(receipt.measurement_contract_binding.raw_byte_length, 18581);
  assert.equal(receipt.measurement_contract_binding.raw_byte_sha256, "2ab764f77c90bf8ac979be7dde58a8d7352552d146d117cda3a8850c0b66e480");
  assert.deepEqual(receipt.capability_aggregate, {
    capability_result: "fail",
    fail_count: 10,
    failed_field_ids: expectedMeasurementIds,
    field_count: 10,
    pass_count: 0
  });
  assert.equal(currentMeasurement.measurement_result, deriveMeasurementResult(currentMeasurement), "derived measurement aggregate");
}

validateMeasurementBindings(measurement);

const contaminationRaw = text(names.contamination);
function parseContamination(raw) {
  assert.ok(!raw.startsWith("\ufeff"));
  assert.ok(!raw.includes("\r"));
  assert.ok(raw.endsWith("\n"));
  assert.ok(!raw.endsWith("\n\n"), "JSONL must have exactly one final newline");
  const lines = raw.slice(0, -1).split("\n");
  assert.ok(lines.every((line) => line.length > 0), "JSONL cannot contain a blank record");
  return lines.map((line, index) => {
    const entry = JSON.parse(line);
    assert.equal(line, canonicalCompact(entry), `contamination line ${index + 1}: canonical JSONL`);
    validate(entry, schema.$defs.contamination_entry, `contamination[${index}]`);
    return entry;
  });
}

const contamination = parseContamination(contaminationRaw);
assert.equal(contamination.length, 16);
const expectedContaminationSequence = [
  ["CONTAM-0001", "known_prior_conclusion_exposure", "P1-EXP-002-stop_p1_exp_002"],
  ["CONTAM-0002", "known_prior_proxy_exposure", "M6-operationalized_hypothesis_not_authentic"],
  ["CONTAM-0003", "known_prior_discovery_conclusion_exposure", "M6R-72-episodes-no_candidate"],
  ["CONTAM-0004", "known_prior_method_decision_exposure", "M6M-method_reconciled_recommend_path"],
  ["CONTAM-0005", "known_prior_source_scoping_exposure", "trade-philosopher-715ffec-source-narrative"],
  ["CONTAM-0006", "known_prior_method_scoping_exposure", "trade-philosopher-5802d0f-and-7691c31-method-sources"],
  ["CONTAM-0007", "known_prior_governance_scoping_exposure", "paired-trading-main-4fa3dc4-governance"],
  ["CONTAM-0008", "pre_gate_boundary_scoping_only", "M6F-pre-gate-boundary-scope"],
  ["CONTAM-0009", "post_gate_evidence_recovery", "M6F-post-gate-source-method-governance-audit"],
  ["CONTAM-0010", "source_authorization_request", "M6F-SOURCE-AUTH-01-request"],
  ["CONTAM-0011", "source_authorization_protocol", "PI-routing-comment-5156155428"],
  ["CONTAM-0012", "source_authorization_provenance", "M6F-source-author-provenance-receipt-v1"],
  ["CONTAM-0013", "external_dependency_opened", "M6F-DATA-CAPABILITY-01-issue-79"],
  ["CONTAM-0014", "external_dependency_opened", "M6F-CONFIRMATION-RESERVE-01-issue-80"],
  ["CONTAM-0015", "external_dependency_closed_negative", "M6F-DATA-CAPABILITY-01-merged-fail"],
  ["CONTAM-0016", "external_dependency_closed_accepted", "M6F-CONFIRMATION-RESERVE-01-merged-pass"]
];

function validateContaminationRequirements(currentContamination) {
  assert.deepEqual(
    currentContamination.map((entry) => [entry.entry_id, entry.access_class, entry.evidence_id]),
    expectedContaminationSequence,
    "complete contamination evidence sequence"
  );
}

validateContaminationRequirements(contamination);
function validateContaminationChain(currentContamination, currentLedger = ledger, currentSourceReceipt = sourceReceipt, currentMeasurement = measurement) {
  let priorHash = "0".repeat(64);
  let priorTimestamp = "";
  for (const [index, entry] of currentContamination.entries()) {
    assert.equal(entry.sequence, index + 1, `${entry.entry_id}: sequence`);
    assert.equal(entry.entry_id, `CONTAM-${String(index + 1).padStart(4, "0")}`);
    validateTimestamp(entry.timestamp, `${entry.entry_id}.timestamp`);
    assert.equal(entry.prior_entry_sha256, priorHash, `${entry.entry_id}: prior hash`);
    const unhashed = clone(entry);
    delete unhashed.entry_sha256;
    assert.equal(entry.entry_sha256, digest(canonicalCompact(unhashed)), `${entry.entry_id}: entry hash`);
    assert.ok(entry.timestamp >= priorTimestamp, `${entry.entry_id}: monotonic timestamp`);
    priorHash = entry.entry_sha256;
    priorTimestamp = entry.timestamp;
  }
  assert.equal(currentLedger.source_authorization_dependency.opened_at, currentContamination[9].timestamp, "source request dependency/comment/contamination timestamp binding");
  assert.equal(currentSourceReceipt.approved_protocol.created_at, currentContamination[10].timestamp, "approved protocol comment/contamination timestamp binding");
  assert.equal(currentSourceReceipt.authorization_received_at, currentContamination[11].timestamp, "source authorization receipt/contamination timestamp binding");
  assert.equal(currentContamination[12].timestamp, "2026-08-02T07:28:07Z", "Issue #79 creation timestamp");
  assert.equal(currentContamination[13].timestamp, "2026-08-02T07:28:09Z", "Issue #80 creation timestamp");
  assert.equal(currentContamination[14].timestamp, "2026-08-02T09:52:11Z", "Issue #79 accepted closed-negative timestamp");
  assert.equal(currentMeasurement.external_dependencies[0].closure_evidence.accepted_at, currentContamination[14].timestamp, "Data closure timestamp/contamination binding");
  assert.equal(currentMeasurement.external_dependencies[0].closure_evidence.contamination_entry_id, currentContamination[14].entry_id, "Data closure contamination binding");
  assert.equal(currentContamination[15].timestamp, "2026-08-02T12:44:53Z", "Issue #80 accepted closure timestamp");
  assert.equal(currentMeasurement.external_dependencies[1].closure_evidence.accepted_at, currentContamination[15].timestamp, "reserve closure timestamp/contamination binding");
  assert.equal(currentMeasurement.external_dependencies[1].closure_evidence.contamination_entry_id, currentContamination[15].entry_id, "reserve closure contamination binding");
}
validateContaminationChain(contamination);
const contaminationIds = new Set(contamination.map((entry) => entry.entry_id));
for (const node of ledger.nodes) {
  assert.ok(node.contamination_entry_ids.length > 0, `${node.node_id}: contamination binding`);
  for (const id of node.contamination_entry_ids) assert.ok(contaminationIds.has(id), `${node.node_id}: unknown contamination id ${id}`);
  assert.ok(node.contamination_entry_ids.includes("CONTAM-0009"), `${node.node_id}: post-gate evidence binding`);
  if (expectedSourceAuthorizationNodeIds.includes(node.node_id)) {
    assert.ok(node.contamination_entry_ids.includes("CONTAM-0010"), `${node.node_id}: source request binding`);
    assert.ok(node.contamination_entry_ids.includes("CONTAM-0011"), `${node.node_id}: approved protocol binding`);
    assert.ok(node.contamination_entry_ids.includes("CONTAM-0012"), `${node.node_id}: source provenance binding`);
  }
}
const m6rEntry = contamination.find((entry) => entry.entry_id === "CONTAM-0003");
assert.match(m6rEntry.evidence_id, /72-episodes-no_candidate/);
assert.match(m6rEntry.permitted_use, /not_inspected_or_used_for_confirmation/);

const expectedVisibleReserveMetadata = [
  "access_log_chain_head_sha256",
  "access_log_locator",
  "custodian_role",
  "eligibility_rule_sha256",
  "exclusion_registry_envelope_sha256",
  "exclusion_registry_plaintext_sha256",
  "exclusion_set_sha256",
  "identity_manifest_envelope_sha256",
  "identity_manifest_plaintext_sha256",
  "release_authority_role",
  "required_releasing_issue_type",
  "reserve_id",
  "schema_version",
  "sealed_at"
];
const expectedUnacceptedReserveMetadata = [
  "reserve_id",
  "eligibility_rule_sha256",
  "exclusion_set_sha256",
  "custodian_role",
  "sealed_at",
  "release_authority_role",
  "required_releasing_issue_type",
  "access_log_locator"
];
const acceptedOnlyReserveFields = [
  "accepted_custody_receipt_schema_version",
  "access_log_chain_head_sha256",
  "access_log_locator",
  "exclusion_registry_envelope_sha256",
  "exclusion_registry_plaintext_sha256",
  "identity_manifest_envelope_sha256",
  "identity_manifest_plaintext_sha256"
];

function validateReserveState(currentReserve) {
  assert.equal(currentReserve.eligibility_rule_sha256, digest(currentReserve.eligibility_rule));
  assert.equal(currentReserve.exclusion_set_sha256, digest(currentReserve.exclusion_rule));
  assert.match(currentReserve.exclusion_rule, /all 72 M6R episode IDs/);
  assert.equal(currentReserve.dependency_contract_locator, "https://github.com/algotradinglife/paired-trading/issues/80#issuecomment-5156235454");
  assert.equal(currentReserve.dependency_id, "M6F-CONFIRMATION-RESERVE-01");
  assert.equal(currentReserve.dependency_issue, 80);
  assert.equal(currentReserve.dependency_locator, "https://github.com/algotradinglife/paired-trading/issues/80");
  if (currentReserve.dependency_status === "closed_accepted") {
    assert.equal(currentReserve.access_log_locator, acceptedReserveAccessLogLocator);
    assert.deepEqual(currentReserve.permitted_metadata_visible_to_strategy, expectedVisibleReserveMetadata);
    assert.ok(acceptedOnlyReserveFields.every((field) => currentReserve[field] !== null), "accepted reserve requires every public custody commitment");
    assert.equal(currentReserve.status, "sealed");
    assert.notEqual(currentReserve.closure_evidence, null);
    assert.equal(currentReserve.closure_evidence.result, "pass");
    assert.equal(currentReserve.mechanically_enforceable, true);
    assert.ok(["data_owner", "data_custodian", "pi_approved_external_custodian"].includes(currentReserve.custodian_role), "sealed reserve needs a PI-approved non-Strategy custodian");
    validateTimestamp(currentReserve.sealed_at, "reserve.sealed_at");
    assert.equal(currentReserve.terminal_effect, "none");
  } else if (currentReserve.dependency_status === "closed_failed") {
    assert.deepEqual(currentReserve.permitted_metadata_visible_to_strategy, expectedUnacceptedReserveMetadata);
    assert.ok(acceptedOnlyReserveFields.every((field) => currentReserve[field] === null), "closed-negative reserve forbids accepted-positive custody commitments");
    assert.equal(currentReserve.status, "unavailable_no_custodian_or_sealed_identity_manifest");
    assert.notEqual(currentReserve.closure_evidence, null);
    assert.ok(["fail", "unavailable"].includes(currentReserve.closure_evidence.result));
    assert.equal(currentReserve.custodian_role, "unassigned_pi_approved_non_strategy_custodian");
    assert.equal(currentReserve.mechanically_enforceable, false);
    assert.equal(currentReserve.sealed_at, null);
    assert.equal(currentReserve.terminal_effect, "readiness_cannot_pass");
  } else {
    assert.equal(currentReserve.dependency_status, "open");
    assert.deepEqual(currentReserve.permitted_metadata_visible_to_strategy, expectedUnacceptedReserveMetadata);
    assert.ok(acceptedOnlyReserveFields.every((field) => currentReserve[field] === null), "open reserve forbids accepted-positive custody commitments");
    assert.equal(currentReserve.status, "blocked_pending_data_custodian_receipt");
    assert.equal(currentReserve.closure_evidence, null);
    assert.equal(currentReserve.custodian_role, "unassigned_pi_approved_non_strategy_custodian");
    assert.equal(currentReserve.mechanically_enforceable, false);
    assert.equal(currentReserve.sealed_at, null);
    assert.equal(currentReserve.terminal_effect, "readiness_cannot_pass");
  }
}

validateReserveState(reserve);

function validateAcceptedReserveProjection(currentReserve, receipt, attestation) {
  assert.deepEqual(Object.keys(receipt), expectedVisibleReserveMetadata, "exact PI-accepted public custody metadata projection");
  assert.equal(receipt.reserve_id, currentReserve.reserve_id);
  assert.equal(receipt.schema_version, currentReserve.accepted_custody_receipt_schema_version);
  assert.equal(receipt.access_log_locator, currentReserve.access_log_locator);
  assert.equal(receipt.access_log_chain_head_sha256, currentReserve.access_log_chain_head_sha256);
  assert.equal(attestation.access_log_chain_head_sha256, currentReserve.access_log_chain_head_sha256);
  assert.equal(receipt.eligibility_rule_sha256, currentReserve.eligibility_rule_sha256);
  assert.equal(receipt.exclusion_set_sha256, currentReserve.exclusion_set_sha256);
  assert.equal(receipt.exclusion_registry_envelope_sha256, currentReserve.exclusion_registry_envelope_sha256);
  assert.equal(receipt.exclusion_registry_plaintext_sha256, currentReserve.exclusion_registry_plaintext_sha256);
  assert.equal(receipt.identity_manifest_envelope_sha256, currentReserve.identity_manifest_envelope_sha256);
  assert.equal(receipt.identity_manifest_plaintext_sha256, currentReserve.identity_manifest_plaintext_sha256);
  assert.equal(receipt.custodian_role, currentReserve.custodian_role);
  assert.equal(receipt.sealed_at, currentReserve.sealed_at);
  assert.equal(receipt.release_authority_role, currentReserve.release_authority_role);
  assert.equal(receipt.required_releasing_issue_type, currentReserve.required_releasing_issue_type);
}

function validateAcceptedReserveArtifacts(currentReserve, currentMeasurement = measurement) {
  const closure = currentMeasurement.external_dependencies.find(
    (dependency) => dependency.dependency_id === "M6F-CONFIRMATION-RESERVE-01"
  ).closure_evidence;
  assert.deepEqual(currentReserve.closure_evidence, closure, "reserve contract/dependency closure evidence binding");
  const reservePackage = join(here, reservePackagePath);
  const receiptBytes = readFileSync(join(reservePackage, reserveReceiptName));
  const manifestBytes = readFileSync(join(reservePackage, reserveManifestName));
  const attestationBytes = readFileSync(join(reservePackage, reserveAttestationName));
  const verifierBytes = readFileSync(join(reservePackage, reserveVerifierName));
  assert.equal(digest(receiptBytes), reserveReceiptSha256, "accepted reserve receipt raw-byte hash");
  assert.equal(digest(manifestBytes), reserveManifestSha256, "accepted reserve manifest raw-byte hash");
  assert.equal(digest(attestationBytes), reserveAttestationSha256, "accepted reserve attestation raw-byte hash");
  assert.equal(digest(verifierBytes), reserveVerifierSha256, "accepted reserve verifier raw-byte hash");
  assert.equal(closure.artifact_sha256, reserveReceiptSha256);
  assert.equal(closure.manifest_sha256, reserveManifestSha256);
  assert.equal(closure.independent_attestation_sha256, reserveAttestationSha256);
  assert.equal(closure.accepted_head, "81ef05de9a71dfb332fa28f86e2702c5a5252a66");
  assert.equal(closure.merged_revision, "5da299892514c7ca2d7bf1c77baba32f9df9753b");
  const receipt = JSON.parse(receiptBytes.toString("utf8"));
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  assert.equal(manifest.dependency_id, "M6F-CONFIRMATION-RESERVE-01");
  assert.equal(manifest.issue_number, 80);
  assert.deepEqual(
    manifest.payloads.map((payload) => [payload.path, payload.raw_byte_sha256]),
    [
      [reserveReceiptName, reserveReceiptSha256],
      [reserveAttestationName, reserveAttestationSha256],
      [reserveVerifierName, reserveVerifierSha256]
    ]
  );
  const attestation = JSON.parse(attestationBytes.toString("utf8"));
  validateAcceptedReserveProjection(currentReserve, receipt, attestation);
  assert.equal(attestation.custody_receipt_raw_byte_sha256, reserveReceiptSha256);
  assert.equal(attestation.overall_result, "pass");
  assert.equal(attestation.assertion_count, 10);
  assert.equal(Object.keys(attestation.assertions).length, 10);
  assert.ok(Object.values(attestation.assertions).every((result) => result === true));
  assert.equal(attestation.reserve_nonempty, true);
  assert.equal(attestation.verifier_independent_from_custodian, true);
  assert.equal(attestation.no_strategy_access_or_release_before_verified_at, true);
}

validateAcceptedReserveArtifacts(reserve);

function recomputeTerminal(currentLedger, currentConstruct, currentMeasurement, currentReserve) {
  const sourceDependency = currentLedger.source_authorization_dependency;
  if (sourceDependency.status === "open") {
    return "source_fidelity_recovery_blocked";
  }
  const openDependencies = currentMeasurement.external_dependencies
    .filter((dependency) => dependency.status === "open")
    .map((dependency) => dependency.dependency_id);
  assert.deepEqual(currentMeasurement.open_external_dependencies, openDependencies, "open dependency aggregate");
  if (openDependencies.length > 0) {
    if (deriveMeasurementResult(currentMeasurement) === "blocked") {
      assert.ok(openDependencies.includes("M6F-DATA-CAPABILITY-01"), "blocked measurement must bind the Data capability dependency");
    }
    if (currentReserve.dependency_status === "open") {
      assert.ok(openDependencies.includes("M6F-CONFIRMATION-RESERVE-01"), "open reserve must be a named open dependency");
    }
    return "source_fidelity_recovery_blocked";
  }
  assert.notEqual(currentReserve.dependency_status, "open", "closed dependency aggregate cannot retain an open reserve");
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
  if (currentReserve.dependency_status === "closed_failed" || !currentReserve.mechanically_enforceable) {
    return "source_fidelity_measurement_failure";
  }
  return "source_fidelity_ready_for_preregistration_design";
}

const recomputedTerminal = recomputeTerminal(ledger, construct, measurement, reserve);
assert.equal(recomputedTerminal, "source_fidelity_measurement_failure");
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
assert.match(readme, /source_fidelity_measurement_failure/);
assert.match(readme, /PI may not open\s+a (?:separate )?preregistration-design\s+Issue/);

const actualFiles = readdirSync(here).sort();
const evidenceHeadFiles = Object.values(names).filter((name) => name !== names.receipt).sort();
const finalFiles = Object.values(names).sort();
assert.deepEqual(actualFiles, evidenceHeadMode ? evidenceHeadFiles : finalFiles, "exact package membership");
const sourceAwareRegexLiteralProbes = [/implementer/i, /foo_bar/gm];
assert.ok(sourceAwareRegexLiteralProbes.every((pattern) => pattern instanceof RegExp), "regex literal probes");

function receiptField(receipt, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matches = [...receipt.matchAll(new RegExp(`^${escaped}: (.+)$`, "gm"))];
  assert.equal(matches.length, 1, `receipt field ${label}`);
  return matches[0][1];
}

function validateReceipt(receipt, evidenceHead) {
  assert.ok(!receipt.startsWith("\ufeff"), "receipt UTF-8 BOM is forbidden");
  assert.ok(!receipt.includes("\r"), "receipt CR is forbidden");
  assert.ok(receipt.endsWith("\n") && !receipt.endsWith("\n\n"), "receipt needs exactly one final newline");
  assert.equal((receipt.match(/^\[ENGINEERING VALIDATION\]\[PASS\]$/gm) ?? []).length, 1, "exactly one PASS verdict");
  assert.doesNotMatch(receipt, /CHANGES_REQUIRED|FAIL(?:ED)?|unresolved critical/i, "receipt contradiction");
  const fields = Object.fromEntries([
    "Reviewer",
    "Reviewer independence",
    "Requested by",
    "Review locator",
    "Review body SHA-256",
    "Exact HEAD",
    "Issue",
    "Release",
    "Mutations",
    "Tests",
    "Clean replay",
    "Findings"
  ].map((label) => [label, receiptField(receipt, label)]));
  assert.match(fields.Reviewer, /^[A-Za-z0-9/][A-Za-z0-9._/-]{2,}$/);
  assert.doesNotMatch(fields.Reviewer, sourceAwareRegexLiteralProbes[0], "reviewer must not be the implementer");
  assert.equal(fields["Reviewer independence"], "fresh non-implementer");
  assert.equal(fields["Requested by"], "PI");
  assert.match(fields["Review locator"], /^https:\/\/github\.com\/algotradinglife\/paired-trading\/pull\/78#issuecomment-[0-9]+$/);
  assert.match(fields["Review body SHA-256"], /^[0-9a-f]{64}$/);
  assert.equal(fields["Exact HEAD"], evidenceHead);
  assert.equal(fields.Issue, "77");
  assert.equal(fields.Release, "not-applicable");
  assert.equal(fields.Mutations, "none");
  assert.equal(fields.Tests, "evidence-head verifier; negative verifier; manifest hashes; exact base-to-head diff-check");
  assert.equal(fields["Clean replay"], "pass from clean checkout");
  assert.equal(fields.Findings, "none");
  const manifestSha256 = receiptField(receipt, "Evidence manifest SHA-256");
  assert.equal(manifestSha256, digest(bytes(names.manifest)));
  const payloads = [...receipt.matchAll(/^Payload: ([^|\n]+) \| ([0-9]+) \| ([0-9a-f]{64})$/gm)]
    .map((match) => [match[1], Number(match[2]), match[3]]);
  assert.deepEqual(
    payloads,
    manifest.entries.map((entry) => [entry.path, entry.byte_length, entry.sha256]),
    "receipt payload hashes"
  );
  const expectedLines = [
    "[ENGINEERING VALIDATION][PASS]",
    `Reviewer: ${fields.Reviewer}`,
    `Reviewer independence: ${fields["Reviewer independence"]}`,
    `Requested by: ${fields["Requested by"]}`,
    `Review locator: ${fields["Review locator"]}`,
    `Review body SHA-256: ${fields["Review body SHA-256"]}`,
    `Exact HEAD: ${fields["Exact HEAD"]}`,
    `Issue: ${fields.Issue}`,
    `Release: ${fields.Release}`,
    `Mutations: ${fields.Mutations}`,
    `Tests: ${fields.Tests}`,
    `Clean replay: ${fields["Clean replay"]}`,
    `Findings: ${fields.Findings}`,
    `Evidence manifest SHA-256: ${manifestSha256}`,
    ...manifest.entries.map((entry) => `Payload: ${entry.path} | ${entry.byte_length} | ${entry.sha256}`)
  ];
  assert.equal(receipt, `${expectedLines.join("\n")}\n`, "receipt exact line set/order");
  return fields;
}

function validateFinalTopology(topology) {
  assert.match(topology.finalHead, /^[0-9a-f]{40}$/);
  assert.match(topology.parentHead, /^[0-9a-f]{40}$/);
  assert.notEqual(topology.finalHead, topology.parentHead);
  assert.equal(topology.parentCount, 1, "final receipt commit must have one parent");
  assert.equal(topology.receiptHead, topology.parentHead, "receipt must review the exact evidence parent");
  assert.deepEqual(topology.diffPaths, [`doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02/${names.receipt}`]);
  assert.equal(topology.readmeSame, true, "README must not drift after evidence review");
  assert.equal(topology.manifestSame, true, "manifest must not drift after evidence review");
}

function validateFinalEligibility(currentTerminal, currentMeasurement, currentReserve) {
  assert.notEqual(currentTerminal, "source_fidelity_recovery_blocked", "blocked evidence head cannot pass final mode");
  assert.equal(currentMeasurement.open_external_dependencies.length, 0, "final mode requires all external dependencies closed");
  assert.ok(currentMeasurement.external_dependencies.every((dependency) => dependency.status !== "open"), "final mode forbids open dependency records");
  validateReserveState(currentReserve);
  if (currentTerminal === "source_fidelity_ready_for_preregistration_design") {
    assert.equal(currentReserve.dependency_status, "closed_accepted", "ready terminal requires accepted reserve closure");
    assert.equal(currentReserve.status, "sealed", "ready terminal requires a sealed confirmation reserve");
    assert.equal(currentReserve.mechanically_enforceable, true, "ready terminal requires an enforceable confirmation reserve");
  } else {
    assert.ok(
      ["source_fidelity_measurement_failure", "source_fidelity_unrecoverable_construct"].includes(currentTerminal),
      "closed-negative final terminal must be explicit"
    );
    assert.ok(["closed_accepted", "closed_failed"].includes(currentReserve.dependency_status));
  }
}

if (!evidenceHeadMode) {
  validateFinalEligibility(recomputedTerminal, measurement, reserve);
  assert.ok(existsSync(join(here, names.receipt)), "independent receipt required at final head");
  const git = (...args) => execFileSync("git", args, { encoding: "utf8" }).trim();
  const repoRoot = git("rev-parse", "--show-toplevel");
  const finalHead = git("rev-parse", "HEAD");
  const parentLine = git("rev-list", "--parents", "-n", "1", finalHead).split(" ");
  const parentHead = parentLine[1] ?? "";
  const receipt = text(names.receipt);
  const fields = validateReceipt(receipt, parentHead);
  const packetPath = "doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02";
  const readParentBytes = (name) => execFileSync("git", ["show", `${parentHead}:${join(packetPath, name)}`], { cwd: repoRoot });
  validateFinalTopology({
    diffPaths: git("diff", "--name-only", parentHead, finalHead).split("\n").filter(Boolean),
    finalHead,
    manifestSame: digest(readParentBytes(names.manifest)) === digest(bytes(names.manifest)),
    parentCount: parentLine.length - 1,
    parentHead,
    readmeSame: digest(readParentBytes(names.readme)) === digest(bytes(names.readme)),
    receiptHead: fields["Exact HEAD"]
  });
}

function maskJavaScriptRegexLiterals(source) {
  const masked = source.split("");
  const prefixKeywords = new Set([
    "await", "case", "delete", "do", "else", "in", "instanceof", "new",
    "of", "return", "throw", "typeof", "void", "yield"
  ]);
  const blank = (start, end) => {
    for (let index = start; index < end; index += 1) {
      if (masked[index] !== "\n" && masked[index] !== "\r") masked[index] = " ";
    }
  };
  const quotedEnd = (start, quote) => {
    let index = start + 1;
    while (index < source.length) {
      if (source[index] === "\\") {
        index += 2;
      } else if (source[index] === quote) {
        return index + 1;
      } else {
        index += 1;
      }
    }
    return source.length;
  };
  const regexEnd = (start) => {
    let inCharacterClass = false;
    let index = start + 1;
    while (index < source.length) {
      const character = source[index];
      if (character === "\n" || character === "\r") return null;
      if (character === "\\") {
        index += 2;
        continue;
      }
      if (character === "[") inCharacterClass = true;
      if (character === "]") inCharacterClass = false;
      if (character === "/" && !inCharacterClass) {
        index += 1;
        while (index < source.length && /[A-Za-z]/.test(source[index])) index += 1;
        return index;
      }
      index += 1;
    }
    return null;
  };
  const lineCommentEnd = (start) => {
    const newline = source.indexOf("\n", start + 2);
    return newline === -1 ? source.length : newline;
  };
  const blockCommentEnd = (start) => {
    const close = source.indexOf("*/", start + 2);
    return close === -1 ? source.length : close + 2;
  };

  let scanCode;
  const scanTemplate = (start) => {
    let index = start;
    while (index < source.length) {
      if (source[index] === "\\") {
        index += 2;
      } else if (source[index] === "`") {
        return index + 1;
      } else if (source[index] === "$" && source[index + 1] === "{") {
        index = scanCode(index + 2, true);
      } else {
        index += 1;
      }
    }
    return source.length;
  };
  scanCode = (start = 0, stopAtTemplateBrace = false) => {
    let braceDepth = 0;
    let index = start;
    let previousToken = "prefix";
    while (index < source.length) {
      const character = source[index];
      if (index === 0 && source.startsWith("#!")) {
        const end = lineCommentEnd(0);
        blank(0, end);
        index = end;
        continue;
      }
      if (/\s/.test(character)) {
        index += 1;
        continue;
      }
      if (stopAtTemplateBrace && character === "}" && braceDepth === 0) return index + 1;
      if (character === "/" && source[index + 1] === "/") {
        index = lineCommentEnd(index);
        continue;
      }
      if (character === "/" && source[index + 1] === "*") {
        index = blockCommentEnd(index);
        continue;
      }
      if (character === "\"" || character === "'") {
        index = quotedEnd(index, character);
        previousToken = "value";
        continue;
      }
      if (character === "`") {
        index = scanTemplate(index + 1);
        previousToken = "value";
        continue;
      }
      if (character === "/") {
        if (previousToken !== "value") {
          const end = regexEnd(index);
          if (end !== null) {
            blank(index, end);
            index = end;
            previousToken = "value";
            continue;
          }
        }
        index += 1;
        previousToken = "prefix";
        continue;
      }
      if (/[A-Za-z_$]/.test(character)) {
        let end = index + 1;
        while (end < source.length && /[A-Za-z0-9_$]/.test(source[end])) end += 1;
        previousToken = prefixKeywords.has(source.slice(index, end)) ? "prefix" : "value";
        index = end;
        continue;
      }
      if (/[0-9]/.test(character)) {
        let end = index + 1;
        while (end < source.length && /[0-9A-Fa-f_xXobn.]/.test(source[end])) end += 1;
        index = end;
        previousToken = "value";
        continue;
      }
      if (character === "{") {
        braceDepth += 1;
        previousToken = "prefix";
      } else if (character === "}") {
        braceDepth = Math.max(0, braceDepth - 1);
        previousToken = "value";
      } else if (character === ")" || character === "]" || character === ".") {
        previousToken = "value";
      } else {
        previousToken = "prefix";
      }
      index += 1;
    }
    return index;
  };
  scanCode();
  return masked.join("");
}

const pathValueSafetyPatterns = [
  ["generic absolute POSIX path in public text", /(?:^|[\s"'`()\[\]{}=,:;!?> <])\/(?!\/)(?=[^\s"'`])[^\s"'`\])}>;,!?#]*/m],
];
const publicSafetyPatterns = [
  ["established private/local root", /(?:^|[\s"'`(=:])\/(?:home|Users|root|mnt|tmp|var|srv|opt)\//m],
  ["forward-slash UNC local path", /(?:^|[\s"'`()\[\]{}=;!?> <])\/\/(?=[^\s"'`])[^\s"'`\])}>;,!?#]*/m],
  ["Windows or backslash UNC local path", /(?:^|[\s"'`(=])(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+\\[^\\\s]+)[^\s"'`]*/m],
  ["local file URI", /\bfile:\/{1,3}[^\s"'`]+/i],
  ["private data-file extension", /\.(?:csv|parquet)\b/i],
  ["private key", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
  ["GitHub token", /(?:gh[oprsu]_|github_pat_)[A-Za-z0-9_]{20,}/],
  ["Slack token", /xox[baprs]-[A-Za-z0-9-]{10,}/],
  ["AWS access key", /AKIA[0-9A-Z]{16}/],
  ["OpenAI token", /sk-[A-Za-z0-9]{20,}/],
  ["email identity", /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i],
  ["credential assignment", /(?:password|secret|token)\s*[:=]\s*["'][^"']{8,}["']/i],
  ["licensed row payload", /"(?:open|high|low|close|volume)"\s*:\s*-?[0-9]+(?:\.[0-9]+)?/],
  ["CSV-like OHLCV row", /^(?:[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[^,\n]+)?),-?[0-9]+(?:\.[0-9]+)?(?:,-?[0-9]+(?:\.[0-9]+)?){4,}$/m],
  ["raw contract identifier", /\b(?:SHFE|CZCE|DCE|CFFEX|INE|GFEX)\.[A-Za-z]+\d/i]
];
const positiveClaimPatterns = [
  /authentic[\s,;:—–-]+feitian\b[^.\n]{0,40}\b(?:supported|validated|confirmed)\b/i,
  /\bstrategy\b[^.\n]{0,30}\b(?:fully[\s,;:—–-]+)?validated\b/i,
  /profitability[\s,;:—–-]+(?:is[\s,;:—–-]+)?supported/i,
  /\bm7\b[^.\n]{0,30}\bauthorized\b/i,
  /\bexperiment\b[^.\n]{0,30}\bauthorized\b/i,
  /trader[\s,;:—–-]+gt[\s,;:—–-]+(?:is[\s,;:—–-]+)?confirmed/i,
  /\bPI\s+may\s+(?:now\s+)?open\s+(?:a\s+)?(?:separate\s+)?preregistration-design\s+Issue\b/i
];

const maskerProbePath = ["", "data", "private"].join("/");
const maskerProbeSlash = String.fromCharCode(47);
const maskerProbeContexts = [
  `const stringProbe = "${maskerProbePath}";`,
  `const templateProbe = \`${maskerProbePath}\`;`,
  `${maskerProbeSlash}${maskerProbeSlash} line probe ${maskerProbePath}`,
  `${maskerProbeSlash}* block probe ${maskerProbePath} *${maskerProbeSlash}`
];
const maskerProbeRegexes = [
  `const regexA = ${maskerProbeSlash}implementer${maskerProbeSlash}i;`,
  `const regexB = ${maskerProbeSlash}foo_bar${maskerProbeSlash}gm;`
];
const maskedProbeSource = maskJavaScriptRegexLiterals(
  [...maskerProbeContexts, ...maskerProbeRegexes].join("\n")
);
for (const context of maskerProbeContexts) {
  assert.ok(maskedProbeSource.includes(context), `masker must preserve non-regex context: ${context.split(" ")[1]}`);
}
for (const regex of maskerProbeRegexes) {
  assert.ok(!maskedProbeSource.includes(regex), "masker must blank an actual JavaScript regex token");
}

function validatePublicSafety(content, claimContent = content, { javascriptSource = false } = {}) {
  const pathValueContent = javascriptSource ? maskJavaScriptRegexLiterals(content) : content;
  for (const [label, pattern] of pathValueSafetyPatterns) {
    assert.equal(pattern.test(pathValueContent), false, `public-safe scan: ${label}`);
  }
  for (const [label, pattern] of publicSafetyPatterns) {
    assert.doesNotMatch(content, pattern, `public-safe scan: ${label}`);
  }
  for (const pattern of positiveClaimPatterns) {
    assert.doesNotMatch(claimContent, pattern, `forbidden positive claim: ${pattern.source}`);
  }
}

function collectPackageText(overrides = {}, includeVerifier = true) {
  return actualFiles
    .filter((name) => includeVerifier || name !== names.verify)
    .map((name) => overrides[name] ?? text(name))
    .join("\n");
}

function validatePackagePublicSafety(overrides = {}) {
  for (const name of actualFiles) {
    const content = overrides[name] ?? text(name);
    validatePublicSafety(content, "", { javascriptSource: name === names.verify });
  }
  for (const pattern of positiveClaimPatterns) {
    assert.doesNotMatch(
      collectPackageText(overrides, false),
      pattern,
      `forbidden positive claim: ${pattern.source}`
    );
  }
}

validatePackagePublicSafety();

if (negativeMode) {
  let rejected = 0;
  const reject = (mutation) => {
    assert.throws(mutation);
    rejected += 1;
  };
  reject(() => {
    const mutated = clone(ledger);
    mutated.unexpected = true;
    validate(mutated, schema.$defs.source_fidelity_ledger, "negative.extra_key");
  });
  reject(() => {
    const mutated = clone(ledger);
    mutated.nodes[0].status = "source_pinned";
    validateSourceBindings(mutated);
  });
  reject(() => {
    const mutated = clone(ledger);
    mutated.nodes[0].evidence.locator = `trade-philosopher:${sourcePath}#L20-L22`;
    validateSourceBindings(mutated);
  });
  reject(() => {
    const mutated = clone(ledger);
    mutated.source_authorization_dependency.closed_evidence.file_sha256 = "0".repeat(64);
    validateSourceAuthorizationDependency(mutated);
  });
  reject(() => {
    const mutated = clone(ledger);
    mutated.source_authorization_dependency.status = "closed_no_route";
    validateSourceAuthorizationDependency(mutated);
  });
  reject(() => {
    const mutated = clone(sourceReceipt);
    mutated.approved_protocol.body_sha256 = "0".repeat(64);
    validateSourceReceipt(mutated);
  });
  reject(() => {
    const mutated = clone(sourceReceipt);
    mutated.authorization_scope.approved_nodes.reverse();
    validateSourceReceipt(mutated);
  });
  reject(() => {
    const mutated = clone(ledger);
    mutated.nodes[0].authorization.receipt_sha256 = "0".repeat(64);
    validateSourceBindings(mutated);
  });
  reject(() => {
    const mutated = clone(contamination[3]);
    mutated.permitted_use = "mutated";
    const unhashed = clone(mutated);
    delete unhashed.entry_sha256;
    assert.equal(mutated.entry_sha256, digest(canonicalCompact(unhashed)));
  });
  reject(() => {
    const mutated = clone(construct);
    mutated.nodes = mutated.nodes.filter((node) => node.plane !== "outcome");
    validateConstructBindings(mutated);
  });
  reject(() => {
    const mutated = clone(construct);
    mutated.edges[0] = { from: "DAG-03-DAILY-EVENT", to: "DAG-02-OPTION-CONTEXT" };
    validateConstructBindings(mutated);
  });
  reject(() => {
    const mutated = clone(construct);
    mutated.nodes[2].readiness = "source_authorized_protocol";
    validateConstructBindings(mutated);
  });
  reject(() => {
    const mutated = clone(construct);
    mutated.nodes.find((node) => node.node_id === "DAG-11-OUTCOME-OBSERVATION").readiness = "source_authorized_protocol";
    validateConstructBindings(mutated);
  });
  reject(() => {
    const mutated = clone(measurement);
    mutated.measurement_result = "pass";
    validateMeasurementBindings(mutated);
  });
  reject(() => {
    const mutated = clone(measurement);
    mutated.fields[0].evidence_locator = `${names.ledger}#SF-02-OPTION-CONTRACT`;
    validateMeasurementBindings(mutated);
  });
  reject(() => {
    const mutated = clone(measurement);
    mutated.external_dependencies[0].issue = 80;
    validateMeasurementBindings(mutated);
  });
  reject(() => {
    const mutated = clone(measurement);
    mutated.open_external_dependencies.push("M6F-CONFIRMATION-RESERVE-01");
    validateMeasurementBindings(mutated);
  });
  reject(() => {
    const mutated = clone(contamination);
    mutated.splice(4, 1);
    validateContaminationRequirements(mutated);
  });
  reject(() => {
    const mutated = clone(reserve);
    mutated.dependency_issue = 79;
    validateReserveState(mutated);
  });
  reject(() => {
    const mutated = clone(reserve);
    mutated.access_log_locator = names.contamination;
    validateReserveState(mutated);
  });
  reject(() => {
    const mutated = clone(reserve);
    mutated.permitted_metadata_visible_to_strategy.pop();
    validateReserveState(mutated);
  });
  reject(() => {
    const mutated = clone(reserve);
    mutated.closure_evidence.artifact_sha256 = "0".repeat(64);
    validateAcceptedReserveArtifacts(mutated);
  });
  reject(() => {
    const reservePackage = join(here, reservePackagePath);
    const receipt = JSON.parse(readFileSync(join(reservePackage, reserveReceiptName), "utf8"));
    const attestation = JSON.parse(readFileSync(join(reservePackage, reserveAttestationName), "utf8"));
    attestation.access_log_chain_head_sha256 = "0".repeat(64);
    validateAcceptedReserveProjection(reserve, receipt, attestation);
  });
  reject(() => {
    const mutated = clone(reserve);
    mutated.dependency_status = "open";
    validateReserveState(mutated);
  });
  reject(() => {
    assert.equal("source_fidelity_ready_for_preregistration_design", recomputedTerminal);
  });
  validateFinalEligibility(recomputedTerminal, measurement, reserve);

  const closedNegativeEvidence = {
    acceptance_locator: "https://github.com/algotradinglife/paired-trading/issues/80#issuecomment-5157000000",
    accepted_at: "2026-08-02T10:00:00Z",
    artifact_locator: "doc/repro/pa-feitian-m6f-confirmation-reserve/confirmation_reserve_unavailable_receipt_v1.json",
    artifact_sha256: "d".repeat(64),
    contamination_entry_id: "CONTAM-0016",
    manifest_sha256: "e".repeat(64),
    merged_revision: "f".repeat(40),
    result: "unavailable"
  };
  const closedNegativeMeasurement = clone(measurement);
  closedNegativeMeasurement.external_dependencies[1].status = "closed_failed";
  closedNegativeMeasurement.external_dependencies[1].closure_evidence = closedNegativeEvidence;
  closedNegativeMeasurement.open_external_dependencies = [];
  closedNegativeMeasurement.terminal_result = "source_fidelity_measurement_failure";
  validate(closedNegativeMeasurement, schema.$defs.measurement_readiness, "closedNegativeMeasurement");
  validateExternalDependencyStates(closedNegativeMeasurement);
  assert.equal(deriveMeasurementResult(closedNegativeMeasurement), "fail");
  const closedNegativeReserve = {
    accepted_custody_receipt_schema_version: null,
    access_log_chain_head_sha256: null,
    access_log_locator: null,
    artifact_type: "pa_feitian_m6f_confirmation_reserve_contract",
    closure_evidence: closedNegativeEvidence,
    custodian_role: "unassigned_pi_approved_non_strategy_custodian",
    dependency_contract_locator: "https://github.com/algotradinglife/paired-trading/issues/80#issuecomment-5156235454",
    dependency_id: "M6F-CONFIRMATION-RESERVE-01",
    dependency_issue: 80,
    dependency_locator: "https://github.com/algotradinglife/paired-trading/issues/80",
    dependency_status: "closed_failed",
    eligibility_rule: reserve.eligibility_rule,
    eligibility_rule_sha256: reserve.eligibility_rule_sha256,
    exclusion_registry_envelope_sha256: null,
    exclusion_registry_plaintext_sha256: null,
    exclusion_rule: reserve.exclusion_rule,
    exclusion_set_sha256: reserve.exclusion_set_sha256,
    identity_manifest_envelope_sha256: null,
    identity_manifest_plaintext_sha256: null,
    mechanically_enforceable: false,
    permitted_metadata_visible_to_strategy: expectedUnacceptedReserveMetadata,
    release_authority_role: "pi",
    required_releasing_issue_type: "pi_approved_preregistration_design",
    reserve_id: "M6F-CONFIRMATION-RESERVE-V1",
    schema_version: "pa_feitian_m6f_confirmation_reserve_contract_v1",
    sealed_at: null,
    status: "unavailable_no_custodian_or_sealed_identity_manifest",
    strategy_visibility_prohibition: reserve.strategy_visibility_prohibition,
    terminal_effect: "readiness_cannot_pass"
  };
  assert.ok(acceptedOnlyReserveFields.every((field) => closedNegativeReserve[field] === null));
  validate(closedNegativeReserve, schema.$defs.confirmation_reserve_contract, "closedNegativeReserve");
  validateReserveState(closedNegativeReserve);
  const honestOpenReserve = clone(closedNegativeReserve);
  honestOpenReserve.closure_evidence = null;
  honestOpenReserve.dependency_status = "open";
  honestOpenReserve.status = "blocked_pending_data_custodian_receipt";
  validate(honestOpenReserve, schema.$defs.confirmation_reserve_contract, "honestOpenReserve");
  validateReserveState(honestOpenReserve);
  const closedNegativeTerminal = recomputeTerminal(ledger, construct, closedNegativeMeasurement, closedNegativeReserve);
  assert.equal(closedNegativeTerminal, "source_fidelity_measurement_failure", "closed-negative #80 must terminate after all dependencies close");
  validateFinalEligibility(closedNegativeTerminal, closedNegativeMeasurement, closedNegativeReserve);
  reject(() => assert.equal(closedNegativeTerminal, "source_fidelity_recovery_blocked"));
  reject(() => {
    const mutated = clone(closedNegativeReserve);
    mutated.status = "blocked_pending_data_custodian_receipt";
    validateReserveState(mutated);
  });
  for (const field of acceptedOnlyReserveFields) {
    reject(() => {
      const mutated = clone(closedNegativeReserve);
      mutated[field] = reserve[field];
      validate(mutated, schema.$defs.confirmation_reserve_contract, `closedNegativeLeakage.${field}`);
    });
  }
  reject(() => {
    const mutated = clone(closedNegativeReserve);
    mutated.permitted_metadata_visible_to_strategy = expectedVisibleReserveMetadata;
    validate(mutated, schema.$defs.confirmation_reserve_contract, "closedNegativeLeakage.metadata");
  });
  reject(() => {
    const mutated = clone(reserve);
    mutated.access_log_chain_head_sha256 = null;
    validate(mutated, schema.$defs.confirmation_reserve_contract, "closedAcceptedMissingCommitment");
  });
  reject(() => {
    const mutated = clone(closedNegativeMeasurement);
    mutated.external_dependencies[1].closure_evidence = null;
    validateExternalDependencyStates(mutated);
  });

  const receiptHead = "a".repeat(40);
  const receiptLines = [
    "[ENGINEERING VALIDATION][PASS]",
    "Reviewer: fresh-independent-reviewer",
    "Reviewer independence: fresh non-implementer",
    "Requested by: PI",
    "Review locator: https://github.com/algotradinglife/paired-trading/pull/78#issuecomment-5156999999",
    `Review body SHA-256: ${"c".repeat(64)}`,
    `Exact HEAD: ${receiptHead}`,
    "Issue: 77",
    "Release: not-applicable",
    "Mutations: none",
    "Tests: evidence-head verifier; negative verifier; manifest hashes; exact base-to-head diff-check",
    "Clean replay: pass from clean checkout",
    "Findings: none",
    `Evidence manifest SHA-256: ${digest(bytes(names.manifest))}`,
    ...manifest.entries.map((entry) => `Payload: ${entry.path} | ${entry.byte_length} | ${entry.sha256}`)
  ];
  const validReceipt = `${receiptLines.join("\n")}\n`;
  validateReceipt(validReceipt, receiptHead);
  reject(() => validateReceipt(validReceipt.replace(receiptHead, "0".repeat(40)), receiptHead));
  reject(() => validateReceipt(validReceipt.replace(receiptHead, "b".repeat(40)), receiptHead));
  for (const label of [
    "Reviewer",
    "Reviewer independence",
    "Requested by",
    "Review locator",
    "Review body SHA-256",
    "Exact HEAD",
    "Issue",
    "Release",
    "Mutations",
    "Tests",
    "Clean replay",
    "Findings"
  ]) {
    reject(() => validateReceipt(validReceipt.replace(new RegExp(`^${label}: .+\\n`, "m"), ""), receiptHead));
  }
  reject(() => validateReceipt(validReceipt.replace("fresh-independent-reviewer", "implementer"), receiptHead));
  reject(() => validateReceipt(validReceipt.replace("[ENGINEERING VALIDATION][PASS]\n", "[ENGINEERING VALIDATION][PASS]\n[CHANGES_REQUIRED]\n"), receiptHead));
  reject(() => validateReceipt(validReceipt.replace("Findings: none\n", "Findings: none\nUnresolved critical finding remains.\n"), receiptHead));
  reject(() => validateReceipt(validReceipt.replace("evidence-head verifier; negative verifier; manifest hashes; exact base-to-head diff-check", "x"), receiptHead));
  reject(() => validateReceipt(validReceipt.replace("pass from clean checkout", "x"), receiptHead));
  reject(() => validateReceipt(validReceipt.replace("pull/78#issuecomment-5156999999", "issues/77#issuecomment-5156999999"), receiptHead));
  reject(() => validateReceipt(validReceipt.replace("c".repeat(64), "Z".repeat(64)), receiptHead));
  reject(() => validateReceipt(validReceipt.replace(digest(bytes(names.manifest)), "0".repeat(64)), receiptHead));
  reject(() => validateReceipt(validReceipt.replace(manifest.entries[0].sha256, "0".repeat(64)), receiptHead));

  const validTopology = {
    diffPaths: [`doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02/${names.receipt}`],
    finalHead: "b".repeat(40),
    manifestSame: true,
    parentCount: 1,
    parentHead: receiptHead,
    readmeSame: true,
    receiptHead
  };
  validateFinalTopology(validTopology);
  reject(() => validateFinalTopology({ ...validTopology, parentHead: "c".repeat(40) }));
  reject(() => validateFinalTopology({ ...validTopology, parentCount: 2 }));
  reject(() => validateFinalTopology({ ...validTopology, diffPaths: [...validTopology.diffPaths, "README.md"] }));
  reject(() => validateFinalTopology({ ...validTopology, readmeSame: false }));
  reject(() => validateFinalTopology({ ...validTopology, manifestSame: false }));

  reject(() => {
    const mutated = clone(ledger);
    mutated.nodes[0].acquisition_or_authorization_at = "2999-01-01T00:00:00Z";
    validateSourceBindings(mutated);
  });
  reject(() => {
    const mutated = clone(ledger);
    mutated.source_authorization_dependency.opened_at = "2999-01-01T00:00:00Z";
    validateSourceAuthorizationDependency(mutated);
  });
  reject(() => {
    const mutated = clone(contamination);
    mutated[9].timestamp = "2999-01-01T00:00:00Z";
    for (let index = 9; index < mutated.length; index += 1) {
      mutated[index].prior_entry_sha256 = index === 0 ? "0".repeat(64) : mutated[index - 1].entry_sha256;
      const unhashed = clone(mutated[index]);
      delete unhashed.entry_sha256;
      mutated[index].entry_sha256 = digest(canonicalCompact(unhashed));
    }
    validateContaminationChain(mutated);
  });

  for (const badTimestamp of ["2026-13-02T07:00:00Z", "2026-02-30T07:00:00Z", "2026-08-02T25:00:00Z"]) {
    reject(() => validateTimestamp(badTimestamp, "negative.timestamp"));
  }
  reject(() => parseContamination(contaminationRaw.slice(0, -1)));
  reject(() => parseContamination(`${contaminationRaw}\n`));
  reject(() => parseContamination(contaminationRaw.replace("\n", "\n\n")));

  const publicSafetyBypasses = [
    ["", "home", "example", "private.txt"].join("/"),
    ["", "root", "private.txt"].join("/"),
    ["", "mnt", "private", "source.dat"].join("/"),
    ["", "tmp", "private", "source.dat"].join("/"),
    ["licensed-source", "csv"].join("."),
    ["licensed-source", "parquet"].join("."),
    ["C:", "Users", "example", "private.txt"].join("\\"),
    ["-----BEGIN", "PRIVATE KEY-----"].join(" "),
    `gho_${"A".repeat(24)}`,
    `github_pat_${"A".repeat(24)}`,
    `xoxb-${"A".repeat(24)}`,
    `AKIA${"A".repeat(16)}`,
    `sk-${"A".repeat(24)}`,
    ["source.author", "example.com"].join("@"),
    "password: \"abcdefgh\"",
    "\"open\": 12",
    "2026-01-02,1,2,3,4,5"
  ];
  for (const bypass of publicSafetyBypasses) reject(() => validatePublicSafety(bypass));
  const packageBoundaryMutations = [
    ["", "mnt", "private", "source-author", ["licensed-feitian", "csv"].join(".")].join("/"),
    ...["home", "Users", "root", "tmp", "var", "srv", "opt"].map((root) => ["", root, "private", "source.dat"].join("/")),
    ["", "data", "private", "source.dat"].join("/"),
    ["D:", "private", "source.dat"].join("\\"),
    ["", "", "private-server", "licensed-share", "source.dat"].join("\\"),
    ["file:", "srv", "private", "source.dat"].join("/"),
    ["file:", "", "", "srv", "private", "source.dat"].join("/"),
    ["licensed-source", "csv"].join("."),
    ["licensed-source", "parquet"].join("."),
    ["SHFE", "au2606"].join(".")
  ];
  for (const leak of packageBoundaryMutations) {
    reject(() => {
      const mutatedReadme = `${readme}\nInternal replay locator: ${leak}\n`;
      const overrides = { [names.readme]: mutatedReadme };
      validatePackagePublicSafety(overrides);
    });
  }
  const genericPosixPath = ["", "data", "private", "source.dat"].join("/");
  const independentReviewPathFragments = [
    ["", "data", "private", "id"].join("/"),
    ["", "data", "private", ""].join("/"),
    `${genericPosixPath}:42`,
    `[${genericPosixPath}]`,
    ["", "", "private-server", "licensed-share", "source.dat"].join("/"),
    ["", "", "private-server", "licensed-share", ""].join("/"),
    ["", "", "private-server", "licensed-share", "source.dat:42"].join("/"),
    ["", "secret"].join("/"),
    ["", "data", "private", "source+raw.dat"].join("/"),
    ["", "", "private-server", "C$", "source.dat"].join("/"),
    ...["{}", "()", "[]", "<>", "+", "$", "@", "%", "&", "=", "~", ",", ";", "!", "#", "?"].map(
      (component) => ["", "data", `private${component}share`, "source.dat"].join("/")
    )
  ];
  const pairedDelimiterBoundaryFragments = ["{", "}", "]", "<"].map(
    (delimiter) => `x${delimiter}${genericPosixPath}`
  );
  for (const injectedReadme of [
    `${readme}\nInternal replay is stored at ${genericPosixPath}\n`,
    `${readme}\n${genericPosixPath}\n`,
    ...independentReviewPathFragments.map(
      (pathFragment) => `${readme}\nInternal replay is stored at ${pathFragment}\n`
    )
  ]) {
    reject(() => {
      const overrides = { [names.readme]: injectedReadme };
      validatePackagePublicSafety(overrides);
    });
  }
  const verifierSource = text(names.verify);
  for (const pathFragment of independentReviewPathFragments) {
    for (const injectedVerifier of [
      `${verifierSource}\nconst publicSafetyStringProbe = "${pathFragment}";\n`,
      `${verifierSource}\nconst publicSafetyTemplateProbe = \`${pathFragment}\`;\n`,
      `${verifierSource}\n// public-safety comment probe: ${pathFragment}\n`
    ]) {
      reject(() => validatePackagePublicSafety({ [names.verify]: injectedVerifier }));
    }
  }
  for (const pathFragment of independentReviewPathFragments.slice(-5)) {
    reject(() => validatePackagePublicSafety({
      [names.verify]: `${verifierSource}\n/* public-safety block-comment probe: ${pathFragment} */\n`
    }));
  }
  for (const pathFragment of pairedDelimiterBoundaryFragments) {
    for (const injectedVerifier of [
      `${verifierSource}\nconst pairedBoundaryStringProbe = "${pathFragment}";\n`,
      `${verifierSource}\nconst pairedBoundaryTemplateProbe = \`${pathFragment}\`;\n`,
      `${verifierSource}\n// paired-boundary line probe: ${pathFragment}\n`,
      `${verifierSource}\n/* paired-boundary block probe: ${pathFragment} */\n`
    ]) {
      reject(() => validatePackagePublicSafety({ [names.verify]: injectedVerifier }));
    }
  }
  const committedVerifierLeakPath = ["", "data", "private"].join("/");
  const committedVerifierLeakValue = `x}${committedVerifierLeakPath}`;
  const reboundVerifier = `${verifierSource}\nconst committedVerifierLeakProbe = "${committedVerifierLeakValue}";\n`;
  const reboundManifest = clone(manifest);
  const reboundVerifierEntry = reboundManifest.entries.find((entry) => entry.path === names.verify);
  reboundVerifierEntry.byte_length = Buffer.byteLength(reboundVerifier);
  reboundVerifierEntry.sha256 = digest(reboundVerifier);
  const reboundManifestText = `${JSON.stringify(sortKeys(reboundManifest), null, 2)}\n`;
  const reboundReadme = readme.replace(manifestBinding[1], digest(reboundManifestText));
  assert.equal(reboundVerifierEntry.byte_length, Buffer.byteLength(reboundVerifier), "rebound verifier byte binding");
  assert.equal(reboundVerifierEntry.sha256, digest(reboundVerifier), "rebound verifier hash binding");
  assert.match(reboundReadme, new RegExp(digest(reboundManifestText)), "rebound README manifest binding");
  reject(() => validatePackagePublicSafety({
    [names.manifest]: reboundManifestText,
    [names.readme]: reboundReadme,
    [names.verify]: reboundVerifier
  }));
  validatePublicSafety(
    "https://github.com/algotradinglife/paired-trading custody://data-owner/M6F-CONFIRMATION-RESERVE-V1/log relative/path/file"
  );
  const positiveClaimBypasses = [
    "Authentic Feitian is now supported.",
    "The strategy is fully validated.",
    "PROFITABILITY, IS, SUPPORTED",
    "M7 is hereby authorized.",
    "Experiment is hereby authorized.",
    "Trader GT confirmed",
    "PI may now open a preregistration-design Issue from this packet."
  ];
  for (const bypass of positiveClaimBypasses) reject(() => validatePublicSafety("safe", bypass));

  console.log("negative mutations: PASS (" + rejected + "/" + rejected + " rejected)");
}

console.log(`M6F source-fidelity verification: PASS (${recomputedTerminal}; ${evidenceHeadMode ? "evidence-head" : "final-head"})`);
