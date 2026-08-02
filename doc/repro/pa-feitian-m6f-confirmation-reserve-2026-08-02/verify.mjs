#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DIR = dirname(fileURLToPath(import.meta.url));
const RECEIPT_PATH = "confirmation_reserve_custody_receipt_v2.json";
const ATTESTATION_PATH = "independent_non_overlap_verification_attestation_v1.json";
const MANIFEST_PATH = "artifact_manifest_v1.json";
const VERIFIER_PATH = "verify.mjs";
const PACKAGE_FILES = [ATTESTATION_PATH, MANIFEST_PATH, RECEIPT_PATH, VERIFIER_PATH].sort();
const CANONICAL_INVOCATION = 'env -u NODE_OPTIONS node --permission --allow-fs-read="$ABS_PACKAGE" "$ABS_PACKAGE/verify.mjs" [--negative]';

const EXPECTED_ASSERTIONS = {
  all_m6r_episode_identities_excluded: true,
  all_recovery_and_discovery_artifacts_byte_bound: true,
  derivative_overlap_and_near_duplicate_promotion_impossible: true,
  identity_material_contains_no_outcome_fields: true,
  no_plaintext_identity_manifest_present: true,
  reserve_and_excluded_source_partition_complete: true,
  reserve_family_intersection_empty: true,
  sealed_payloads_canonical_and_log_bound: true,
  source_bytes_and_required_schema_revalidated: true,
  whole_family_cross_expiry_quarantine_enforced: true,
};

const EXPECTED_RECEIPT = {
  access_log_chain_head_sha256: "1a31f1b29fa4a234a68808da1e8a3bfc0ac18991566a31cc90b77fc18f0eef00",
  access_log_locator: "custody://data-owner/M6F-CONFIRMATION-RESERVE-V1/append-only-access-log-v1.jsonl",
  custodian_role: "data_owner",
  eligibility_rule_sha256: "0a9cab614107bcf9bdb23bcba4e531cd8cb8a00c6b0396870bcae6976b90b914",
  exclusion_registry_envelope_sha256: "1e656868bb861927851d349926fb4b197f5735076ac71ff7e3cfeaacb5161949",
  exclusion_registry_plaintext_sha256: "6dc1f26c52d35068d42aceff225fae991f0d8743504addd06992123ef924a4db",
  exclusion_set_sha256: "5bbdfb22ff9b383e9623227835ca56493b7e22a1b5fb51944ef3f185bd19bf08",
  identity_manifest_envelope_sha256: "ef18a08921e250ffb02018edece1338ba1079c9eac29532f271c37ffd4c6686c",
  identity_manifest_plaintext_sha256: "a0f7733b2bbd8a28005b3cc35dab341080d9353a49fd610da9a5bf6e404ef807",
  release_authority_role: "pi",
  required_releasing_issue_type: "pi_approved_preregistration_design",
  reserve_id: "M6F-CONFIRMATION-RESERVE-V1",
  schema_version: "pa_feitian_m6f_confirmation_reserve_custody_receipt_v2",
  sealed_at: "2026-08-02T09:23:03Z",
};

const EXPECTED_ATTESTATION = {
  access_log_chain_head_sha256: EXPECTED_RECEIPT.access_log_chain_head_sha256,
  assertion_count: 10,
  assertions: EXPECTED_ASSERTIONS,
  custodian_role: EXPECTED_RECEIPT.custodian_role,
  custody_receipt_path: RECEIPT_PATH,
  custody_receipt_raw_byte_sha256: "1a4baa1a72d5c7090397f2619429308679d9efa0d25c38dc50207c01da072610",
  no_strategy_access_or_release_before_verified_at: true,
  overall_result: "pass",
  reserve_id: EXPECTED_RECEIPT.reserve_id,
  reserve_nonempty: true,
  schema_version: "pa_feitian_m6f_public_non_overlap_verification_attestation_v1",
  verification_report_envelope_sha256: "f6638457312d8bb6852363527f068ae431f0f6d16d48ffb95f6fa2169e24b503",
  verification_report_plaintext_sha256: "c25c5e34c6e47c2d8e0f448c7276d8677409c0d2836081e6ea6cd7d3a8c886e4",
  verification_report_schema_version: "pa_feitian_m6f_private_non_overlap_verification_v3",
  verified_at: "2026-08-02T11:48:50Z",
  verifier_independent_from_custodian: true,
  verifier_role: "independent_data_verifier",
};

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalValue(value[key])]),
    );
  }
  return value;
}

function canonicalBytes(value) {
  return Buffer.from(`${JSON.stringify(canonicalValue(value))}\n`, "utf8");
}

