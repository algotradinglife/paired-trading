#!/usr/bin/env node

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const requirementsName = "measurement_interface_requirements_v1.json";
const upstreamName = "upstream_measurement_readiness_v2.json";
const receiptName = "causal_measurement_capability_receipt_v1.json";
const manifestName = "artifact_manifest_v1.json";
const readmeName = "README.md";
const verifierName = "verify.mjs";
const packageLocator = "doc/repro/pa-feitian-m6f-causal-measurement-capability-2026-08-02";
const normalCommand = `node ${packageLocator}/verify.mjs`;
const negativeCommand = `${normalCommand} --negative`;

function bytes(path) {
  return readFileSync(path);
}

function parse(path) {
  return JSON.parse(bytes(path).toString("utf8"));
}

function parseBytes(value) {
  return JSON.parse(value.toString("utf8"));
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sorted(value) {
  if (Array.isArray(value)) return value.map(sorted);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sorted(value[key])]));
  }
  return value;
}

function canonicalPretty(value) {
  return `${JSON.stringify(sorted(value), null, 2)}\n`;
}

function canonicalCompact(value) {
  return JSON.stringify(sorted(value));
}

function immutableFileBytes(revision, locator) {
  const options = { cwd: repoRoot, maxBuffer: 16 * 1024 * 1024 };
  try {
    return execFileSync("jj", ["file", "show", "-r", revision, locator], options);
  } catch (error) {
    if (error?.code !== "ENOENT" && error?.status === 0) throw error;
    return execFileSync("git", ["show", `${revision}:${locator}`], options);
  }
}

function strictUtcTimestamp(value, context) {
  assert.match(value, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/, `${context} syntax`);
  const milliseconds = Date.parse(value);
  assert.equal(Number.isFinite(milliseconds), true, `${context} calendar`);
  assert.equal(new Date(milliseconds).toISOString(), value.replace("Z", ".000Z"), `${context} calendar`);
  return milliseconds;
}

function exactKeys(value, expected, context) {
  assert.deepEqual(Object.keys(value).sort(), [...expected].sort(), `${context} keys`);
}

function assertCanonicalText(value, textValue, context) {
  assert.equal(canonicalPretty(value), textValue, `${context} must be canonical UTF-8/LF JSON`);
}

function stringLeaves(value) {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(stringLeaves);
  if (value && typeof value === "object") return Object.values(value).flatMap(stringLeaves);
  return [];
}

