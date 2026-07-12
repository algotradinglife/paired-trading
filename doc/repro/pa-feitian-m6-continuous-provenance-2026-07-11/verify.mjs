import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const python = process.env.PA_FEITIAN_PYTHON;
const rawRoot = process.env.QUANT_DATA_ROOT;
const quantRepo = process.env.QUANT_REPO;
const pairedRepo = process.env.PAIRED_REPO;
assert.ok(python, "PA_FEITIAN_PYTHON is required");
assert.ok(rawRoot, "QUANT_DATA_ROOT is required");
assert.ok(quantRepo, "QUANT_REPO is required");
assert.ok(pairedRepo, "PAIRED_REPO is required");

const manifestPath = "doc/repro/pa-feitian-m6-continuous-provenance-2026-07-11/continuous_provenance_manifest_v1.json";
const protocolPath = "docs/research/pa-feitian-m6-historical-asof-protocol-v1.json";
const digest = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
const bytes = (path) => readFileSync(resolve(repoRoot, path));
assert.equal(
  digest(bytes(manifestPath)),
  "sha256:a239a15d7f11bfacac0565a32e6f6bb5895ff8c5815cf5138926722590ffd3a3",
  "manifest hash",
);
assert.equal(
  digest(bytes(protocolPath)),
  "sha256:1ee6e334ada94fa928d311f3d7992d1708e4334c5b16e8e39b51ffedafcd7a1d",
  "M6-HIST-002A protocol hash",
);

const manifest = JSON.parse(bytes(manifestPath).toString("utf8"));
assert.equal(manifest.hermes_task, "t_6df19e2b");
assert.equal(manifest.bound_candidates.length, 2);
assert.equal(manifest.quarantined_candidates.length, 4);
assert.ok(manifest.bound_candidates.every((row) => !row.eligible_for_score_today));
assert.ok(manifest.bound_candidates.every((row) => row.raw_acquisition_lineage.status === "quarantined"));
assert.ok(manifest.bound_candidates.every((row) => row.embedded_main_month_is_roll.status === "quarantined"));
assert.ok(manifest.quarantined_candidates.every((row) => !row.manifest_binding_attempted));
assert.equal(manifest.capability_boundary.full_sample_atr_regime, "blocked");
assert.equal(manifest.capability_boundary.performance_evaluation_allowed, false);
assert.equal(manifest.capability_boundary.advance_m7, false);

const output = execFileSync(
  python,
  [
    "src/scripts/verify_pa_feitian_continuous_provenance.py",
    "--manifest", manifestPath,
    "--protocol", protocolPath,
    "--raw-root", rawRoot,
    "--quant-repo", quantRepo,
    "--paired-repo", pairedRepo,
  ],
  { cwd: repoRoot, env: { ...process.env, PYTHONPATH: "src" }, encoding: "utf8" },
);
const result = JSON.parse(output);
assert.equal(result.ok, true);
assert.equal(result.bound.length, 2);
assert.equal(result.quarantined.length, 4);
assert.equal(result.advance_m7, false);
console.log(JSON.stringify({ task: "t_6df19e2b", ...result }));