function sameValue(actual, expected) {
  return JSON.stringify(canonicalValue(actual)) === JSON.stringify(canonicalValue(expected));
}

function validateRuntimeBoundary() {
  const expectedArgs = ["--permission", `--allow-fs-read=${DIR}`].sort();
  invariant(typeof process.permission === "object", "runtime: Node permission mode is required");
  invariant(
    sameValue([...process.execArgv].sort(), expectedArgs),
    "runtime: use only --permission and the exact public package read grant",
  );
  const permissions = process.permission;
  invariant(permissions.has("fs.read", DIR), "runtime: public package read grant missing");
  invariant(!permissions.has("fs.read", dirname(DIR)), "runtime: parent-directory read must be denied");
  invariant(!permissions.has("fs.read", "/"), "runtime: root read must be denied");
  invariant(!permissions.has("fs.write", DIR), "runtime: writes must be denied");
  for (const scope of ["addons", "child", "wasi", "worker"]) {
    invariant(!permissions.has(scope), `runtime: ${scope} capability must be denied`);
  }
}

function parseCanonical(raw, label) {
  const text = raw.toString("utf8");
  invariant(Buffer.from(text, "utf8").equals(raw), `${label}: invalid UTF-8`);
  let value;
  try {
    value = JSON.parse(text);
  } catch (error) {
    throw new Error(`${label}: invalid JSON: ${error.message}`);
  }
  invariant(raw.equals(canonicalBytes(value)), `${label}: bytes are not canonical JSON plus one LF`);
  return value;
}

function exactKeys(value, expectedKeys, label) {
  invariant(value && typeof value === "object" && !Array.isArray(value), `${label}: expected object`);
  invariant(
    sameValue(Object.keys(value).sort(), [...expectedKeys].sort()),
    `${label}: unexpected key set`,
  );
}

function strictUtc(value, label) {
  invariant(typeof value === "string", `${label}: expected string`);
  invariant(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value), `${label}: expected strict UTC seconds`);
  const parsed = new Date(value);
  invariant(!Number.isNaN(parsed.valueOf()), `${label}: invalid calendar timestamp`);
  invariant(parsed.toISOString().replace(".000Z", "Z") === value, `${label}: non-round-tripping timestamp`);
  return parsed.valueOf();
}

function hash64(value, label) {
  invariant(typeof value === "string" && /^[0-9a-f]{64}$/.test(value), `${label}: expected lowercase SHA-256`);
}

const FORBIDDEN_DATA_KEYS = new Set([
  "access_token",
  "api_key",
  "authorization",
  "close",
  "contract_identity",
  "episode_id",
  "ev",
  "exchange",
  "family",
  "filesystem_path",
  "high",
  "horizon",
  "instrument",
  "instrument_family",
  "local_path",
  "loss",
  "low",
  "metric",
  "ohlc",
  "open",
  "open_interest",
  "outcome",
  "outcomes",
  "password",
  "pnl",
  "product",
  "profit",
  "provider_code",
  "provider_implementation",
  "raw_rows",
  "relative_path",
  "reserve_identities",
  "return",
  "returns",
  "rows",
  "sample_members",
  "sample_size",
  "secret",
  "source_identities",
  "threshold",
  "turnover",
  "volume",
  "win_rate",
]);

const PUBLIC_SAFE_KEYS = new Set([
  ...Object.keys(EXPECTED_RECEIPT),
  ...Object.keys(EXPECTED_ATTESTATION),
  ...Object.keys(EXPECTED_ASSERTIONS),
  "byte_length",
  "dependency_id",
  "invocation",
  "issue_number",
  "path",
  "payloads",
  "raw_byte_sha256",
]);