function assertPublicSafe(value) {
  const publicText = canonicalPretty(value);
  const scanTexts = [publicText, ...stringLeaves(value)];
  for (const forbidden of [
    "\\\\Users\\\\", ".parquet", ".csv", "github_pat_", "ghp_", "sk-", "xoxb-",
    "-----BEGIN PRIVATE KEY-----", "authorization: bearer", "api_key=", "client_secret=",
    "password=", "requests.get(", "requests.post(", "akshare.", "tqsdk.", "yfinance.",
    "pd.read_csv(", "pd.read_parquet(",
  ]) {
    assert.equal(scanTexts.some((textValue) => textValue.toLowerCase().includes(forbidden.toLowerCase())), false, `public package contains ${forbidden}`);
  }
  const contains = (pattern) => scanTexts.some((textValue) => pattern.test(textValue));
  assert.equal(contains(/\bAKIA[0-9A-Z]{16}\b/), false, "public package contains an AWS access-key identity");
  assert.equal(contains(/authorization\s*:\s*(?:basic|bearer)\s+\S+/i), false, "public package contains an authorization credential");
  assert.equal(contains(/(?:api[_-]?key|client[_-]?secret|password|access[_-]?token)\s*[:=]\s*["']?[^\s,"'}]+/i), false, "public package contains a credential-shaped assignment");
  assert.equal(contains(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i), false, "public package contains an email identity");
  assert.equal(contains(/file:\/{1,3}[^\s"'`]+/i), false, "public package contains a local file URI");
  assert.equal(contains(/(?:^|[\s"'`(=])\/(?!\/)(?:[A-Za-z0-9._-]+\/)+[A-Za-z0-9._-]+/m), false, "public package contains an absolute POSIX path");
  assert.equal(contains(/(?:^|[\s"'])(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+\\[^\\\s]+)[^\s"']*/m), false, "public package contains an absolute Windows or UNC path");
  assert.equal(contains(/(?:date|datetime|timestamp),open,high,low,close(?:,volume)?/i), false, "public package contains a raw OHLC header");
  assert.equal(contains(/\d{4}-\d{2}-\d{2}(?:T[^,\s]+)?\s*,\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?){3,}/), false, "public package contains a CSV-like raw OHLC row");
  assert.equal(contains(/(?:from\s+|import\s+)(?:akshare|tqsdk|yfinance)\b/i), false, "public package contains provider import code");
  const jsonLikeSegments = publicText.match(/\{[^{}]{0,800}\}/g) ?? [];
  const numericOhlcKey = (key) => new RegExp(`\\\\?"${key}\\\\?"\\s*:\\s*-?\\d+(?:\\.\\d+)?`, "i");
  assert.equal(jsonLikeSegments.some((segment) => ["open", "high", "low", "close"].every((key) => numericOhlcKey(key).test(segment))), false, "public package contains a JSON-like raw OHLC row");
  assert.equal(contains(/M6R-[0-9a-f]{20}/i), false, "public package contains an M6R episode identity");
  assert.equal(contains(/\b(?:SHFE|CZCE|DCE|CFFEX|INE|GFEX)\.[A-Za-z]+\d/i), false, "public package contains a raw contract identity");
}

function hasDeepKey(value, target) {
  if (Array.isArray(value)) return value.some((item) => hasDeepKey(item, target));
  if (!value || typeof value !== "object") return false;
  return Object.hasOwn(value, target) || Object.values(value).some((item) => hasDeepKey(item, target));
}

function sum(values) {
  return values.reduce((total, value) => total + value, 0);
}

function dailyBarEndNormalizationWithoutEmbeddedProviderLineage(cells) {
  const dailyCells = cells.filter((cell) => cell.cadence === "daily");
  return dailyCells.length > 0 && dailyCells.every((cell) =>
    cell.timestamp_semantics.provider_bar_end_semantics_bound_file_count === cell.source_file_count
    && cell.timestamp_semantics.embedded_provider_metadata_file_count === 0
  );
}

const requirementsPath = join(here, requirementsName);
const upstreamPath = join(here, upstreamName);
const receiptPath = join(here, receiptName);
const manifestPath = join(here, manifestName);
const requirements = parse(requirementsPath);
const receipt = parse(receiptPath);
const manifest = parse(manifestPath);

const expectedRequirements = [
  ["MEAS-01-UNDERLYING-DIRECTION", "SF-01-UNDERLYING-DIRECTION", "causally_available_underlying_or_regime_record", ["underlying_identity", "direction_state", "direction_available_at"]],
  ["MEAS-02-OPTION-CONTRACT", "SF-02-OPTION-CONTRACT", "as_of_option_contract_master_and_selection_state", ["contract_identity", "option_type", "strike", "expiry", "listed_at", "delisted_at", "selection_available_at"]],
  ["MEAS-03-DAILY-OPTION-CANDLE", "SF-03-DAILY-CHART", "completed_exchange_option_daily_candle", ["contract_identity", "trading_date", "open", "high", "low", "close", "bar_available_at", "source_version"]],
  ["MEAS-04-DD-GEOMETRY", "SF-04-DD-LOW-LINE", "derived_causal_perception_trace", ["anchor_ids", "construction_version", "projected_value", "geometry_available_at"]],
  ["MEAS-05-DESCENDING-HIGH-GEOMETRY", "SF-05-DESCENDING-HIGH-LINE", "derived_causal_perception_trace", ["chart_source", "anchor_ids", "construction_version", "break_state", "break_available_at"]],
  ["MEAS-06-ONE-B-TWO-B", "SF-06-ONE-B-TWO-B", "source_authorized_perception_annotation_or_rule", ["classification", "context_start", "context_end", "annotator_authorization_class", "classification_available_at"]],
  ["MEAS-07-HOLISTIC-QUALITY", "SF-07-HOLISTIC-QUALITY", "source_authorized_perception_annotation_or_rule", ["quality_state", "context_ref", "authorization_class", "decision_cutoff"]],
  ["MEAS-08-ENTRY-DECISION", "SF-08-ENTRY-ORDERING", "derived_causal_decision_trace", ["entry_path", "contract_identity", "decision_at", "fill_state", "conflict_state"]],
  ["MEAS-09-STRUCTURAL-INVALIDATION", "SF-09-STRUCTURAL-INVALIDATION", "derived_causal_decision_trace", ["reference_structure", "invalidation_value", "evaluation_rule", "available_at"]],
  ["MEAS-10-PREMIUM-MANAGEMENT", "SF-10-PREMIUM-MANAGEMENT", "causal_option_premium_and_lifecycle_observation", ["contract_identity", "premium_price", "price_basis", "available_at", "expiry_state", "roll_from", "roll_to", "row_disposition"]],
].map(([field_id, node_id, source_class, required_fields]) => ({
  field_id,
  node_id,
  required_fields,
  source_class,
}));

const upstreamSemanticKeys = [
  "available_at_and_decision_cutoff",
  "bar_open_and_end_semantics",
  "evidence_locator",
  "exchange_timezone_and_session",
  "expiry_and_roll_mapping",
  "fail_closed_behavior",
  "missing_and_rejected_row_accounting",
  "option_lifecycle_and_selection_state",
  "premium_price_basis",
  "provenance_and_replay_binding",
];

const expectedUpstreamSemanticHashes = [
  "fa6e90d267a31092c5e2dbcda98f6303f58f921852fa6bb68416a572c46057e8",
  "f220d30d9da039857b49cb4df8eaacb9d1a39e311a7c688bbe07616e40d82956",
  "5adb8e8a7dd77771ee08dcc63322beb01e2c1245bd05b433ddb69245d34bbf12",
  "882ba2991fbfffe46822bfb57e047b1687bd3eac5fe7150e49b90c5c73d58fbf",
  "26b08a82e20518661800be511136312bc2d791a8eb5d656a6b5470f6c89a2054",
  "428a2ab0b830f097199757683eba2df339778b6d563a494a8643f650a062b94a",
  "f4369ebd14fe96c8ec345c107845d4aebb79fd1f625a8d32d563744a3dcb13b3",
  "e84b67afcae6d3e72171b1013840b789a395d2f4ee0446bc2824b32287e3a75f",
  "ccb4729c0dd32cbc266fd63d06a27ab696bec95b198939c66df70965026dceec",
  "6ac73e34b8513e7fed792ba817b6d560ed51289eb265ea586a81998ca970a6da",
];

const semanticKeys = [
  "available_at_and_decision_cutoff",
  "bar_open_end_and_finalization",
  "exchange_timezone_session_and_trading_date",
  "expiry_and_roll_mapping",
  "option_lifecycle_and_asof_selection",
  "premium_price_basis",
  "provider_source_version_and_provenance",
];

const expectedStatusMatrix = {
  "BP-UNDERLYING-DAILY": {
    available_at_and_decision_cutoff: "fail",
    bar_open_end_and_finalization: "fail",
    exchange_timezone_session_and_trading_date: "fail",
    expiry_and_roll_mapping: "not_applicable",
    option_lifecycle_and_asof_selection: "not_applicable",
    premium_price_basis: "not_applicable",
    provider_source_version_and_provenance: "fail",
  },
  "BP-OPTION-CONTRACT": {
    available_at_and_decision_cutoff: "fail",
    bar_open_end_and_finalization: "fail",
    exchange_timezone_session_and_trading_date: "fail",
    expiry_and_roll_mapping: "fail",
    option_lifecycle_and_asof_selection: "fail",
    premium_price_basis: "not_applicable",
    provider_source_version_and_provenance: "fail",
  },
  "BP-OPTION-DAILY": Object.fromEntries(semanticKeys.map((key) => [key, "fail"])),
  "BP-DERIVED-TRACE": Object.fromEntries(semanticKeys.map((key) => [key, "fail"])),
  "BP-DERIVED-TRACE-CONDITIONAL-CHART": Object.fromEntries(semanticKeys.map((key) => [key, "fail"])),
  "BP-PREMIUM-LIFECYCLE": Object.fromEntries(semanticKeys.map((key) => [key, "fail"])),
};

const expectedFieldProfileIds = [
  "BP-UNDERLYING-DAILY",
  "BP-OPTION-CONTRACT",
  "BP-OPTION-DAILY",
  "BP-DERIVED-TRACE",
  "BP-DERIVED-TRACE-CONDITIONAL-CHART",
  "BP-DERIVED-TRACE",
  "BP-DERIVED-TRACE",
  "BP-DERIVED-TRACE",
  "BP-DERIVED-TRACE",
  "BP-PREMIUM-LIFECYCLE",
];

const expectedOperationalSemantics = {
  "BP-UNDERLYING-DAILY": {
    deterministic_replay_rule: "Verify the bound public evidence bytes, select daily underlying interface aggregates in declared family order, and fail whenever requested, missing or late denominators or available_at are unavailable.",
    fail_closed_behavior: "Emit no direction state and permit no downstream contract selection when bar finalization, available_at or accounting is incomplete.",
  },
  "BP-OPTION-CONTRACT": {
    deterministic_replay_rule: "Verify the exact option-input audit bytes and parsed-contract-set hash; reject the interface because filename parsing is not an as-of contract master.",
    fail_closed_behavior: "Select no option contract when any lifecycle, expiry, eligibility, availability or tie field is missing.",
  },
  "BP-OPTION-DAILY": {
    deterministic_replay_rule: "Verify the bound audits, reproduce six-family daily option aggregates in declared order, and reject because availability and complete row-accounting denominators cannot be reconstructed.",
    fail_closed_behavior: "Reject the candle and every dependent perception or decision when finalization, lifecycle, price basis, available_at or accounting is incomplete.",
  },
  "BP-DERIVED-TRACE": {
    deterministic_replay_rule: "Verify that no bound evidence artifact materializes the required derived trace, then emit fail without constructing, imputing or outcome-tuning one.",
    fail_closed_behavior: "Emit unknown or no trace; do not synthesize anchors, geometry, labels or decisions.",
  },
  "BP-DERIVED-TRACE-CONDITIONAL-CHART": {
    deterministic_replay_rule: "Verify that no admitted evidence selects an option-versus-underlying chart source or materializes the required trace; evaluate both conditional branches and fail without selecting a chart plane.",
    fail_closed_behavior: "Emit no line or break state while chart source, inherited candle semantics, causal provenance or trace accounting is unresolved.",
  },
  "BP-PREMIUM-LIFECYCLE": {
    deterministic_replay_rule: "Verify the bound option evidence and reject management measurement because price availability, exact lifecycle transitions and complete action accounting are absent.",
    fail_closed_behavior: "Emit no exit, runner, roll or management measurement when premium, availability, lifecycle or accounting fields are incomplete.",
  },
};

const expectedTruthProjectionSha256 = "1e0fd215c8b2f80e5ded634ede5c88352b7da462cc9a64537002946552c8eec8";
const expectedFieldTruthProjectionSha256 = "98e45c74e14f96031ed0882778dc541859ce2593b4c38dfe17bd2c041445dcd1";

const evidencePaths = {
  "EVIDENCE-CANDIDATE-INTERFACE": "doc/repro/pa-feitian-phase1-data-capability-2026-07-30/candidate_interface_audit_v1.json",
  "EVIDENCE-NATIVE-REGISTRATION": "doc/repro/pa-feitian-m6-native-source-registration-2026-07-30/native_source_registration_audit_v1.json",
  "EVIDENCE-OPTION-INPUT": "doc/repro/pa-feitian-m6-option-input-audit-2026-07-12/option_input_capability_audit_v1.json",
  "EVIDENCE-CONTINUOUS-PROVENANCE": "doc/repro/pa-feitian-m6-continuous-provenance-2026-07-11/continuous_provenance_manifest_v1.json",
};

const evidenceSchemaVersions = {
  "EVIDENCE-CANDIDATE-INTERFACE": "pa_feitian_phase1_candidate_interface_audit_v1",
  "EVIDENCE-NATIVE-REGISTRATION": "pa_feitian_m6_native_source_registration_audit_v1",
  "EVIDENCE-OPTION-INPUT": "pa_feitian_m6_option_input_capability_audit_v1",
  "EVIDENCE-CONTINUOUS-PROVENANCE": "pa_feitian_continuous_provenance_manifest_v1",
};

const evidenceMetadata = {
  "EVIDENCE-CANDIDATE-INTERFACE": {
    audit_as_of: "2026-07-30",
    role: "six-family interface schema, quality, timestamp and row-count evidence",
  },
  "EVIDENCE-NATIVE-REGISTRATION": {
    audit_as_of: "2026-07-30T15:45:00Z",
    role: "source-version, provenance and source-to-candidate accounting evidence",
  },
  "EVIDENCE-OPTION-INPUT": {
    audit_as_of: "2026-07-12",
    role: "option contract parsing, timestamp, availability and expiry-gap evidence",
  },
  "EVIDENCE-CONTINUOUS-PROVENANCE": {
    audit_as_of: "2026-07-11T00:00:00Z",
    role: "existing causal continuous-roll provenance boundary",
  },
};

function validatePackage(requirementsValue, receiptValue) {
  exactKeys(requirementsValue, ["fields", "issue_number", "schema_version", "upstream_binding"], "requirements");
  exactKeys(requirementsValue.upstream_binding, ["artifact_path", "issue_number", "pull_request_number", "raw_byte_length", "raw_byte_sha256", "revision"], "upstream binding");
  assert.equal(requirementsValue.schema_version, "pa_feitian_m6f_measurement_interface_requirements_v1");
  assert.equal(requirementsValue.issue_number, 79);
  assert.equal(requirementsValue.fields.length, expectedRequirements.length);
  for (let index = 0; index < expectedRequirements.length; index += 1) {
    const actual = requirementsValue.fields[index];
    exactKeys(actual, ["field_id", "node_id", "required_fields", "source_class", "upstream_semantics"], `requirement field ${index}`);
    exactKeys(actual.upstream_semantics, upstreamSemanticKeys, `requirement field ${index} upstream semantics`);
    assert.deepEqual({
      field_id: actual.field_id,
      node_id: actual.node_id,
      required_fields: actual.required_fields,
      source_class: actual.source_class,
    }, expectedRequirements[index]);
    assert.equal(sha256(canonicalCompact(actual.upstream_semantics)), expectedUpstreamSemanticHashes[index]);
  }
  assert.deepEqual(requirementsValue.upstream_binding, {
    artifact_path: "doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02/measurement_readiness_v1.json",
    issue_number: 77,
    pull_request_number: 78,
    raw_byte_length: 18581,
    raw_byte_sha256: "2ab764f77c90bf8ac979be7dde58a8d7352552d146d117cda3a8850c0b66e480",
    revision: "c10d4ccd462e7fb6369d6e1a25aeb7a5a622b2c2",
  });
  const upstreamBytes = bytes(upstreamPath);
  assert.equal(upstreamBytes.length, requirementsValue.upstream_binding.raw_byte_length);
  assert.equal(sha256(upstreamBytes), requirementsValue.upstream_binding.raw_byte_sha256);
  const upstreamArtifact = parseBytes(upstreamBytes);
  assertCanonicalText(upstreamArtifact, upstreamBytes.toString("utf8"), upstreamName);
  const upstreamProjection = upstreamArtifact.fields.map((field) => ({
    field_id: field.field_id,
    node_id: field.node_id,
    required_fields: field.required_fields,
    source_class: field.source_class,
    upstream_semantics: Object.fromEntries(upstreamSemanticKeys.map((key) => [key, field[key]])),
  }));
  assert.deepEqual(upstreamProjection, requirementsValue.fields);

  exactKeys(receiptValue, [
    "artifact_type",
    "binding_profiles",
    "capability_aggregate",
    "claim_boundary",
    "dependency_id",
    "deterministic_verifier",
    "evidence_cutoff_utc",
    "field_results",
    "handoff",
    "issue_number",
    "measurement_contract_binding",
    "public_safety_attestation",
    "receipt_created_at_utc",
    "schema_version",
    "source_evidence",
    "source_version",
  ], "receipt");
  assert.equal(receiptValue.schema_version, "pa_feitian_m6f_causal_measurement_capability_receipt_v1");
  assert.equal(receiptValue.artifact_type, "pa_feitian_m6f_causal_measurement_capability_receipt");
  assert.equal(receiptValue.dependency_id, "M6F-DATA-CAPABILITY-01");
  assert.equal(receiptValue.issue_number, 79);
  assert.deepEqual(receiptValue.measurement_contract_binding, requirementsValue.upstream_binding);
  const evidenceCutoff = strictUtcTimestamp(receiptValue.evidence_cutoff_utc, "evidence cutoff");
  const receiptCreatedAt = strictUtcTimestamp(receiptValue.receipt_created_at_utc, "receipt created at");
  assert.equal(evidenceCutoff <= receiptCreatedAt, true);
  assert.deepEqual(receiptValue.deterministic_verifier, {
    commands: [normalCommand, negativeCommand],
    network_access_required: false,
  });
  assert.deepEqual(receiptValue.public_safety_attestation, {
    assertions: [
      "no_raw_or_licensed_rows",
      "no_credentials_or_tokens",
      "no_private_or_local_paths",
      "no_provider_implementation",
      "no_reserve_identities",
      "no_outcomes_or_profitability",
      "no_m6r_episode_payloads",
    ],
    status: "pass",
  });
  assertPublicSafe({ requirements: requirementsValue, receipt: receiptValue });

  const sourceEvidence = new Map(receiptValue.source_evidence.map((row) => [row.evidence_id, row]));
  assert.equal(sourceEvidence.size, receiptValue.source_evidence.length, "duplicate source evidence id");
  assert.deepEqual([...sourceEvidence.keys()], Object.keys(evidencePaths));
  for (const [evidenceId, locator] of Object.entries(evidencePaths)) {
    const row = sourceEvidence.get(evidenceId);
    exactKeys(row, ["audit_as_of", "evidence_id", "evidence_schema_version", "locator", "raw_byte_length", "raw_byte_sha256", "repository_revision", "role"], `source evidence ${evidenceId}`);
    assert.equal(row.locator, locator);
    assert.equal(row.repository_revision, "7673394a9710036bf7ea9fb79d515b8a6beb0290");
    assert.deepEqual({ audit_as_of: row.audit_as_of, role: row.role }, evidenceMetadata[evidenceId]);
    const evidenceBytes = immutableFileBytes(row.repository_revision, locator);
    assert.equal(row.raw_byte_length, evidenceBytes.length);
    assert.equal(row.raw_byte_sha256, sha256(evidenceBytes));
    assert.match(row.raw_byte_sha256, /^[0-9a-f]{64}$/);
    assert.equal(row.evidence_schema_version, evidenceSchemaVersions[evidenceId]);
    assert.equal(parseBytes(evidenceBytes).schema_version, row.evidence_schema_version);
  }

  const evidenceRevision = "7673394a9710036bf7ea9fb79d515b8a6beb0290";
  const candidateAudit = parseBytes(immutableFileBytes(evidenceRevision, evidencePaths["EVIDENCE-CANDIDATE-INTERFACE"]));
  const nativeAudit = parseBytes(immutableFileBytes(evidenceRevision, evidencePaths["EVIDENCE-NATIVE-REGISTRATION"]));
  const optionAudit = parseBytes(immutableFileBytes(evidenceRevision, evidencePaths["EVIDENCE-OPTION-INPUT"]));
  const continuousAudit = parseBytes(immutableFileBytes(evidenceRevision, evidencePaths["EVIDENCE-CONTINUOUS-PROVENANCE"]));
  assert.equal(candidateAudit.source.access, "read_only");
  assert.equal(candidateAudit.source.matched_candidate_files, 31141);
  assert.equal(candidateAudit.source.inventory_sha256, receiptValue.source_version.candidate_interface_inventory_sha256);
  assert.equal(nativeAudit.source.access, "read_only");
  assert.equal(nativeAudit.source.source_file_count, receiptValue.source_version.source_file_count);
  assert.equal(nativeAudit.source.source_row_count, receiptValue.source_version.source_row_count);
  assert.equal(nativeAudit.source.complete_private_inventory_sha256, receiptValue.source_version.native_complete_private_inventory_sha256);
  assert.equal(nativeAudit.source.public_membership_sha256, receiptValue.source_version.native_public_membership_sha256);
  assert.equal(nativeAudit.verdict.status, "data_blocked");
  assert.equal(optionAudit.inventory.parsed_contract_set_count, 4935);
  assert.equal(optionAudit.inventory.parsed_contract_set_sha256, receiptValue.source_version.option_parsed_contract_set_sha256);
  assert.equal(optionAudit.availability_evidence.decision_time_availability, "unproven");
  assert.equal(optionAudit.availability_evidence.historical_acquisition_timestamp_present, false);
  assert.equal(optionAudit.availability_evidence.query_cutoff_present, false);
  assert.equal(optionAudit.availability_evidence.timezone_declared_in_bar_schema, false);

  const dailyUnderlying = candidateAudit.decision_surface.map((family) =>
    family.cadences.find((cadence) => cadence.cadence === "daily").interfaces.underlying,
  );
  const dailyOption = candidateAudit.decision_surface.map((family) =>
    family.cadences.find((cadence) => cadence.cadence === "daily").interfaces.option_premium,
  );
  const underlyingAccounting = {
    accepted_rows: sum(dailyUnderlying.map((row) => row.rows - row.ohlc_quality.violation_rows - row.timestamp_quality.null_rows)),
    duplicate_rows: sum(dailyUnderlying.map((row) => row.timestamp_quality.duplicate_rows)),
    observed_rows: sum(dailyUnderlying.map((row) => row.rows)),
    rejected_rows: sum(dailyUnderlying.map((row) => row.ohlc_quality.violation_rows + row.timestamp_quality.null_rows)),
  };
  const optionAccounting = {
    accepted_rows: sum(dailyOption.map((row) => row.rows - row.ohlc_quality.violation_rows - row.timestamp_quality.null_rows)),
    duplicate_rows: sum(dailyOption.map((row) => row.timestamp_quality.duplicate_rows)),
    observed_rows: sum(dailyOption.map((row) => row.rows)),
    rejected_rows: sum(dailyOption.map((row) => row.ohlc_quality.violation_rows + row.timestamp_quality.null_rows)),
  };

  const optionFindings = new Map(optionAudit.capability_findings.map((row) => [row.capability, row]));
  const dailyNativeCells = nativeAudit.cells.filter((cell) => cell.cadence === "daily");
  const admittedEvidence = [candidateAudit, nativeAudit, optionAudit, continuousAudit];
  const predicateResults = new Map([
    ["PRED-CANDIDATE-DAILY-UNDERLYING-ACCOUNTING", underlyingAccounting.observed_rows === 66720 && underlyingAccounting.accepted_rows === 66625 && underlyingAccounting.rejected_rows === 95 && underlyingAccounting.duplicate_rows === 0],
    ["PRED-CANDIDATE-DAILY-OPTION-ACCOUNTING", optionAccounting.observed_rows === 798548 && optionAccounting.accepted_rows === 416764 && optionAccounting.rejected_rows === 381784 && optionAccounting.duplicate_rows === 0],
    ["PRED-UNDERLYING-AVAILABLE-AT-ABSENT", !hasDeepKey(dailyUnderlying, "available_at") && !hasDeepKey(dailyNativeCells, "available_at")],
    ["PRED-NATIVE-DAILY-BAR-END-NORMALIZED-PROVIDER-LINEAGE-UNBOUND", dailyBarEndNormalizationWithoutEmbeddedProviderLineage(nativeAudit.cells)],
    ["PRED-NATIVE-PROVIDER-METADATA-ABSENT", nativeAudit.cells.every((cell) => cell.timestamp_semantics.embedded_provider_metadata_file_count === 0)],
    ["PRED-NATIVE-TIMEZONE-NAIVE", nativeAudit.cells.every((cell) => cell.timestamp_semantics.timezone_naive_storage_file_count === cell.source_file_count)],
    ["PRED-NATIVE-DATA-BLOCKED", nativeAudit.verdict.status === "data_blocked" && nativeAudit.verdict.approved_native_source_version_registered === false],
    ["PRED-CONTINUOUS-PROVENANCE-VERSIONED", continuousAudit.schema_version === "pa_feitian_continuous_provenance_manifest_v1" && Array.isArray(continuousAudit.bound_candidates)],
    ["PRED-UNDERLYING-ROW-DENOMINATORS-INCOMPLETE", dailyUnderlying.every((row) => !hasDeepKey(row, "requested_rows") && !hasDeepKey(row, "missing_rows") && !hasDeepKey(row, "late_rows"))],
    ["PRED-OPTION-DECISION-TIME-UNPROVEN", optionAudit.availability_evidence.decision_time_availability === "unproven" && optionAudit.availability_evidence.historical_acquisition_timestamp_present === false && optionAudit.availability_evidence.query_cutoff_present === false],
    ["PRED-OPTION-PERIOD-SEMANTICS-UNBOUND", optionAudit.availability_evidence.period_start_or_end_declared_in_bar_schema === false],
    ["PRED-OPTION-TIMEZONE-UNBOUND", optionAudit.availability_evidence.timezone_declared_in_bar_schema === false && optionAudit.inventory.bar_roots.every((root) => root.timezone_aware_files === 0)],
    ["PRED-OPTION-EXACT-EXPIRY-MISSING", optionFindings.get("exact_exchange_expiry_and_dte")?.state === "missing"],
    ["PRED-OPTION-CONTRACT-LINEAGE-UNVERIFIED", optionFindings.get("contract_and_maturity_lineage")?.state === "data_present_but_unverified" && optionAudit.decision.faithful_option_corpus === "blocked"],
    ["PRED-OPTION-PREMIUM-BASIS-UNBOUND", optionFindings.get("premium_bars_at_or_below_15_minutes")?.state === "data_present_but_unverified" && optionFindings.get("premium_bars_at_or_below_15_minutes")?.basis.includes("period semantics are absent")],
    ["PRED-OPTION-PROVIDER-LINEAGE-UNBOUND", optionAudit.availability_evidence.historical_acquisition_timestamp_present === false && optionAudit.availability_evidence.query_cutoff_present === false],
    ["PRED-OPTION-FILE-INVENTORY-ACCOUNTING", optionAudit.inventory.same_parsed_contract_set_across_bar_roots === true && optionAudit.inventory.bar_roots.every((root) => root.au_ag_prefixed_parquet_candidates === 5040 && root.parsed_option_files === 4935 && root.rejected_non_option_or_sidecar_files === 105)],
    ["PRED-OPTION-ROW-DENOMINATORS-INCOMPLETE", dailyOption.every((row) => !hasDeepKey(row, "requested_rows") && !hasDeepKey(row, "missing_rows") && !hasDeepKey(row, "late_rows"))],
    ["PRED-BOUND-EVIDENCE-HAS-NO-DERIVED-TRACE", optionFindings.get("formal_pa_feitian_dd_line")?.state === "missing" && admittedEvidence.every((artifact) => ["derived_trace_rows", "derived_trace", "decision_trace", "perception_trace", "geometry_available_at", "construction_version"].every((key) => !hasDeepKey(artifact, key)))],
    ["PRED-BOUND-EVIDENCE-HAS-NO-CHART-SOURCE-SELECTION", admittedEvidence.every((artifact) => !hasDeepKey(artifact, "chart_source"))],
    ["PRED-OPTION-CORPUS-BLOCKED", optionAudit.decision.faithful_option_corpus === "blocked" && optionAudit.decision.option_corpus_generation_warranted_now === false],
    ["PRED-DERIVED-ROW-DENOMINATOR-ABSENT", admittedEvidence.every((artifact) => !hasDeepKey(artifact, "derived_trace_rows"))],
    ["PRED-PREMIUM-ACTION-TRACE-ABSENT", admittedEvidence.every((artifact) => !hasDeepKey(artifact, "row_disposition") && !hasDeepKey(artifact, "management_action"))],
  ]);
  for (const [predicateId, result] of predicateResults) assert.equal(result, true, `${predicateId} failed`);

  const predicateEvidenceIds = {
    "PRED-CANDIDATE-DAILY-UNDERLYING-ACCOUNTING": ["EVIDENCE-CANDIDATE-INTERFACE"],
    "PRED-CANDIDATE-DAILY-OPTION-ACCOUNTING": ["EVIDENCE-CANDIDATE-INTERFACE"],
    "PRED-UNDERLYING-AVAILABLE-AT-ABSENT": ["EVIDENCE-CANDIDATE-INTERFACE", "EVIDENCE-NATIVE-REGISTRATION"],
    "PRED-NATIVE-DAILY-BAR-END-NORMALIZED-PROVIDER-LINEAGE-UNBOUND": ["EVIDENCE-NATIVE-REGISTRATION"],
    "PRED-NATIVE-PROVIDER-METADATA-ABSENT": ["EVIDENCE-NATIVE-REGISTRATION"],
    "PRED-NATIVE-TIMEZONE-NAIVE": ["EVIDENCE-NATIVE-REGISTRATION"],
    "PRED-NATIVE-DATA-BLOCKED": ["EVIDENCE-NATIVE-REGISTRATION"],
    "PRED-CONTINUOUS-PROVENANCE-VERSIONED": ["EVIDENCE-CONTINUOUS-PROVENANCE"],
    "PRED-UNDERLYING-ROW-DENOMINATORS-INCOMPLETE": ["EVIDENCE-CANDIDATE-INTERFACE"],
    "PRED-OPTION-DECISION-TIME-UNPROVEN": ["EVIDENCE-OPTION-INPUT"],
    "PRED-OPTION-PERIOD-SEMANTICS-UNBOUND": ["EVIDENCE-OPTION-INPUT"],
    "PRED-OPTION-TIMEZONE-UNBOUND": ["EVIDENCE-OPTION-INPUT"],
    "PRED-OPTION-EXACT-EXPIRY-MISSING": ["EVIDENCE-OPTION-INPUT"],
    "PRED-OPTION-CONTRACT-LINEAGE-UNVERIFIED": ["EVIDENCE-OPTION-INPUT"],
    "PRED-OPTION-PREMIUM-BASIS-UNBOUND": ["EVIDENCE-OPTION-INPUT"],
    "PRED-OPTION-PROVIDER-LINEAGE-UNBOUND": ["EVIDENCE-OPTION-INPUT"],
    "PRED-OPTION-FILE-INVENTORY-ACCOUNTING": ["EVIDENCE-OPTION-INPUT"],
    "PRED-OPTION-ROW-DENOMINATORS-INCOMPLETE": ["EVIDENCE-CANDIDATE-INTERFACE"],
    "PRED-BOUND-EVIDENCE-HAS-NO-DERIVED-TRACE": Object.keys(evidencePaths),
    "PRED-BOUND-EVIDENCE-HAS-NO-CHART-SOURCE-SELECTION": Object.keys(evidencePaths),
    "PRED-OPTION-CORPUS-BLOCKED": ["EVIDENCE-OPTION-INPUT"],
    "PRED-DERIVED-ROW-DENOMINATOR-ABSENT": Object.keys(evidencePaths),
    "PRED-PREMIUM-ACTION-TRACE-ABSENT": Object.keys(evidencePaths),
  };
  assert.deepEqual(Object.keys(predicateEvidenceIds).sort(), [...predicateResults.keys()].sort());

  const profiles = new Map(receiptValue.binding_profiles.map((profile) => [profile.profile_id, profile]));
  assert.deepEqual([...profiles.keys()], [
    "BP-UNDERLYING-DAILY",
    "BP-OPTION-CONTRACT",
    "BP-OPTION-DAILY",
    "BP-DERIVED-TRACE",
    "BP-DERIVED-TRACE-CONDITIONAL-CHART",
    "BP-PREMIUM-LIFECYCLE",
  ]);
  assert.deepEqual(
    Object.fromEntries(Object.entries(underlyingAccounting).map(([key, value]) => [key, profiles.get("BP-UNDERLYING-DAILY").row_accounting[key]])),
    underlyingAccounting,
  );
  assert.deepEqual(
    Object.fromEntries(Object.entries(optionAccounting).map(([key, value]) => [key, profiles.get("BP-OPTION-DAILY").row_accounting[key]])),
    optionAccounting,
  );
  assert.deepEqual(profiles.get("BP-OPTION-CONTRACT").row_accounting.inventory_units, {
    accepted_parsed_files: 4935,
    candidate_files: 5040,
    rejected_files: 105,
  });
  assert.deepEqual(profiles.get("BP-PREMIUM-LIFECYCLE").row_accounting.support_surface, {
    daily_option_ohlc_quality: {
      duplicate_timestamp_rows: optionAccounting.duplicate_rows,
      observed_rows: optionAccounting.observed_rows,
      quality_passing_rows: optionAccounting.accepted_rows,
      quality_rejected_rows: optionAccounting.rejected_rows,
    },
  });

  for (const profile of profiles.values()) {
    exactKeys(profile, [...semanticKeys, "deterministic_replay_rule", "fail_closed_behavior", "profile_id", "profile_result", "row_accounting"], `profile ${profile.profile_id}`);
    assert.equal(profile.profile_result, "fail");
    assert.match(profile.row_accounting.accounting_status, /^fail_/);
    assert.equal(profile.deterministic_replay_rule.trim().length > 0, true);
    assert.equal(profile.fail_closed_behavior.trim().length > 0, true);
    assert.deepEqual({
      deterministic_replay_rule: profile.deterministic_replay_rule,
      fail_closed_behavior: profile.fail_closed_behavior,
    }, expectedOperationalSemantics[profile.profile_id]);
    for (const key of semanticKeys) {
      exactKeys(profile[key], ["evidence_ids", "evidence_predicate_ids", "statement", "status"], `${profile.profile_id}.${key}`);
      assert.ok(["pass", "fail", "not_applicable"].includes(profile[key].status));
      assert.equal(profile[key].status, expectedStatusMatrix[profile.profile_id][key]);
      assert.equal(typeof profile[key].statement, "string");
      for (const evidenceId of profile[key].evidence_ids) assert.ok(sourceEvidence.has(evidenceId));
      for (const predicateId of profile[key].evidence_predicate_ids) {
        assert.equal(predicateResults.get(predicateId), true, `${profile.profile_id}.${key}.${predicateId}`);
        for (const evidenceId of predicateEvidenceIds[predicateId]) {
          assert.equal(profile[key].evidence_ids.includes(evidenceId), true, `${profile.profile_id}.${key} omits ${evidenceId} required by ${predicateId}`);
        }
      }
      if (profile[key].status === "pass") {
        assert.ok(profile[key].evidence_ids.length > 0, `${profile.profile_id}.${key} pass lacks evidence`);
        assert.ok(profile[key].evidence_predicate_ids.length > 0, `${profile.profile_id}.${key} pass lacks predicates`);
      }
    }
    assert.equal(semanticKeys.some((key) => profile[key].status === "fail"), true);
    for (const key of ["requested_rows", "accepted_rows", "missing_rows", "duplicate_rows", "late_rows", "rejected_rows", "observed_rows"]) {
      assert.equal(Object.hasOwn(profile.row_accounting, key), true);
      const count = profile.row_accounting[key];
      assert.equal(count === null || (Number.isSafeInteger(count) && count >= 0), true, `${profile.profile_id}.${key} must be a nonnegative integer or null`);
    }
    for (const predicateId of profile.row_accounting.evidence_predicate_ids) assert.equal(predicateResults.get(predicateId), true, `${profile.profile_id}.row_accounting.${predicateId}`);
    const rowKeys = ["accepted_rows", "accounting_status", "duplicate_rows", "evidence_predicate_ids", "late_rows", "missing_rows", "observed_rows", "rejected_rows", "requested_rows", "scope"];
    if (profile.profile_id === "BP-OPTION-CONTRACT") rowKeys.push("inventory_units");
    if (profile.profile_id === "BP-PREMIUM-LIFECYCLE") rowKeys.push("support_surface");
    exactKeys(profile.row_accounting, rowKeys, `${profile.profile_id}.row_accounting`);
  }
  assert.equal(underlyingAccounting.observed_rows, underlyingAccounting.accepted_rows + underlyingAccounting.rejected_rows);
  assert.equal(optionAccounting.observed_rows, optionAccounting.accepted_rows + optionAccounting.rejected_rows);
  assert.deepEqual(
    ["requested_rows", "missing_rows", "late_rows"].map((key) => profiles.get("BP-UNDERLYING-DAILY").row_accounting[key]),
    [null, null, null],
  );
  assert.deepEqual(
    ["requested_rows", "missing_rows", "late_rows"].map((key) => profiles.get("BP-OPTION-DAILY").row_accounting[key]),
    [null, null, null],
  );
  for (const profileId of ["BP-OPTION-CONTRACT", "BP-DERIVED-TRACE", "BP-DERIVED-TRACE-CONDITIONAL-CHART", "BP-PREMIUM-LIFECYCLE"]) {
    assert.deepEqual(
      ["requested_rows", "accepted_rows", "missing_rows", "duplicate_rows", "late_rows", "rejected_rows", "observed_rows"].map((key) => profiles.get(profileId).row_accounting[key]),
      [null, null, null, null, null, null, null],
      `${profileId} has no exact interface-level disposition denominator`,
    );
  }
  const truthProjection = receiptValue.binding_profiles.map((profile) => ({
    categories: Object.fromEntries(semanticKeys.map((key) => [key, {
      evidence_ids: profile[key].evidence_ids,
      evidence_predicate_ids: profile[key].evidence_predicate_ids,
      statement_sha256: sha256(profile[key].statement),
      status: profile[key].status,
    }])),
    deterministic_replay_rule_sha256: sha256(profile.deterministic_replay_rule),
    fail_closed_behavior_sha256: sha256(profile.fail_closed_behavior),
    profile_id: profile.profile_id,
    row_accounting: {
      accounting_status: profile.row_accounting.accounting_status,
      evidence_predicate_ids: profile.row_accounting.evidence_predicate_ids,
      scope_sha256: sha256(profile.row_accounting.scope),
    },
  }));
  assert.equal(sha256(canonicalCompact(truthProjection)), expectedTruthProjectionSha256);

  assert.equal(receiptValue.field_results.length, 10);
  for (let index = 0; index < expectedRequirements.length; index += 1) {
    const expected = expectedRequirements[index];
    const actual = receiptValue.field_results[index];
    exactKeys(actual, ["binding_profile_id", "evidence_bindings", "failure_reasons", "field_id", "field_result", "node_id", "required_fields", "semantic_answers", "source_class", "upstream_semantics"], `field ${index}`);
    assert.deepEqual(
      {
        field_id: actual.field_id,
        node_id: actual.node_id,
        required_fields: actual.required_fields,
        source_class: actual.source_class,
      },
      expected,
    );
    assert.equal(actual.binding_profile_id, expectedFieldProfileIds[index], `${actual.field_id} binding profile`);
    exactKeys(actual.upstream_semantics, upstreamSemanticKeys, `field ${index} upstream semantics`);
    assert.deepEqual(actual.upstream_semantics, requirementsValue.fields[index].upstream_semantics);
    assert.equal(sha256(canonicalCompact(actual.upstream_semantics)), expectedUpstreamSemanticHashes[index]);
    assert.ok(profiles.has(actual.binding_profile_id));
    const profile = profiles.get(actual.binding_profile_id);
    assert.equal(actual.field_result, profile.profile_result);
    const profilePredicateIds = [
      ...semanticKeys.flatMap((key) => profile[key].evidence_predicate_ids),
      ...profile.row_accounting.evidence_predicate_ids,
    ];
    const profileEvidenceIds = [...new Set([
      ...semanticKeys.flatMap((key) => profile[key].evidence_ids),
      ...profilePredicateIds.flatMap((predicateId) => predicateEvidenceIds[predicateId]),
    ])].sort();
    assert.deepEqual(actual.evidence_bindings, receiptValue.source_evidence.filter((row) => profileEvidenceIds.includes(row.evidence_id)));
    assert.deepEqual(actual.semantic_answers, {
      available_at_and_decision_cutoff: profile.available_at_and_decision_cutoff,
      bar_open_end_and_finalization: profile.bar_open_end_and_finalization,
      deterministic_replay_rule: profile.deterministic_replay_rule,
      exchange_timezone_session_and_trading_date: profile.exchange_timezone_session_and_trading_date,
      expiry_and_roll_mapping: profile.expiry_and_roll_mapping,
      fail_closed_behavior: profile.fail_closed_behavior,
      option_lifecycle_and_asof_selection: profile.option_lifecycle_and_asof_selection,
      premium_price_basis: profile.premium_price_basis,
      provider_source_version_and_provenance: profile.provider_source_version_and_provenance,
      row_accounting: profile.row_accounting,
    });
    assert.equal(Array.isArray(actual.failure_reasons) && actual.failure_reasons.length > 0, true);
    assert.equal(actual.failure_reasons.every((reason) => typeof reason === "string" && reason.length > 0), true);
  }
  const fieldTruthProjection = receiptValue.field_results.map((field) => ({
    binding_profile_id: field.binding_profile_id,
    failure_reasons: field.failure_reasons,
    field_id: field.field_id,
  }));
  assert.equal(sha256(canonicalCompact(fieldTruthProjection)), expectedFieldTruthProjectionSha256);
  const failed = receiptValue.field_results.filter((field) => field.field_result === "fail").map((field) => field.field_id);
  const passed = receiptValue.field_results.filter((field) => field.field_result === "pass").map((field) => field.field_id);
  assert.deepEqual(receiptValue.capability_aggregate, {
    capability_result: failed.length === 0 ? "pass" : "fail",
    fail_count: failed.length,
    failed_field_ids: failed,
    field_count: receiptValue.field_results.length,
    pass_count: passed.length,
  });
  exactKeys(receiptValue.capability_aggregate, ["capability_result", "fail_count", "failed_field_ids", "field_count", "pass_count"], "capability aggregate");
  assert.deepEqual(receiptValue.source_version, {
    candidate_interface_inventory_sha256: "sha256:9bbd6c94ca9bf8228c76cd2078513b82655990c88084297d710cd83c2f33ec8f",
    native_complete_private_inventory_sha256: "sha256:13e00e03007e47525bdeac9e5fddb81d222375d7921557b9b1569fe2bd17b819",
    native_public_membership_sha256: "sha256:2cdcd4e6ef456885d59fd89125099e3f1ceb0c27b82a849db45e298f2b1e310d",
    option_parsed_contract_set_sha256: "sha256:1763a5d704c4a03ce7a930db00cdbfd784edbeed86c23803c77c651e7e8408ec",
    provider_identity_publication: "not_required_and_not_published",
    provider_semantics_status: "unbound",
    public_alias: "external://quant-data/",
    source_file_count: 978,
    source_row_count: 2702545,
  });
  assert.deepEqual(receiptValue.handoff, {
    artifact_locator: `${packageLocator}/${receiptName}`,
    dependency_id: "M6F-DATA-CAPABILITY-01",
    pi_acceptance_required: true,
    strategy_may_consume_only_public_receipt: true,
    strategy_recomputation_required: true,
  });
  exactKeys(receiptValue.claim_boundary, ["backtest_or_experiment_authorized", "execution_authorized", "m6r_episode_payloads_included", "m7_authorized", "outcomes_or_profitability_inspected", "provider_implementation_included", "raw_or_licensed_rows_included", "reserve_identities_included", "strategy_parameters_selected"], "claim boundary");
  for (const [key, value] of Object.entries(receiptValue.claim_boundary)) {
    assert.equal(value, false, `claim boundary ${key} must remain false`);
  }
}

assertCanonicalText(requirements, bytes(requirementsPath).toString("utf8"), requirementsName);
assertCanonicalText(receipt, bytes(receiptPath).toString("utf8"), receiptName);
validatePackage(requirements, receipt);

function validateOuterArtifacts(manifestValue, manifestTextValue, readmeTextValue) {
  assertCanonicalText(manifestValue, manifestTextValue, manifestName);
  exactKeys(manifestValue, ["issue_number", "payloads", "schema_version"], "manifest");
  assert.equal(manifestValue.schema_version, "pa_feitian_m6f_causal_measurement_capability_manifest_v1");
  assert.equal(manifestValue.issue_number, 79);
  assert.deepEqual(manifestValue.payloads.map((entry) => entry.path), [upstreamName, requirementsName, receiptName, verifierName]);
  for (const entry of manifestValue.payloads) {
    exactKeys(entry, ["byte_length", "path", "raw_byte_sha256"], `manifest entry ${entry.path}`);
    const content = bytes(join(here, entry.path));
    assert.equal(entry.byte_length, content.length);
    assert.equal(entry.raw_byte_sha256, sha256(content));
  }
  const requiredReadmeBindings = [
    "M6F-DATA-CAPABILITY-01",
    "c10d4ccd462e7fb6369d6e1a25aeb7a5a622b2c2",
    "doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02/measurement_readiness_v1.json",
    "upstream_measurement_readiness_v2.json",
    "18,581 UTF-8 bytes",
    "2ab764f77c90bf8ac979be7dde58a8d7352552d146d117cda3a8850c0b66e480",
    "`capability_result: fail` — 0 pass, 10 fail.",
    `${packageLocator}/${receiptName}`,
    `artifact_manifest_sha256: ${sha256(Buffer.from(manifestTextValue, "utf8"))}`,
    sha256(bytes(receiptPath)),
    normalCommand,
    negativeCommand,
    "After merge and PI provenance acceptance",
    "Strategy may consume only the public",
    "Strategy must independently recompute",
  ];
  for (const binding of requiredReadmeBindings) {
    assert.equal(readmeTextValue.includes(binding), true, `README missing binding: ${binding}`);
  }
  assertPublicSafe({ manifest: manifestValue, readme: readmeTextValue, receipt, requirements, upstream: parse(upstreamPath) });
}
assert.deepEqual(readdirSync(here).sort(), [manifestName, readmeName, receiptName, requirementsName, upstreamName, verifierName].sort());
const readmeText = bytes(join(here, readmeName)).toString("utf8");
const manifestText = bytes(manifestPath).toString("utf8");
validateOuterArtifacts(manifest, manifestText, readmeText);

if (process.argv.includes("--negative")) {
  const mutateCategory = (value, profileId, key, mutate) => {
    const profile = value.binding_profiles.find((row) => row.profile_id === profileId);
    mutate(profile[key]);
    for (const field of value.field_results.filter((row) => row.binding_profile_id === profileId)) mutate(field.semantic_answers[key]);
  };
  const mutateRowAccounting = (value, profileId, mutate) => {
    const profile = value.binding_profiles.find((row) => row.profile_id === profileId);
    mutate(profile.row_accounting);
    for (const field of value.field_results.filter((row) => row.binding_profile_id === profileId)) mutate(field.semantic_answers.row_accounting);
  };
  const mutations = [
    ["missing_field", (value) => { value.field_results.pop(); }],
    ["extra_field", (value) => { value.field_results.push(structuredClone(value.field_results[0])); }],
    ["swapped_node", (value) => { [value.field_results[0].node_id, value.field_results[1].node_id] = [value.field_results[1].node_id, value.field_results[0].node_id]; }],
    ["false_aggregate", (value) => { value.capability_aggregate.pass_count = 1; }],
    ["missing_semantic_category", (value) => { delete value.field_results[0].semantic_answers.premium_price_basis; }],
    ["missing_row_disposition", (value) => { delete value.field_results[0].semantic_answers.row_accounting.requested_rows; }],
    ["fake_evidence_hash", (value) => { value.source_evidence[0].raw_byte_sha256 = "0".repeat(64); }],
    ["fake_evidence_locator", (value) => { value.source_evidence[0].locator = "doc/repro/fake.json"; }],
    ["false_local_pass", (value) => mutateCategory(value, "BP-OPTION-DAILY", "premium_price_basis", (category) => { category.status = "pass"; })],
    ["false_pass_empty_evidence", (value) => mutateCategory(value, "BP-OPTION-DAILY", "premium_price_basis", (category) => { category.status = "pass"; category.evidence_ids = []; category.evidence_predicate_ids = []; })],
    ["false_not_applicable", (value) => mutateCategory(value, "BP-OPTION-DAILY", "premium_price_basis", (category) => { category.status = "not_applicable"; })],
    ["empty_evidence", (value) => mutateCategory(value, "BP-OPTION-DAILY", "available_at_and_decision_cutoff", (category) => { category.evidence_ids = []; })],
    ["inadmissible_evidence", (value) => mutateCategory(value, "BP-OPTION-DAILY", "available_at_and_decision_cutoff", (category) => { category.evidence_ids = ["EVIDENCE-CONTINUOUS-PROVENANCE"]; })],
    ["empty_evidence_predicates", (value) => mutateCategory(value, "BP-OPTION-DAILY", "available_at_and_decision_cutoff", (category) => { category.evidence_predicate_ids = []; })],
    ["contradictory_prose", (value) => mutateCategory(value, "BP-OPTION-DAILY", "available_at_and_decision_cutoff", (category) => { category.statement = "Exact causal availability is proven for every row."; })],
    ["private_path_leak", (value) => { value.field_results[0].failure_reasons[0] = "/srv/provider/private-row-store"; }],
    ["single_slash_file_uri_leak", (value) => { value.field_results[0].failure_reasons[0] = "file:/srv/provider/private-row-store"; }],
    ["triple_slash_file_uri_leak", (value) => { value.field_results[0].failure_reasons[0] = "file:///srv/provider/private-row-store"; }],
    ["credential_leak", (value) => { value.field_results[0].failure_reasons[0] = "AKIA1234567890ABCDEF"; }],
    ["basic_authorization_leak", (value) => { value.field_results[0].failure_reasons[0] = "Authorization: Basic Zm9vOmJhcg=="; }],
    ["email_identity_leak", (value) => { value.field_results[0].failure_reasons[0] = "operator@example.com"; }],
    ["raw_ohlcv_row_leak", (value) => { value.field_results[0].failure_reasons[0] = "2026-01-02,1,2,0.5,1.5,100"; }],
    ["raw_ohlc_row_without_volume_leak", (value) => { value.field_results[0].failure_reasons[0] = "2026-01-02,1,2,0.5,1.5"; }],
    ["json_ohlc_row_leak", (value) => { value.field_results[0].failure_reasons[0] = '{"low":0.5,"close":1.5,"open":1,"high":2}'; }],
    ["provider_implementation_leak", (value) => { value.field_results[0].failure_reasons[0] = "requests.get(provider_url)"; }],
    ["provider_import_leak", (value) => { value.field_results[0].failure_reasons[0] = "from akshare import futures_zh_daily_sina"; }],
    ["contract_identity_leak", (value) => { value.field_results[0].failure_reasons[0] = "SHFE.au2606"; }],
    ["cffex_contract_identity_leak", (value) => { value.field_results[0].failure_reasons[0] = "CFFEX.IF2606"; }],
    ["m6r_identity_leak", (value) => { value.field_results[0].failure_reasons[0] = "M6R-0123456789abcdefabcd"; }],
    ["claim_expansion", (value) => { value.claim_boundary.execution_authorized = true; }],
    ["field_profile_rebind", (value) => { value.field_results[2].binding_profile_id = "BP-DERIVED-TRACE"; }],
    ["conditional_chart_profile_rebind", (value) => { value.field_results[4].binding_profile_id = "BP-DERIVED-TRACE"; }],
    ["derived_row_evidence_omission", (value) => { value.field_results[3].evidence_bindings = value.field_results[3].evidence_bindings.filter((row) => row.evidence_id !== "EVIDENCE-CANDIDATE-INTERFACE"); }],
    ["negative_row_count", (value) => mutateRowAccounting(value, "BP-UNDERLYING-DAILY", (row) => { row.requested_rows = -1; })],
    ["string_row_count", (value) => mutateRowAccounting(value, "BP-UNDERLYING-DAILY", (row) => { row.missing_rows = "forged"; })],
    ["boolean_row_count", (value) => mutateRowAccounting(value, "BP-UNDERLYING-DAILY", (row) => { row.late_rows = true; })],
    ["row_reconciliation_forgery", (value) => mutateRowAccounting(value, "BP-OPTION-DAILY", (row) => { row.accepted_rows += 1; })],
    ["premium_action_acceptance_forgery", (value) => mutateRowAccounting(value, "BP-PREMIUM-LIFECYCLE", (row) => { row.accepted_rows = row.support_surface.daily_option_ohlc_quality.quality_passing_rows; })],
    ["calendar_invalid_timestamp", (value) => { value.receipt_created_at_utc = "2026-02-30T08:21:20Z"; }],
    ["evidence_role_forgery", (value) => { value.source_evidence[0].role = "different semantic evidence"; }],
    ["source_alias_forgery", (value) => { value.source_version.public_alias = "external://forged/"; }],
    ["handoff_locator_forgery", (value) => { value.handoff.artifact_locator = "doc/repro/forged.json"; }],
    ["empty_deterministic_replay_rule", (value) => {
      value.binding_profiles[0].deterministic_replay_rule = "";
      value.field_results[0].semantic_answers.deterministic_replay_rule = "";
    }],
    ["contradictory_fail_open_behavior", (value) => {
      const forged = "Proceed with downstream contract selection when inputs are incomplete.";
      value.binding_profiles[0].fail_closed_behavior = forged;
      value.field_results[0].semantic_answers.fail_closed_behavior = forged;
    }],
  ];
  for (const [name, mutate] of mutations) {
    const damaged = structuredClone(receipt);
    mutate(damaged);
    assert.throws(() => validatePackage(requirements, damaged), name);
  }
  const damagedRequirements = structuredClone(requirements);
  damagedRequirements.fields[0].required_fields.pop();
  assert.throws(() => validatePackage(damagedRequirements, receipt));
  const damagedUpstreamSemantics = structuredClone(requirements);
  damagedUpstreamSemantics.fields[0].upstream_semantics.bar_open_and_end_semantics = "stale semantics";
  assert.throws(() => validatePackage(damagedUpstreamSemantics, receipt));
  assert.throws(() => assertCanonicalText(receipt, `${canonicalPretty(receipt)} `, "damaged receipt"));
  const noncanonicalManifestText = `${canonicalPretty(manifest)} `;
  const manifestHash = sha256(Buffer.from(manifestText, "utf8"));
  const noncanonicalManifestHash = sha256(Buffer.from(noncanonicalManifestText, "utf8"));
  const refreshedReadme = readmeText.replace(manifestHash, noncanonicalManifestHash);
  assert.throws(() => validateOuterArtifacts(manifest, noncanonicalManifestText, refreshedReadme));
  assert.throws(() => validateOuterArtifacts(manifest, manifestText, readmeText.replace(sha256(bytes(receiptPath)), "0".repeat(64))));
  assert.throws(() => validateOuterArtifacts(manifest, manifestText, readmeText.replaceAll(normalCommand, "node forged-verifier.mjs")));
  assert.throws(() => validateOuterArtifacts(manifest, manifestText, `${readmeText}\n/srv/provider/private-row-store\n`));
  assert.equal(dailyBarEndNormalizationWithoutEmbeddedProviderLineage([
    { cadence: "daily", source_file_count: 2, timestamp_semantics: { embedded_provider_metadata_file_count: 0, provider_bar_end_semantics_bound_file_count: 2 } },
    { cadence: "daily", source_file_count: 2, timestamp_semantics: { embedded_provider_metadata_file_count: 0, provider_bar_end_semantics_bound_file_count: 1 } },
    { cadence: "15m", source_file_count: 1, timestamp_semantics: { embedded_provider_metadata_file_count: 0, provider_bar_end_semantics_bound_file_count: 0 } },
  ]), false);
  console.log(JSON.stringify({ negative_mutations: mutations.length + 8, ok: true }));
}

console.log(JSON.stringify({ capability_result: receipt.capability_aggregate.capability_result, fail: 10, fields: 10, ok: true, pass: 0 }));
