import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const packet = "doc/repro/pa-feitian-m6-causal-swing-line-induction-2026-07-13";
const protocolPath = "docs/research/pa-feitian-m6-causal-swing-line-induction-protocol-v1.json";
const atlasPath = `${packet}/causal_swing_line_atlas_v1.json`;
const protocol = JSON.parse(readFileSync(join(repoRoot, protocolPath), "utf8"));
const atlas = JSON.parse(readFileSync(join(repoRoot, atlasPath), "utf8"));
const forbidden = new Set([
  "open", "high", "low", "close", "raw_bar", "price", "chart", "anchor",
  "projection", "tolerance", "future_return", "outcome", "pnl", "premium",
  "contract", "bid", "ask", "delta", "greeks", "dte", "execution"
]);

function sha256(path) {
  return `sha256:${createHash("sha256").update(readFileSync(path)).digest("hex")}`;
}

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

assert.equal(protocol.schema_version, "pa_feitian_m6_causal_swing_line_induction_protocol_v1");
assert.equal(protocol.protocol_status, "frozen_before_external_data_access");
assert.equal(protocol.causal_proxy_semantics.tolerance.formula, "0.25 times the median of high-low ranges of exactly the 20 completed bars before the decision bar");
for (const name of ["protocol", "atlas"]) {
  const binding = protocol.m6_exp_011_bindings[name];
  assert.equal(sha256(join(repoRoot, binding.path)), binding.sha256, `EXP-011 ${name} binding mismatch`);
}
assert.equal(atlas.schema_version, "pa_feitian_m6_causal_swing_line_atlas_v1");
assert.equal(atlas.study_label, "empirical_operationalization_exploratory_only");
assert.equal(atlas.protocol.path, protocolPath);
assert.equal(atlas.protocol.sha256, sha256(join(repoRoot, protocolPath)));
assert.equal(atlas.m6_exp_011_atlas.sha256, protocol.m6_exp_011_bindings.atlas.sha256);
for (const product of ["AU", "AG"]) {
  assert.equal(atlas.source_inventory.selected_series_by_product[product], 4);
  assert(atlas.coverage.global_label_counts_by_product_and_split[product].training);
  assert(atlas.coverage.global_label_counts_by_product_and_split[product].holdout);
}
assert.equal(atlas.proxy_definition.labels.join(","), "empirically_induced_not_authentic,training_only");
assert.equal(atlas.holdout_result.candidate_definition_frozen_before_holdout_application, true);
assert.equal(atlas.holdout_result.outcome_fields_present, false);
assert.equal(atlas.holdout_result.performance_metrics_present, false);
assertNoForbiddenKeys(atlas);

const publicText = [
  readFileSync(join(repoRoot, atlasPath), "utf8"),
  readFileSync(join(repoRoot, packet, "README.md"), "utf8")
].join("\n");
assert.doesNotMatch(publicText, /(?:^|[\s"'])\/(?:home|mnt|Users|var|tmp|root)\//, "public packet contains an absolute local path");
assert.doesNotMatch(publicText, /\b[a-z][a-z0-9._-]*198[0-9]\b/i, "public packet contains a local username");
assert.doesNotMatch(publicText, /(?:api[_-]?key|access[_-]?token|private[_-]?key|password)\s*[:=]\s*["'][^"']+/i, "public packet appears to contain a credential");

if (process.env.PA_FEITIAN_REGENERATE === "1") {
  const python = process.env.PA_FEITIAN_PYTHON;
  const dataRoot = process.env.QUANT_DATA_ROOT;
  assert(python, "PA_FEITIAN_PYTHON is required for regeneration");
  assert(dataRoot, "QUANT_DATA_ROOT is required for regeneration");
  const temp = mkdtempSync(join(tmpdir(), "pa-feitian-swing-line-"));
  const rebuilt = join(temp, "causal_swing_line_atlas_v1.json");
  try {
    execFileSync(
      python,
      [
        "src/scripts/build_pa_feitian_swing_line_induction.py",
        "--repo-root", ".",
        "--data-root", dataRoot,
        "--protocol", protocolPath,
        "--out", rebuilt
      ],
      { cwd: repoRoot, env: { ...process.env, PYTHONPATH: "src" }, stdio: "inherit" }
    );
    assert.deepEqual(readFileSync(rebuilt), readFileSync(join(repoRoot, atlasPath)));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
}

console.log("PA/Feitian causal swing-line induction verification passed");