function normalizedKey(key) {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function forbiddenAliasedKey(key) {
  if (PUBLIC_SAFE_KEYS.has(key)) return false;
  const normalized = normalizedKey(key);
  const collapsed = normalized.replaceAll("_", "");
  return /(?:accesstoken|apikey|clientsecret|contractid|episodeid|exchangecode|familyname|instrumentid|privatekey|productid|provideradapter|refreshtoken|sourcealias)/.test(collapsed) || [
    /(?:^|_)(?:access_token|api_key|authorization|client_secret|credential|password|private_key|refresh_token|secret)(?:_|$)/,
    /(?:^|_)(?:contract_(?:code|id|identity|symbol)|episode(?:_id|_identities|_identity|s)?|exchange(?:_code|_id|_name)?|family(?:_code|_id|_name)?|instrument_(?:code|family|id|identity|symbol)|product(?:_code|_id|_name)?|provider_(?:adapter|code|implementation)|source_(?:alias|identities|identity))(?:_|$)/,
    /(?:^|_)(?:ev|loss|metric|ohlc|outcome|pnl|profit|raw_rows|returns?|rows|sample_members|sample_size|threshold|win_rate)(?:_|$)/,
  ].some((pattern) => pattern.test(normalized));
}

function stringLeakPatterns() {
  const privateRoots = ["ho" + "me", "ro" + "ot", "sr" + "v", "op" + "t", "va" + "r", "tm" + "p", "mn" + "t", "Us" + "ers"];
  const tokenPrefixes = ["gh" + "p_", "github_" + "pat_", "AK" + "IA", "sk" + "-live-"];
  const identityLabels = ["contract", "episode", "instrument", "source" + "_alias"];
  const credentialLabels = ["access[_-]?token", "api[_-]?key", "client[_-]?secret", "password", "refresh[_-]?token"];
  const exchangeCodes = ["SH" + "FE", "D" + "CE", "CZ" + "CE", "CFF" + "EX", "I" + "NE", "GF" + "EX"];
  const provenanceLabels = ["exchange", "family", "product", "provider"];
  return [
    new RegExp(`/(?:${privateRoots.join("|")})/`, "i"),
    new RegExp("fi" + "le:/+", "i"),
    /[A-Za-z]:\\/,
    /\\\\[^\\\s]+\\[^\\\s]+/,
    new RegExp("BEGIN (?:RSA |EC |OPENSSH )?" + "PRIVATE" + " KEY", "i"),
    new RegExp(`(?:${tokenPrefixes.join("|")})[A-Za-z0-9_-]{8,}`),
    new RegExp("(?:Auth" + "orization\\s*:\\s*(?:Bearer|Basic)|Bearer\\s+[A-Za-z0-9._-]{8,})", "i"),
    new RegExp(`(?:${credentialLabels.join("|")})\\s*[:=]\\s*[^\\s,;]+`, "i"),
    new RegExp(`(?:${identityLabels.join("|")})(?:[_-]?(?:id|identity|code|symbol))?\\s*[:=]\\s*[^\\s,;]+`, "i"),
    new RegExp(`(?:${provenanceLabels.join("|")})(?:[_-]?(?:adapter|code|id|name))?\\s*[:=]\\s*[^\\s,;]+`, "i"),
    new RegExp(`\\b(?:${exchangeCodes.join("|")})[.:/][A-Za-z]{1,4}(?:\\d{3,4})?\\b`, "i"),
    new RegExp("\\bM6" + "R-[0-9a-f]{16,64}\\b", "i"),
    /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i,
  ];
}

function validateStringSafety(value, label, { sourceCode = false } = {}) {
  if (!sourceCode) {
    invariant(!/(?:^|[\s=:])\/(?!\/)[^\s,;]*/.test(value), `${label}: absolute path forbidden`);
  }
  for (const [index, pattern] of stringLeakPatterns().entries()) {
    if (sourceCode && index === 3) continue;
    invariant(!pattern.test(value), `${label}: forbidden public string (${pattern})`);
  }
}

function validateJsonSafety(value, label, path = []) {
  if (Array.isArray(value)) {
    value.forEach((item, index) => validateJsonSafety(item, label, [...path, index]));
    return;
  }
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      const normalized = normalizedKey(key);
      invariant(
        !FORBIDDEN_DATA_KEYS.has(normalized) && !forbiddenAliasedKey(key),
        `${label}.${[...path, key].join(".")}: forbidden data field`,
      );
      validateJsonSafety(child, label, [...path, key]);
    }
    return;
  }
  if (typeof value === "string") validateStringSafety(value, `${label}.${path.join(".")}`);
}

