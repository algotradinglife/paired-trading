import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const packet = "doc/repro/pa-feitian-m6-historical-swing-induction-2026-07-12";
const protocolPath = "docs/research/pa-feitian-m6-historical-swing-induction-protocol-v1.json";
const atlasPath = `${packet}/historical_swing_atlas_v1.json`;
const protocol = JSON.parse(readFileSync(join(repoRoot, protocolPath), "utf8"));
const atlas = JSON.parse(readFileSync(join(repoRoot, atlasPath), "utf8"));

const forbidden = new Set([
  "open", "high", "low", "close", "raw_bar", "price", "chart",
  "future_return", "outcome", "pnl", "premium", "bid", "ask", "delta",
  "greeks", "dte", "execution"
]);

function assertNoForbiddenKeys(value) {
  if (Array.isArray(value)) {
    value.forEach(assertNoForbiddenKeys);
    return;
  }
  if (value && typeof value === "object") {
    for (const [key, nested] of Object.entries(value)) {
      assert(!forbidden.has(key), `public artifact contains forbidden key: ${key}`);
      assertNoForbiddenKeys(nested);
    }
  }
}

assert.equal(protocol.schema_version, "pa_feitian_m6_historical_swing_induction_protocol_v1");
assert.equal(protocol.protocol_status, "frozen_before_external_data_access");
assert.equal(protocol.induction.training_only, true);
assert.equal(protocol.induction.authentic_rule_recovery, false);
assert.equal(atlas.schema_version, "pa_feitian_m6_historical_swing_atlas_v1");
assert.equal(atlas.study_label, "empirical_operationalization_exploratory_only");
assert.equal(atlas.protocol.path, protocolPath);
assert.match(atlas.protocol.sha256, /^sha256:[a-f0-9]{64}$/);
for (const product of ["AU", "AG"]) {
  assert.equal(atlas.source_inventory.selected_series_by_product[product], 4);
  assert(atlas.coverage.candidate_windows_by_product_and_split[product].training > 0);
  assert(atlas.coverage.candidate_windows_by_product_and_split[product].holdout > 0);
}
assert.equal(atlas.induced_definition.labels.join(","), "empirically_induced_not_authentic,training_only");
assert(atlas.induced_definition.shared_training_trace_class_count > 0);
assert.equal(atlas.holdout_result.candidate_definition_frozen_before_holdout_application, true);
assert.equal(atlas.holdout_result.performance_metrics_present, false);
assert.equal(atlas.holdout_result.outcome_fields_present, false);
assertNoForbiddenKeys(atlas);

const publicText = [
  readFileSync(join(repoRoot, atlasPath), "utf8"),
  readFileSync(join(repoRoot, packet, "README.md"), "utf8")
].join("\n");
assert.doesNotMatch(publicText, /(?:^|[\s"'])\/(?:home|mnt|Users|var|tmp|root)\//, "public packet contains an absolute local path");
assert.doesNotMatch(publicText, /\bdrwho1985\b/i, "public packet contains a local username");
assert.doesNotMatch(publicText, /(?:api[_-]?key|access[_-]?token|private[_-]?key|password)\s*[:=]\s*["'][^"']+/i, "public packet appears to contain a credential");

if (process.env.PA_FEITIAN_REGENERATE === "1") {
  const python = process.env.PA_FEITIAN_PYTHON;
  const dataRoot = process.env.QUANT_DATA_ROOT;
  assert(python, "PA_FEITIAN_PYTHON is required for regeneration");
  assert(dataRoot, "QUANT_DATA_ROOT is required for regeneration");
  const temp = mkdtempSync(join(tmpdir(), "pa-feitian-swing-"));
  const rebuilt = join(temp, "historical_swing_atlas_v1.json");
  try {
    execFileSync(
      python,
      [
        "src/scripts/build_pa_feitian_swing_induction.py",
        "--data-root", dataRoot,
        "--protocol", protocolPath,
        "--max-series-per-product", "4",
        "--out", rebuilt
      ],
      { cwd: repoRoot, env: { ...process.env, PYTHONPATH: "src" }, stdio: "inherit" }
    );
    assert.deepEqual(readFileSync(rebuilt), readFileSync(join(repoRoot, atlasPath)));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
}

console.log("PA/Feitian historical swing induction verification passed");
