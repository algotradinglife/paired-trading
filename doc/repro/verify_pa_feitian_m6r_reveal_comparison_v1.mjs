import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import assert from "node:assert/strict";

const dir = dirname(fileURLToPath(import.meta.url));
const comparisonPath = join(dir, "pa-feitian-m6r-reveal-comparison-v1.json");
const blindPath = join(dir, "pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31", "blind_annotations_v1.json");
const comparison = JSON.parse(readFileSync(comparisonPath, "utf8"));
const blind = JSON.parse(readFileSync(blindPath, "utf8"));
const contract = JSON.parse(readFileSync(join(dir, "pa-feitian-m6r-reveal-comparison-contract-v1.json"), "utf8"));
const decodedPath = process.argv[2];
if (!decodedPath) throw new Error("explicit decoded reveal path is required");
const hash = (path) => `sha256:${createHash("sha256").update(readFileSync(path)).digest("hex")}`;
if (comparison.blind_annotations_sha256 !== hash(blindPath)) throw new Error("blind annotation hash drift");
if (comparison.contract_schema_version !== contract.schema_version || comparison.blind_pack_sha256 !== contract.blind_pack_sha256 || comparison.sealed_reveal_artifact_sha256 !== contract.sealed_reveal_artifact_sha256 || comparison.sealed_reveal_payload_sha256 !== contract.sealed_reveal_payload_sha256) throw new Error("contract hash drift");
if (comparison.episode_count !== 72 || comparison.rows.length !== 72) throw new Error("episode count drift");
if (JSON.stringify(comparison.horizons) !== JSON.stringify([1, 5, 10, 20])) throw new Error("fixed horizon drift");
const expected = blind.annotations.map((item) => item.episode_id);
const seen = new Set();
for (const [index, row] of comparison.rows.entries()) {
  if (row.episode_id !== expected[index] || seen.has(row.episode_id)) throw new Error("ID accounting drift");
  for (const key of ["context", "local_turn_count", "range_behavior", "bar_0_shape"]) {
    if (typeof row[key] !== "string" && key !== "local_turn_count") throw new Error(`descriptor missing: ${key}`);
    if (key === "local_turn_count" && !Number.isInteger(row[key])) throw new Error("turn count drift");
  }
  if (!["candidate_activity", "ordinary_control"].includes(row.sampling_role)) throw new Error("role drift");
  for (const horizon of comparison.horizons) for (const metric of ["close_change_pct", "future_high_change_pct", "future_low_change_pct"]) if (typeof row.horizons[String(horizon)]?.[metric] !== "number") throw new Error("horizon metric drift");
  seen.add(row.episode_id);
}
if (seen.size !== 72) throw new Error("incomplete ID accounting");
if (comparison.verdict !== "no_candidate" || comparison.candidate_count !== 0) throw new Error("verdict drift");
if (!comparison.aggregates || comparison.aggregates.sampling_role.candidate_activity !== 36 || comparison.aggregates.sampling_role.ordinary_control !== 36) throw new Error("aggregate drift");
const tempDir = mkdtempSync(join("/tmp", "m6r-verify-"));
const rebuiltPath = join(tempDir, "comparison.json");
execFileSync("python3", [join(dir, "..", "..", "src", "scripts", "build_pa_feitian_m6r_reveal_comparison_v1.py"), "--decoded-reveal", decodedPath, "--sealed-reveal", join(dir, "pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31", "sealed_reveal_pack_v1.json"), "--blind-pack", join(dir, "pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31", "blind_episode_pack_v1.json"), "--blind-annotations", blindPath, "--contract", join(dir, "pa-feitian-m6r-reveal-comparison-contract-v1.json"), "--output", rebuiltPath]);
if (readFileSync(rebuiltPath).toString() !== readFileSync(comparisonPath).toString()) throw new Error("builder recomputation mismatch");
rmSync(tempDir, { recursive: true, force: true });
function validateCandidate(candidate) {
  if (candidate.verdict !== "no_candidate") throw new Error("verdict drift");
  if (candidate.rows[0].context !== comparison.rows[0].context) throw new Error("descriptor drift");
  if (candidate.rows[0].horizons["1"].close_change_pct !== comparison.rows[0].horizons["1"].close_change_pct) throw new Error("metric drift");
  if (candidate.rows[0].episode_id !== comparison.rows[0].episode_id) throw new Error("ID drift");
  if (candidate.blind_pack_sha256 !== contract.blind_pack_sha256) throw new Error("source hash drift");
  if (candidate.aggregates.sampling_role.candidate_activity !== comparison.aggregates.sampling_role.candidate_activity) throw new Error("aggregate drift");
  if (JSON.stringify(candidate.horizons) !== JSON.stringify(comparison.horizons)) throw new Error("horizon drift");
  if (!Array.isArray(candidate.candidate_floor_audit.categories) || candidate.candidate_floor_audit.categories.length === 0) throw new Error("candidate audit drift");
  if (candidate.candidate_floor_audit.category_count !== 27 || candidate.candidate_floor_audit.structural_floor_pass_count !== 15 || candidate.candidate_floor_audit.mixed_sign_horizon_20_count !== 15) throw new Error("candidate audit count drift");
}
validateCandidate(comparison);
if (process.argv.includes("--negative-tests")) {
  const guards = [["descriptor", (x) => x.rows[0].context === comparison.rows[0].context], ["metric", (x) => x.rows[0].horizons["1"].close_change_pct === comparison.rows[0].horizons["1"].close_change_pct], ["id-order", (x) => x.rows[0].episode_id === expected[0]], ["source-hash", (x) => x.blind_pack_sha256 === contract.blind_pack_sha256], ["aggregate", (x) => x.aggregates.sampling_role.candidate_activity === 36], ["horizon", (x) => JSON.stringify(x.horizons) === JSON.stringify(contract.fixed_horizons)], ["verdict", (x) => x.verdict === "no_candidate"], ["candidate-audit", (x) => x.candidate_floor_audit.category_count === 27]];
  for (const [label, guard] of guards) { const copy = structuredClone(comparison); if (label === "descriptor") copy.rows[0].context = "tampered"; if (label === "metric") copy.rows[0].horizons["1"].close_change_pct += 1; if (label === "id-order") copy.rows[0].episode_id = "tampered"; if (label === "source-hash") copy.blind_pack_sha256 = "sha256:bad"; if (label === "aggregate") copy.aggregates.sampling_role.candidate_activity += 1; if (label === "horizon") copy.horizons = [1]; if (label === "verdict") copy.verdict = "candidate_hypotheses_frozen"; if (label === "candidate-audit") copy.candidate_floor_audit.category_count = 0; assert.notEqual(guard(copy), true, `${label} mutation was not changed`); assert.throws(() => validateCandidate(copy), `${label} negative mutation accepted`); }
}
console.log(JSON.stringify({ ok: true, episodes: seen.size, horizons: comparison.horizons, verdict: "no_candidate", candidates: 0 }));
