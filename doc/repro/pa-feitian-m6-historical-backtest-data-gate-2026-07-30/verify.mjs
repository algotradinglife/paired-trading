#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const contractPath = resolve(
  repoRoot,
  "docs/research/pa-feitian-m6-historical-backtest-data-gate-contract-v1.json",
);
const profilePath = resolve(packetDir, "historical_backtest_data_gate_profile_v1.json");
const readmePath = resolve(packetDir, "README.md");
const builderPath = resolve(
  repoRoot,
  "src/scripts/build_pa_feitian_historical_backtest_gate.py",
);
const testPath = resolve(
  repoRoot,
  "src/tests/test_pa_feitian_historical_backtest_gate.py",
);
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

function canonical(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonical).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function runPython(args) {
  return spawnSync(python, args, {
    cwd: repoRoot,
    encoding: "utf8",
    env: { ...process.env, PYTHONPATH: resolve(repoRoot, "src") },
  });
}

const contract = json(contractPath);
const profile = json(profilePath);
const families = ["SHFE.au", "SHFE.ag", "CZCE.TA", "CZCE.MA", "SHFE.cu", "DCE.i"];
const allCadences = ["daily", "hour", "min15", "min5"];
const requiredCadences = ["daily", "hour", "min15"];

assert.equal(
  contract.schema_version,
  "pa_feitian_m6_historical_backtest_data_gate_contract_v1",
);
assert.equal(contract.issue_number, 50);
assert.equal(contract.timezone, "Asia/Shanghai");
assert.deepEqual(
  contract.candidate_universe.map((row) => row.instrument_family),
  families,
);
assert.deepEqual(contract.p1_exp_002_input_policy.required_families, families);
assert.deepEqual(
  contract.p1_exp_002_input_policy.required_underlying_cadences,
  requiredCadences,
);
assert.equal(contract.p1_exp_002_input_policy.allowed_mode, "historical_replay");
assert.equal(contract.p1_exp_002_input_policy.request_scope, "one_decision_timestamp");
assert.equal(
  contract.p1_exp_002_input_policy.formal_run_coverage,
  "exactly_one_allow_decision_per_materialized_decision_timestamp",
);
assert.equal(contract.p1_exp_002_input_policy.option_inputs_allowed, false);
assert.equal(contract.p1_exp_002_input_policy.min5_input_allowed, false);
assert.equal(
  contract.mode_policy.historical_replay.append_only_acquisition_manifest_required,
  false,
);
assert.equal(
  contract.mode_policy.historical_replay.exact_filtered_content_binding_required,
  true,
);
assert.equal(
  contract.mode_policy.historical_replay
    .independently_approved_native_source_version_required,
  true,
);
assert.equal(contract.mode_policy.live.authorized_by_this_gate, false);
assert.equal(contract.binding_policy.manifest_membership_hash_is_sufficient, false);
assert.equal(
  contract.binding_policy.approved_native_source_version_manifest_sha256,
  null,
);
assert.equal(
  contract.binding_policy.complete_prefix_extraction,
  "all_approved_native_rows_from_history_start_through_decision_cutoff",
);
assert.deepEqual(contract.binding_policy.calendar_versions, {
  XSGE: "exchange_calendars==4.13.2+XSGE+cn_night_session_v1",
  XZCE: "exchange_calendars==4.13.2+XZCE+cn_night_session_v1",
  XDCE: "exchange_calendars==4.13.2+XDCE+cn_night_session_v1",
});
assert.equal(
  contract.binding_policy.duplicate_identity,
  "composite_identity_key_fields_not_timestamp_alone",
);
assert.deepEqual(contract.binding_policy.required_underlying_fields, [
  "open",
  "high",
  "low",
  "close",
  "volume",
  "open_interest",
]);
assert.equal(contract.fail_closed_policy.nonfinite_or_negative_activity_rows, 0);
assert.equal(contract.fail_closed_policy.option_inputs, "forbidden");
assert.equal(contract.request_schema.exact_binding_fields.length, 24);
assert(contract.decision_schema.exact_top_level_fields.includes("manifest_binding"));
assert.equal(contract.research_boundary.p1_exp_002_outcome_work_authorized, false);
assert.equal(contract.research_boundary.issue_51_unblocked, false);
assert.equal(contract.research_boundary.causal_roll_rule_recomputation_authorized, false);
assert.equal(
  contract.research_boundary.causal_roll_semantic_validation_owner,
  "issue_51_strategy_implementation",
);
assert.equal(contract.research_boundary.execution_authorized, false);

const aliases = contract.bound_evidence.map((row) => row.alias);
assert.equal(aliases.length, 7);
assert(aliases.includes("hypothesis_registry_v2"));
assert(aliases.includes("hypothesis_registry_v2_lock"));
assert.deepEqual(
  profile.bound_evidence.map((row) => row.alias),
  aliases,
);
for (const expected of contract.bound_evidence) {
  const sourcePath = resolve(repoRoot, expected.path);
  assert.equal(expected.sha256, digest(bytes(sourcePath)));
  assert.equal(json(sourcePath).schema_version, expected.schema_version);
  assert.deepEqual(
    profile.bound_evidence.find((row) => row.alias === expected.alias),
    expected,
  );
}

