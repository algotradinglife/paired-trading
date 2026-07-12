import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { REQUIRED_DIMENSIONS, validateRecoveryMatrix } from "./authentic_rule_recovery_validation_v1.mjs";

const matrix = JSON.parse(await readFile(new URL("./authentic_rule_recovery_evidence_matrix_v1.json", import.meta.url), "utf8"));

test("the committed matrix fails closed for authentic recovery", () => {
  validateRecoveryMatrix(matrix);
  assert.equal(matrix.authentic_rule_recovery_status, "blocked");
  assert.equal(matrix.faithful_bare_k_v1_emitted, false);
});

test("a synthetic all-exact matrix is the only promotable state", () => {
  const synthetic = structuredClone(matrix);
  synthetic.dimension_results = REQUIRED_DIMENSIONS.map((dimension) => ({
    dimension,
    status: "exact_source_supported",
    paraphrased_support: "Synthetic verifier-only support.",
    source_aliases: [synthetic.source_inventory[0].source_alias],
    missing_machine_testable_details: []
  }));
  synthetic.authentic_rule_recovery_status = "complete";
  synthetic.faithful_bare_k_v1_emitted = true;
  synthetic.minimum_missing_evidence = [];
  validateRecoveryMatrix(synthetic);
});

test("a non-exact dimension cannot be promoted", () => {
  const synthetic = structuredClone(matrix);
  synthetic.dimension_results = REQUIRED_DIMENSIONS.map((dimension) => ({
    dimension,
    status: "exact_source_supported",
    paraphrased_support: "Synthetic verifier-only support.",
    source_aliases: [synthetic.source_inventory[0].source_alias],
    missing_machine_testable_details: []
  }));
  synthetic.dimension_results[0].status = "ambiguous_source_supported";
  synthetic.authentic_rule_recovery_status = "complete";
  synthetic.faithful_bare_k_v1_emitted = true;
  assert.throws(() => validateRecoveryMatrix(synthetic));
});