function validateVerifierCapabilities(verifierSource) {
  const expectedImports = ["node:crypto", "node:fs", "node:path", "node:url"].sort();
  const staticImportPattern = /\bimport\s*(?:[^"'();]*?\s+from\s*)?["']([^"']+)["']\s*;?/g;
  const actualImports = [...verifierSource.matchAll(staticImportPattern)].map((match) => match[1]).sort();
  invariant(sameValue(actualImports, expectedImports), "verifier: import capability allowlist changed");
  invariant(
    (verifierSource.match(/\bimport\b/g) ?? []).length === 6,
    "verifier: unexpected module token",
  );

  const forbiddenSyntax = [
    /\\(?:u(?:[0-9A-Fa-f]{4}|\{[0-9A-Fa-f]{1,6}\})|x[0-9A-Fa-f]{2})/,
    new RegExp("\\b" + "fe" + "tch\\b"),
    new RegExp("\\b" + "Web" + "Socket\\b"),
    new RegExp("\\b" + "XMLHttp" + "Request\\b"),
    new RegExp("\\b" + "im" + "port\\s*\\("),
    new RegExp("\\b" + "requ" + "ire\\s*\\("),
    new RegExp("\\b" + "ev" + "al\\b"),
    new RegExp("\\b" + "Fun" + "ction\\b"),
    new RegExp(("pro" + "cess") + "\\.(?:binding|env|mainModule)"),
    new RegExp("\\bglo" + "bal(?:This)?\\b"),
    new RegExp("\\bReflect\\s*\\.\\s*get\\s*\\("),
    new RegExp("(?:\\.\\s*|\\[\\s*[\"'])" + "con" + "structor\\b"),
    new RegExp("[\"']con[\"']\\s*\\+\\s*[\"']structor[\"']"),
    new RegExp("\\b(?:get|set)" + "PrototypeOf\\b|__" + "proto__"),
    new RegExp("\\b(?:De" + "no|B" + "un)\\."),
  ];
  for (const pattern of forbiddenSyntax) {
    invariant(!pattern.test(verifierSource), `verifier: dynamic capability forbidden (${pattern})`);
  }

  const processAccessPattern = /\bprocess\s*(?:\.\s*([A-Za-z_][\w$]*)|\[\s*["']([^"']+)["']\s*\])/g;
  const processAccesses = [...verifierSource.matchAll(processAccessPattern)].map((match) => match[1] ?? match[2]);
  invariant(
    sameValue(processAccesses.sort(), ["argv", "execArgv", "permission", "permission"].sort()),
    "verifier: runtime capability allowlist changed",
  );
  invariant(
    (verifierSource.match(/\bprocess\b/g) ?? []).length === 4,
    "verifier: unexpected runtime token",
  );
  invariant(!/\bprocess\s*\[/.test(verifierSource), "verifier: computed runtime capability forbidden");

  const readCalls = verifierSource.match(new RegExp("readFile" + "Sync\\s*\\(", "g")) ?? [];
  const directoryCalls = verifierSource.match(new RegExp("readdir" + "Sync\\s*\\(", "g")) ?? [];
  invariant(readCalls.length === 1, "verifier: unexpected file-read capability");
  invariant(directoryCalls.length === 1, "verifier: unexpected directory-read capability");
  invariant((verifierSource.match(/\breadFileSync\b/g) ?? []).length === 2, "verifier: file reader alias forbidden");
  invariant((verifierSource.match(/\breaddirSync\b/g) ?? []).length === 2, "verifier: directory reader alias forbidden");
  const allowedRead = "readFile" + "Sync(join(DIR, name))";
  const allowedDirectoryRead = "readdir" + "Sync(DIR)";
  invariant(verifierSource.includes(allowedRead), "verifier: reads must stay inside package directory");
  invariant(verifierSource.includes(allowedDirectoryRead), "verifier: directory reads must stay inside package directory");
  validateStringSafety(verifierSource, "verifier source", { sourceCode: true });
}

function validatePublicSafety(raws) {
  validateJsonSafety(JSON.parse(raws[RECEIPT_PATH].toString("utf8")), "receipt");
  validateJsonSafety(JSON.parse(raws[ATTESTATION_PATH].toString("utf8")), "attestation");
  validateJsonSafety(JSON.parse(raws[MANIFEST_PATH].toString("utf8")), "manifest");
  validateVerifierCapabilities(raws[VERIFIER_PATH].toString("utf8"));
}

function validateReceipt(receipt) {
  exactKeys(receipt, Object.keys(EXPECTED_RECEIPT), "receipt");
  invariant(sameValue(receipt, EXPECTED_RECEIPT), "receipt: exact contract mismatch");
  for (const [key, value] of Object.entries(receipt)) {
    if (key.endsWith("_sha256")) hash64(value, `receipt.${key}`);
  }
  strictUtc(receipt.sealed_at, "receipt.sealed_at");
  invariant(receipt.custodian_role !== "strategy", "receipt: Strategy cannot be custodian");
  invariant(receipt.release_authority_role === "pi", "receipt: PI must remain release authority");
  invariant(
    receipt.required_releasing_issue_type === "pi_approved_preregistration_design",
    "receipt: release gate changed",
  );
  invariant(receipt.access_log_locator.startsWith("custody://"), "receipt: locator must be public custody alias");
}

function validateAttestation(attestation, receipt, receiptRaw) {
  exactKeys(attestation, Object.keys(EXPECTED_ATTESTATION), "attestation");
  invariant(sameValue(attestation, EXPECTED_ATTESTATION), "attestation: exact contract mismatch");
  exactKeys(attestation.assertions, Object.keys(EXPECTED_ASSERTIONS), "attestation.assertions");
  invariant(attestation.assertion_count === 10, "attestation: assertion_count must be ten");
  invariant(Object.keys(attestation.assertions).length === 10, "attestation: exactly ten assertions required");
  invariant(Object.values(attestation.assertions).every((value) => value === true), "attestation: every assertion must pass");
  invariant(attestation.overall_result === "pass", "attestation: overall result must pass");
  invariant(attestation.reserve_nonempty === true, "attestation: reserve must be nonempty");
  invariant(
    attestation.no_strategy_access_or_release_before_verified_at === true,
    "attestation: pre-verification Strategy non-access must be explicit",
  );
  invariant(
    attestation.verifier_independent_from_custodian === true,
    "attestation: verifier independence must be explicit",
  );
  invariant(attestation.verifier_role !== attestation.custodian_role, "attestation: verifier and custodian roles must differ");
  invariant(attestation.verifier_role === "independent_data_verifier", "attestation: verifier role changed");
  invariant(attestation.custodian_role === receipt.custodian_role, "attestation: custodian binding mismatch");
  invariant(attestation.reserve_id === receipt.reserve_id, "attestation: reserve binding mismatch");
  invariant(
    attestation.access_log_chain_head_sha256 === receipt.access_log_chain_head_sha256,
    "attestation: chain-head binding mismatch",
  );
  invariant(attestation.custody_receipt_path === RECEIPT_PATH, "attestation: receipt path mismatch");
  invariant(
    attestation.custody_receipt_raw_byte_sha256 === sha256(receiptRaw),
    "attestation: receipt raw-byte hash mismatch",
  );
  const sealedAt = strictUtc(receipt.sealed_at, "receipt.sealed_at");
  const verifiedAt = strictUtc(attestation.verified_at, "attestation.verified_at");
  invariant(verifiedAt > sealedAt, "attestation: verification must follow sealing");
  for (const [key, value] of Object.entries(attestation)) {
    if (key.endsWith("_sha256")) hash64(value, `attestation.${key}`);
  }
}

function validateManifest(manifest, raws) {
  const expectedPaths = [ATTESTATION_PATH, RECEIPT_PATH, VERIFIER_PATH].sort();
  exactKeys(manifest, ["dependency_id", "invocation", "issue_number", "payloads", "schema_version"], "manifest");
  invariant(manifest.dependency_id === "M6F-CONFIRMATION-RESERVE-01", "manifest: dependency mismatch");
  invariant(manifest.invocation === CANONICAL_INVOCATION, "manifest: canonical invocation changed");
  invariant(manifest.issue_number === 80, "manifest: issue mismatch");
  invariant(
    manifest.schema_version === "pa_feitian_m6f_confirmation_reserve_public_artifact_manifest_v1",
    "manifest: schema mismatch",
  );
  invariant(Array.isArray(manifest.payloads), "manifest: payloads must be an array");
  invariant(
    sameValue(manifest.payloads.map((entry) => entry.path).sort(), expectedPaths),
    "manifest: payload membership mismatch",
  );
  invariant(manifest.payloads.length === expectedPaths.length, "manifest: duplicate payload entries");
  for (const entry of manifest.payloads) {
    exactKeys(entry, ["byte_length", "path", "raw_byte_sha256"], `manifest.${entry.path}`);
    invariant(expectedPaths.includes(entry.path), `manifest: unexpected path ${entry.path}`);
    const raw = raws[entry.path];
    invariant(Buffer.isBuffer(raw), `manifest: missing bytes for ${entry.path}`);
    invariant(Number.isInteger(entry.byte_length) && entry.byte_length === raw.length, `manifest: size mismatch for ${entry.path}`);
    hash64(entry.raw_byte_sha256, `manifest.${entry.path}.raw_byte_sha256`);
    invariant(entry.raw_byte_sha256 === sha256(raw), `manifest: hash mismatch for ${entry.path}`);
  }
}

function readPackage() {
  const raws = Object.fromEntries(PACKAGE_FILES.map((name) => [name, readFileSync(join(DIR, name))]));
  return raws;
}

function validateArtifacts(raws, { checkDirectory = false } = {}) {
  if (checkDirectory) {
    invariant(sameValue(readdirSync(DIR).sort(), PACKAGE_FILES), "package: unexpected directory membership");
  }
  const receipt = parseCanonical(raws[RECEIPT_PATH], RECEIPT_PATH);
  const attestation = parseCanonical(raws[ATTESTATION_PATH], ATTESTATION_PATH);
  const manifest = parseCanonical(raws[MANIFEST_PATH], MANIFEST_PATH);
  validateReceipt(receipt);
  validateAttestation(attestation, receipt, raws[RECEIPT_PATH]);
  validateManifest(manifest, raws);
  validatePublicSafety(raws);
  return { attestation, manifest, receipt };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function renderMutation(base, mutation) {
  const state = {
    attestation: clone(base.attestation),
    manifest: clone(base.manifest),
    receipt: clone(base.receipt),
    verifierRaw: Buffer.from(base.raws[VERIFIER_PATH]),
  };
  mutation.mutate(state);
  const receiptRaw = canonicalBytes(state.receipt);
  state.attestation.custody_receipt_raw_byte_sha256 = sha256(receiptRaw);
  if (mutation.afterReceipt) mutation.afterReceipt(state);
  const attestationRaw = canonicalBytes(state.attestation);
  const raws = {
    [ATTESTATION_PATH]: attestationRaw,
    [RECEIPT_PATH]: receiptRaw,
    [VERIFIER_PATH]: state.verifierRaw,
  };
  for (const entry of state.manifest.payloads) {
    entry.byte_length = raws[entry.path].length;
    entry.raw_byte_sha256 = sha256(raws[entry.path]);
  }
  if (mutation.afterManifest) mutation.afterManifest(state);
  raws[MANIFEST_PATH] = canonicalBytes(state.manifest);
  return raws;
}

function negativeMutations(base) {
  const zero = "0".repeat(64);
  const cases = [
    { name: "custodian_role", mutate: (s) => { s.receipt.custodian_role = "strategy"; s.attestation.custodian_role = "strategy"; } },
    { name: "release_authority_role", mutate: (s) => { s.receipt.release_authority_role = "data_owner"; } },
    { name: "verifier_role", mutate: (s) => { s.attestation.verifier_role = "reviewer"; } },
    { name: "release_gate", mutate: (s) => { s.receipt.required_releasing_issue_type = "ordinary_issue"; } },
    { name: "eligibility_rule_hash", mutate: (s) => { s.receipt.eligibility_rule_sha256 = zero; } },
    { name: "exclusion_set_hash", mutate: (s) => { s.receipt.exclusion_set_sha256 = zero; } },
    { name: "identity_manifest_plaintext_hash", mutate: (s) => { s.receipt.identity_manifest_plaintext_sha256 = zero; } },
    { name: "identity_manifest_envelope_hash", mutate: (s) => { s.receipt.identity_manifest_envelope_sha256 = zero; } },
    { name: "exclusion_registry_plaintext_hash", mutate: (s) => { s.receipt.exclusion_registry_plaintext_sha256 = zero; } },
    { name: "exclusion_registry_envelope_hash", mutate: (s) => { s.receipt.exclusion_registry_envelope_sha256 = zero; } },
    { name: "chain_head", mutate: (s) => { s.receipt.access_log_chain_head_sha256 = zero; s.attestation.access_log_chain_head_sha256 = zero; } },
    { name: "access_log_locator", mutate: (s) => { s.receipt.access_log_locator = "custody://substituted/log.jsonl"; } },
    { name: "verification_result", mutate: (s) => { s.attestation.overall_result = "fail"; } },
    { name: "verification_time_syntax", mutate: (s) => { s.attestation.verified_at = "2026-08-02 11:48:50"; } },
    { name: "verification_time_order", mutate: (s) => { s.attestation.verified_at = "2026-08-02T09:00:00Z"; } },
    { name: "independence_boolean", mutate: (s) => { s.attestation.verifier_independent_from_custodian = false; } },
    { name: "independence_role_collision", mutate: (s) => { s.attestation.verifier_role = s.attestation.custodian_role; } },
    { name: "strategy_non_access", mutate: (s) => { s.attestation.no_strategy_access_or_release_before_verified_at = false; } },
    { name: "reserve_nonempty", mutate: (s) => { s.attestation.reserve_nonempty = false; } },
    { name: "assertion_count", mutate: (s) => { s.attestation.assertion_count = 9; } },
    { name: "verification_report_plaintext_hash", mutate: (s) => { s.attestation.verification_report_plaintext_sha256 = zero; } },
    { name: "verification_report_envelope_hash", mutate: (s) => { s.attestation.verification_report_envelope_sha256 = zero; } },
    { name: "receipt_hash_binding", mutate: () => {}, afterReceipt: (s) => { s.attestation.custody_receipt_raw_byte_sha256 = zero; } },
    { name: "receipt_path_binding", mutate: (s) => { s.attestation.custody_receipt_path = "other.json"; } },
    { name: "sealed_at", mutate: (s) => { s.receipt.sealed_at = "2026-08-02T99:23:03Z"; } },
    ...Object.keys(EXPECTED_ASSERTIONS).map((key) => ({
      name: `assertion_${key}`,
      mutate: (s) => { s.attestation.assertions[key] = false; },
    })),
    {
      name: "manifest_hash",
      mutate: () => {},
      afterManifest: (s) => { s.manifest.payloads[0].raw_byte_sha256 = zero; },
    },
    { name: "manifest_invocation", mutate: (s) => { s.manifest.invocation = "node verify.mjs"; } },
    ...["ne" + "t", "tl" + "s", "dn" + "s", "dg" + "ram", "ht" + "tp2", "child" + "_process"].map((moduleName) => ({
      name: `verifier_import_${moduleName}`,
      mutate: (s) => {
        const keyword = "im" + "port";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\n${keyword} "node:${moduleName}";\n`)]);
      },
    })),
    {
      name: "verifier_compact_static_import",
      mutate: (s) => {
        const keyword = "im" + "port";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\n${keyword}"node:net";\n`)]);
      },
    },
    {
      name: "verifier_network_global",
      mutate: (s) => {
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid ${"fe" + "tch"}("https://example.invalid");\n`)]);
      },
    },
    {
      name: "verifier_network_alias",
      mutate: (s) => {
        const networkGlobal = "fe" + "tch";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nconst networkAlias=${networkGlobal}; void networkAlias("https://example.invalid");\n`)]);
      },
    },
    {
      name: "verifier_eval_alias",
      mutate: (s) => {
        const evaluator = "ev" + "al";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nconst evaluatorAlias=${evaluator}; void evaluatorAlias("0");\n`)]);
      },
    },
    ...[
      ["unicode_escaped_fetch", "f", "u0065", "tch"],
      ["unicode_escaped_eval", "ev", "u0061", "l"],
      ["unicode_escaped_function", "Funct", "u0069", "on"],
      ["unicode_codepoint_fetch", "f", "u{65}", "tch"],
    ].map(([name, prefix, escape, suffix]) => ({
      name: `verifier_${name}`,
      mutate: (s) => {
        const slash = "\\";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid ${prefix}${slash}${escape}${suffix};\n`)]);
      },
    })),
    {
      name: "verifier_websocket",
      mutate: (s) => {
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid new ${"Web" + "Socket"}("wss://example.invalid");\n`)]);
      },
    },
    {
      name: "verifier_dynamic_import",
      mutate: (s) => {
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid ${"im" + "port"}("node:fs");\n`)]);
      },
    },
    {
      name: "verifier_private_read",
      mutate: (s) => {
        const call = `${"readFile" + "Sync"}("/${"ro" + "ot"}/private")`;
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid ${call};\n`)]);
      },
    },
    {
      name: "verifier_aliased_private_read",
      mutate: (s) => {
        const reader = "readFile" + "Sync";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nconst privateReader=${reader}; void privateReader(join(DIR,"..","private"));\n`)]);
      },
    },
    {
      name: "verifier_process_env",
      mutate: (s) => {
        const runtime = "pro" + "cess";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid ${runtime}.${"en" + "v"};\n`)]);
      },
    },
    ...["f" + "s", "child" + "_process"].map((moduleName) => ({
      name: `verifier_get_builtin_${moduleName}`,
      mutate: (s) => {
        const accessor = "get" + "Builtin" + "Module";
        const runtime = "pro" + "cess";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid ${runtime}.${accessor}("${moduleName}");\n`)]);
      },
    })),
    {
      name: "verifier_process_dlopen",
      mutate: (s) => {
        const accessor = "dl" + "open";
        const runtime = "pro" + "cess";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid ${runtime}.${accessor};\n`)]);
      },
    },
    {
      name: "verifier_process_alias",
      mutate: (s) => {
        const accessor = "get" + "Builtin" + "Module";
        const runtime = "pro" + "cess";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nconst runtimeAlias=${runtime}; void runtimeAlias.${accessor}("fs");\n`)]);
      },
    },
    {
      name: "verifier_global_builtin_alias",
      mutate: (s) => {
        const runtime = "pro" + "cess";
        const accessor = "get" + "Builtin" + "Module";
        const root = "glo" + "bal";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid ${root}["${runtime}"]["${accessor}"]("fs");\n`)]);
      },
    },
    {
      name: "verifier_reflective_constructor",
      mutate: (s) => {
        const constructor = ["con", "structor"].join("");
        const runtime = "pro" + "cess";
        const accessor = "get" + "Builtin" + "Module";
        s.verifierRaw = Buffer.concat([s.verifierRaw, Buffer.from(`\nvoid console.log.${constructor}("return ${runtime}")()["${accessor}"]("child_process");\n`)]);
      },
    },
  ];

  for (const mutation of cases) {
    let rejected = false;
    try {
      validateArtifacts(renderMutation(base, mutation));
    } catch {
      rejected = true;
    }
    invariant(rejected, `negative mutation was accepted: ${mutation.name}`);
  }
  return cases.length;
}

function publicSafetyMutations(base) {
  const privateRoots = ["ho" + "me", "ro" + "ot", "sr" + "v", "op" + "t", "va" + "r", "tm" + "p", "mn" + "t", "Us" + "ers"];
  const cases = [
    { name: "reserve_identity", key: "source_identities", value: ["sealed-member"] },
    { name: "contract_identity", key: "contract_identity", value: "private-contract" },
    { name: "episode_identity", key: "episode_id", value: "private-episode" },
    { name: "instrument_identity", key: "instrument_family", value: "private-family" },
    { name: "email", key: "note", value: "person" + "@" + "example.com" },
    { name: "raw_ohlc", key: "ohlc", value: { open: 1, high: 2, low: 0, close: 1 } },
    { name: "sample_rows", key: "sample_members", value: ["member"] },
    { name: "outcome", key: "outcome", value: "positive" },
    { name: "performance", key: "pnl", value: 1 },
    { name: "provider_code", key: "provider_implementation", value: "private adapter" },
    { name: "client_secret_alias", key: "clientSecret", value: "not-public" },
    { name: "client_secret_collapsed_alias", key: "clientsecret", value: "not-public" },
    { name: "contract_id_alias", key: "contractId", value: "private-contract" },
    { name: "instrument_id_alias", key: "instrument-id", value: "private-instrument" },
    { name: "outcome_summary_alias", key: "outcome_summary", value: "positive" },
    { name: "family_name_alias", key: "familyName", value: "private-family" },
    { name: "exchange_code_alias", key: "exchangeCode", value: "private-exchange" },
    { name: "product_id_alias", key: "productId", value: "private-product" },
    { name: "provider_adapter_alias", key: "providerAdapter", value: "private-provider" },
    { name: "refresh_token_alias", key: "refreshToken", value: "not-public" },
    { name: "credential_assignment", key: "note", value: ("client" + "_secret") + "=not-public" },
    { name: "credential_camel_assignment", key: "note", value: ("client" + "Secret") + "=not-public" },
    { name: "identity_assignment", key: "note", value: ("contract" + "_id") + "=private-contract" },
    { name: "market_identity_value", key: "note", value: ("SH" + "FE") + ".au2606" },
    { name: "market_family_value", key: "note", value: ("D" + "CE") + ".m" },
    { name: "market_product_value", key: "note", value: ("SH" + "FE") + ".au" },
    { name: "m6r_episode_value", key: "note", value: ("M6" + "R-") + "0123456789abcdefabcd" },
    { name: "authorization", key: "authorization", value: "Bear" + "er abcdefghijklmnop" },
    { name: "token_prefix", key: "note", value: "gh" + "p_" + "A".repeat(24) },
    { name: "unc_path", key: "note", value: "\\" + "\\server\\share\\private" },
    { name: "file_uri", key: "note", value: "fi" + "le:///private/location" },
    { name: "single_slash_file_uri", key: "note", value: "fi" + "le:/data/private" },
    { name: "generic_absolute_path", key: "note", value: "/data/private" },
    { name: "windows_path", key: "note", value: "C" + ":\\private\\location" },
    { name: "private_key", key: "note", value: "-----BEGIN " + "PRIVATE" + " KEY-----" },
    { name: "secret_field", key: "secret", value: "not-public" },
    ...privateRoots.map((root) => ({ name: `private_root_${root}`, key: "note", value: `/${root}/private/location` })),
  ];

  for (const mutation of cases) {
    const receipt = clone(base.receipt);
    receipt[mutation.key] = mutation.value;
    const candidate = { ...base.raws, [RECEIPT_PATH]: canonicalBytes(receipt) };
    let rejected = false;
    try {
      validatePublicSafety(candidate);
    } catch {
      rejected = true;
    }
    invariant(rejected, `public-safety mutation was accepted: ${mutation.name}`);
  }
  return cases.length;
}

const args = process.argv.slice(2);
invariant(args.length <= 1 && (args.length === 0 || args[0] === "--negative"), "usage: node verify.mjs [--negative]");
validateRuntimeBoundary();
const raws = readPackage();
const parsed = validateArtifacts(raws, { checkDirectory: true });

if (args[0] === "--negative") {
  const base = { ...parsed, raws };
  const count = negativeMutations(base) + publicSafetyMutations(base);
  console.log(JSON.stringify({ negative_mutations: count, ok: true }));
} else {
  console.log(JSON.stringify({
    assertions: parsed.attestation.assertion_count,
    files: PACKAGE_FILES.length,
    ok: true,
    overall_result: parsed.attestation.overall_result,
    reserve_nonempty: parsed.attestation.reserve_nonempty,
  }));
}