assert.equal(
  profile.contract.sha256,
  digest(Buffer.from(canonical(contract), "utf8")),
);
assert.equal(
  profile.contract.sha256,
  "sha256:ce8508f1cb6f15d5030e6424404f07c7d2e346811ccbc1bad033f63d4bc3d351",
);
assert.equal(profile.contract.sha256_kind, "canonical_json_sha256");
assert.equal(profile.engineer_surface.p1_exp_002_required_binding_count, 18);
assert.deepEqual(
  profile.engineer_surface.p1_exp_002_required_underlying_cadences,
  requiredCadences,
);
assert.equal(profile.engineer_surface.p1_exp_002_option_inputs_allowed, false);
assert.equal(profile.engineer_surface.source_snapshot_verification_required, true);
assert.equal(profile.engineer_surface.approved_native_source_version_registered, false);
assert.equal(
  profile.baseline.p1_exp_002_gate_status,
  "blocked_no_approved_native_source_version",
);
assert.equal(profile.baseline.p1_exp_002_outcome_work_authorized, false);
assert.equal(profile.baseline.issue_51_unblocked, false);

assert.deepEqual(
  profile.candidate_interface_mapping.map((row) => row.instrument_family),
  families,
);
for (const family of profile.candidate_interface_mapping) {
  assert.deepEqual(
    family.cadences.map((row) => row.cadence),
    allCadences,
  );
  for (const cadence of family.cadences) {
    const underlying = cadence.interfaces.underlying;
    const option = cadence.interfaces.option_premium;
    assert.equal(underlying.available, true);
    assert.equal(option.available, true);
    assert.deepEqual(Object.keys(underlying.required_activity_fields).sort(), [
      "open_interest",
      "volume",
    ]);
    assert.deepEqual(option.required_activity_fields, {});
    assert.equal(
      underlying.formal_historical_use,
      requiredCadences.includes(cadence.cadence)
        ? "conditional_exact_run_binding_required"
        : "not_consumed_by_p1_exp_002",
    );
    assert.equal(option.formal_historical_use, "not_consumed_by_p1_exp_002");
  }
}

const readme = bytes(readmePath).toString("utf8");
for (const family of families) {
  assert(readme.includes(`| ${family} |`), `README missing ${family}`);
}
assert.match(readme, /exactly 18 independently\s+verified underlying bindings/);
assert.match(readme, /does not itself allow\s+`P1-EXP-002`/);
assert.match(readme, /does not unblock Issue #51/);
assert.match(readme, /caller-truncated recent-only archive cannot become\s+eligible/);
assert.match(readme, /Sundays,\s+holidays, or false opens\/closes fail closed/);

const publicText = Buffer.concat([
  bytes(contractPath),
  bytes(profilePath),
  bytes(readmePath),
]).toString("utf8");
assert.doesNotMatch(publicText, /(?:^|[\s"'])\/(?:home|mnt|Users|var|tmp|root)\//);
assert.doesNotMatch(publicText, /\.parquet|\.csv/i);
assert.doesNotMatch(publicText, /\b(?:SHFE|CZCE|DCE)\.[A-Za-z]+\d/i);
assert.doesNotMatch(
  publicText,
  /(?:\bgithub_pat_|\bgh[opusr]_|\bsk-(?:proj-)?|\bxox[baprs]-|\bAKIA[0-9A-Z]{12,})/i,
);

const temporary = mkdtempSync(join(tmpdir(), "pa-feitian-historical-gate-"));
try {
  const rebuiltPath = join(temporary, "profile.json");
  const rebuilt = runPython([
    builderPath,
    "--contract",
    contractPath,
    "--repo-root",
    repoRoot,
    "--output",
    rebuiltPath,
  ]);
  assert.equal(
    rebuilt.status,
    0,
    `profile rebuild failed\nstdout:\n${rebuilt.stdout}\nstderr:\n${rebuilt.stderr}`,
  );
  assert.deepEqual(bytes(rebuiltPath), bytes(profilePath));

  const tests = runPython(["-m", "pytest", testPath, "-q"]);
  assert.equal(
    tests.status,
    0,
    `gate acceptance tests failed\nstdout:\n${tests.stdout}\nstderr:\n${tests.stderr}`,
  );
  assert.match(tests.stdout, /passed/);
} finally {
  rmSync(temporary, { recursive: true, force: true });
}

console.log(
  JSON.stringify({
    ok: true,
    families: families.length,
    required_bindings: 18,
    bound_evidence: aliases.length,
    profile_sha256: digest(bytes(profilePath)),
  }),
);
