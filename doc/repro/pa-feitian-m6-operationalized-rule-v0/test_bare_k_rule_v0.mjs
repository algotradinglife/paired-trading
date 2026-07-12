import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { evaluateBareK, OBSERVATION_WINDOW_BARS, RULE_ID, STATUS_LABEL } from "./bare_k_rule_v0.mjs";

const artifactUrl = new URL("./synthetic_bare_k_rule_fixtures_v0.json", import.meta.url);
const fixtures = JSON.parse(await readFile(artifactUrl, "utf8")).fixtures;

test("the rule advertises the required bounded status", () => {
  assert.equal(RULE_ID, "operationalized_bare_k_v0");
  assert.equal(STATUS_LABEL, "operationalized_hypothesis_not_authentic");
  assert.equal(OBSERVATION_WINDOW_BARS, 9);
});

for (const fixture of fixtures) {
  test(`fixture: ${fixture.id}`, () => {
    const actual = evaluateBareK(fixture.bars);
    assert.equal(actual.decision, fixture.expected.decision);
    assert.equal(actual.direction, fixture.expected.direction);
    assert.equal(actual.state, fixture.expected.state);
    for (const [key, value] of Object.entries(fixture.expected.trace_predicates ?? {})) {
      assert.equal(actual.trace.predicates[key], value);
    }
    if (actual.trace.observation_end_index !== undefined) {
      assert.equal(actual.trace.observation_end_index, actual.trace.decision_index);
    }
  });
}
