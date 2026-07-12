import assert from "node:assert/strict";

export const REQUIRED_DIMENSIONS = [
  "chart_cadence_and_decision_timing",
  "long_directional_chain",
  "short_directional_chain",
  "pivot_and_anchor_selection",
  "dd_trend_line_construction_and_projection",
  "touch_break_and_tolerance_semantics",
  "candidate_confirmation_and_invalidation",
  "one_b_two_b_and_k_line_quality",
  "contract_and_option_selection_boundaries",
  "conflict_precedence_and_abstention",
  "explicit_no_lookahead_constraints"
];

const ALLOWED_STATUSES = new Set([
  "exact_source_supported",
  "ambiguous_source_supported",
  "inferred_only",
  "unresolved"
]);

export function validateRecoveryMatrix(matrix) {
  assert.equal(matrix.schema_version, "authentic_rule_recovery_evidence_matrix_v1");
  assert.equal(matrix.contract_reference.contract_id, "authentic_rule_recovery_contract_v1");
  assert(Array.isArray(matrix.source_inventory) && matrix.source_inventory.length > 0);

  const sourceAliases = new Set();
  for (const source of matrix.source_inventory) {
    for (const key of ["source_alias", "repository_alias", "source_revision", "file_sha256", "public_safe_locator", "evidence_role"]) {
      assert.equal(typeof source[key], "string", `source is missing ${key}`);
      assert(source[key].length > 0, `source has empty ${key}`);
    }
    assert(!sourceAliases.has(source.source_alias), `duplicate source alias: ${source.source_alias}`);
    sourceAliases.add(source.source_alias);
    assert.match(source.source_revision, /^[a-f0-9]{40}$/, `source ${source.source_alias} has invalid revision`);
    assert.match(source.file_sha256, /^[a-f0-9]{64}$/, `source ${source.source_alias} has invalid sha256`);
  }

  const dimensions = new Map();
  for (const result of matrix.dimension_results) {
    assert(REQUIRED_DIMENSIONS.includes(result.dimension), `unknown dimension: ${result.dimension}`);
    assert(!dimensions.has(result.dimension), `duplicate dimension: ${result.dimension}`);
    assert(ALLOWED_STATUSES.has(result.status), `invalid status for ${result.dimension}`);
    assert.equal(typeof result.paraphrased_support, "string");
    assert(result.paraphrased_support.length > 0);
    assert(Array.isArray(result.source_aliases) && result.source_aliases.length > 0);
    assert(result.source_aliases.every((alias) => sourceAliases.has(alias)), `unknown source alias in ${result.dimension}`);
    assert(Array.isArray(result.missing_machine_testable_details));
    if (result.status === "exact_source_supported") {
      assert.equal(result.missing_machine_testable_details.length, 0, `exact dimension ${result.dimension} has missing details`);
    } else {
      assert(result.missing_machine_testable_details.length > 0, `non-exact dimension ${result.dimension} needs a concrete missing detail`);
    }
    dimensions.set(result.dimension, result);
  }
  assert.deepEqual([...dimensions.keys()].sort(), [...REQUIRED_DIMENSIONS].sort());

  const allExact = REQUIRED_DIMENSIONS.every((dimension) => dimensions.get(dimension).status === "exact_source_supported");
  assert.equal(matrix.faithful_bare_k_v1_emitted, allExact, "faithful output may only follow all-exact dimensions");
  assert.equal(matrix.authentic_rule_recovery_status, allExact ? "complete" : "blocked");
  if (!allExact) {
    assert(Array.isArray(matrix.minimum_missing_evidence) && matrix.minimum_missing_evidence.length > 0);
  }
  assert.equal(matrix.scope_boundary.market_or_option_data_inspected, false);
  assert.equal(matrix.scope_boundary.performance_or_outcome_claim, false);
  assert.equal(matrix.scope_boundary.execution_or_live_work, false);
  assert.equal(matrix.scope_boundary.operationalized_rule_promoted, false);
}
