import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const packet = "doc/repro/pa-feitian-m6-premium-k-response-2026-07-13";
const protocolPath = "docs/research/pa-feitian-m6-premium-k-response-protocol-v1.json";
const atlasPath = `${packet}/premium_k_response_atlas_v1.json`;
const protocol = JSON.parse(readFileSync(join(repoRoot, protocolPath), "utf8"));
const atlas = JSON.parse(readFileSync(join(repoRoot, atlasPath), "utf8"));
const forbidden = new Set([
  "open", "high", "low", "close", "raw_bar", "price", "chart", "anchor",
  "projection", "tolerance", "return", "response", "pnl", "premium_r",
  "contract", "filename", "bid", "ask", "delta", "greeks", "dte", "execution"
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

assert.equal(protocol.schema_version, "pa_feitian_m6_premium_k_response_protocol_v1");
for (const family of ["m6_exp_011", "m6_exp_012"]) {
  for (const name of ["protocol", "atlas"]) {
    const binding = protocol.read_only_bindings[family][name];
    assert.equal(sha256(join(repoRoot, binding.path)), binding.sha256, `${family} ${name} binding mismatch`);
  }
}
assert.equal(atlas.schema_version, "pa_feitian_m6_premium_k_response_atlas_v1");
assert.deepEqual(atlas.study_labels, ["empirical", "exploratory", "non-authentic", "non-executable"]);
assert.equal(atlas.protocol.path, protocolPath);
assert.equal(atlas.protocol.sha256, sha256(join(repoRoot, protocolPath)));
assert.equal(atlas.training_response_matrix.length, 18);
assert.equal(atlas.training_candidate_freeze.candidate_set.length, 0);
assert.equal(atlas.holdout_application.status, "not_applied_no_training_candidates");
assert.deepEqual(atlas.holdout_application.candidate_response_matrix, []);
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
  const temp = mkdtempSync(join(tmpdir(), "pa-feitian-premium-k-response-"));
  const rebuilt = join(temp, "premium_k_response_atlas_v1.json");
  try {
    execFileSync(
      python,
      [
        "src/scripts/build_pa_feitian_premium_k_response.py",
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

console.log("PA/Feitian premium-K response verification passed");
