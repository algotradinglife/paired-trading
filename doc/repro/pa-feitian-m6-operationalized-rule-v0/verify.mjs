import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { evaluateBareK, RULE_ID, STATUS_LABEL } from "./bare_k_rule_v0.mjs";

const here = fileURLToPath(new URL(".", import.meta.url));
const requiredJson = [
  "formalization_contract_v0.json",
  "bare_k_rule_v0.json",
  "source_assumption_ledger_v0.json",
  "synthetic_bare_k_rule_fixtures_v0.json"
];

async function readJson(name) {
  return JSON.parse(await readFile(new URL(`./${name}`, import.meta.url), "utf8"));
}

function collectStrings(value, output = []) {
  if (typeof value === "string") output.push(value);
  else if (Array.isArray(value)) value.forEach((item) => collectStrings(item, output));
  else if (value && typeof value === "object") Object.values(value).forEach((item) => collectStrings(item, output));
  return output;
}

function assertPublicSafe(strings) {
  const joined = strings.join("\n");
  assert.doesNotMatch(joined, /(?:^|[\s"'])\/(?:home|Users|var|tmp|root)\//, "public artifact contains an absolute local path");
  assert.doesNotMatch(joined, /\bdrwho1985\b/i, "public artifact contains a local username");
  assert.doesNotMatch(joined, /(?:api[_-]?key|access[_-]?token|private[_-]?key|password)\s*[:=]\s*["'][^"']+/i, "public artifact appears to contain a credential");
}

function assertNoForbiddenFixtureFields(fixtures, forbidden) {
  for (const fixture of fixtures) {
    for (const bar of fixture.bars) {
      for (const key of Object.keys(bar)) {
        assert(!forbidden.includes(key), `fixture ${fixture.id} contains forbidden field ${key}`);
      }
    }
  }
}

const contract = await readJson("formalization_contract_v0.json");
const spec = await readJson("bare_k_rule_v0.json");
const ledger = await readJson("source_assumption_ledger_v0.json");
const fixtureDocument = await readJson("synthetic_bare_k_rule_fixtures_v0.json");

assert.equal(contract.contract_version, RULE_ID);
assert.equal(contract.status_label, STATUS_LABEL);
assert.equal(contract.authentic_rule_recovery.status, "unresolved");
for (const excluded of ["premium paths", "performance or outcome claims", "fitting or parameter optimisation", "execution instructions", "bid/ask data", "delta or Greeks", "DTE", "model pricing", "future-bar observations"]) {
  assert(contract.scope.forbidden_inputs_or_outputs.includes(excluded), `contract omits forbidden boundary: ${excluded}`);
}

assert.equal(spec.rule_id, RULE_ID);
assert.equal(spec.status_label, STATUS_LABEL);
assert.equal(spec.authentic_rule_recovery.status, "unresolved");
assert.equal(spec.timing_and_window.future_bars, "forbidden");
assert.deepEqual(spec.input_contract.required_fields, ["id", "open", "high", "low", "close"]);
assertNoForbiddenFixtureFields(fixtureDocument.fixtures, spec.input_contract.forbidden_fields);

const sourceAliases = new Set(ledger.source_aliases.map((source) => source.alias));
for (const source of ledger.source_aliases) {
  for (const key of ["repository_alias", "revision_or_hash", "public_safe_locator", "use"]) {
    assert.equal(typeof source[key], "string", `source ${source.alias} misses ${key}`);
    assert(source[key].length > 0, `source ${source.alias} has empty ${key}`);
  }
}
for (const behavior of ledger.source_supported_behaviors) {
  assert(behavior.source_aliases.every((alias) => sourceAliases.has(alias)), `behavior ${behavior.id} has an unknown source alias`);
}
for (const assumption of ledger.provisional_assumptions) {
  for (const key of ["id", "behavior", "rationale", "source_gap", "expected_impact", "testable_alternative"]) {
    assert.equal(typeof assumption[key], "string", `assumption is missing ${key}`);
    assert(assumption[key].length > 0, `assumption ${assumption.id} has empty ${key}`);
  }
}
assert(ledger.provisional_assumptions.some((assumption) => assumption.id === "A-SHORT-001"));
assert(ledger.provisional_assumptions.some((assumption) => assumption.id === "A-QUALITY-001"));

assert.equal(fixtureDocument.data_notice.includes("invented"), true);
for (const fixture of fixtureDocument.fixtures) {
  const actual = evaluateBareK(fixture.bars);
  assert.equal(actual.decision, fixture.expected.decision, `fixture ${fixture.id} decision`);
  assert.equal(actual.direction, fixture.expected.direction, `fixture ${fixture.id} direction`);
  assert.equal(actual.state, fixture.expected.state, `fixture ${fixture.id} state`);
  if (actual.trace.observation_end_index !== undefined) {
    assert.equal(actual.trace.observation_end_index, actual.trace.decision_index, `fixture ${fixture.id} observed a future bar`);
    for (const index of [...actual.trace.pivot_indices.lows, ...actual.trace.pivot_indices.highs]) {
      assert(index < actual.trace.decision_index, `fixture ${fixture.id} used the decision or a future bar as a pivot`);
    }
  }
}

for (const file of await readdir(here)) {
  if (!file.endsWith(".json") && !file.endsWith(".md") && !file.endsWith(".mjs")) continue;
  assertPublicSafe([await readFile(new URL(`./${file}`, import.meta.url), "utf8")]);
}

execFileSync(process.execPath, ["--test", "test_bare_k_rule_v0.mjs"], { cwd: here, stdio: "inherit" });
console.log("operationalized bare-K v0 verification passed");
