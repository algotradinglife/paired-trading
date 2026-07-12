import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const pairedRepo = process.env.PAIRED_REPO ?? process.cwd();
const quantDataRoot = process.env.QUANT_DATA_ROOT;
const quantRepo = process.env.QUANT_REPO;
const python = process.env.PA_FEITIAN_PYTHON;
assert.ok(quantDataRoot, "QUANT_DATA_ROOT is required");
assert.ok(quantRepo, "QUANT_REPO is required");
assert.ok(python, "PA_FEITIAN_PYTHON is required");

const contractRel = "docs/research/pa-feitian-m6-option-input-audit-contract-v1.json";
const artifactRel = "doc/repro/pa-feitian-m6-option-input-audit-2026-07-12/option_input_capability_audit_v1.json";
const expected = {
  contract: "03afcc9b5760eab50ea66f0163ef17e46c8ecc2f3924fd1ca9e7939142bc861b",
  artifact: "892b0926913bff0665c080dd6a5ba8459ccfe0ca3c4e91cb1441706a778b2753",
};
const digest = (file) => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const contractPath = path.join(pairedRepo, contractRel);
const artifactPath = path.join(pairedRepo, artifactRel);
assert.equal(digest(contractPath), expected.contract);
assert.equal(digest(artifactPath), expected.artifact);

const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
assert.equal(artifact.hermes_task, "t_4c2ae680");
assert.deepEqual(artifact.inventory.bar_roots.map((row) => row.parsed_option_files), [4935, 4935, 4935]);
assert.deepEqual(artifact.inventory.bar_roots.map((row) => row.au_ag_prefixed_parquet_candidates), [5040, 5040, 5040]);
assert.equal(artifact.inventory.parsed_contract_set_count, 4935);
assert.equal(artifact.inventory.greeks_sibling_files, 0);
assert.deepEqual(
  artifact.capability_findings.map((row) => row.state),
  ["data_present_but_unverified", "data_present_but_unverified", "missing", "missing", "missing", "missing"],
);
assert.equal(artifact.decision.faithful_option_corpus, "blocked");
assert.equal(artifact.decision.option_corpus_generation_warranted_now, false);
assert.ok(!JSON.stringify(artifact).includes("/home/"));
assert.ok(!JSON.stringify(artifact).includes("/mnt/"));

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "pa-feitian-option-audit-"));
const rebuilt = path.join(temporary, "option_input_capability_audit_v1.json");
try {
  const result = spawnSync(
    python,
    [
      path.join(pairedRepo, "src/scripts/build_pa_feitian_option_input_audit.py"),
      "--contract", contractPath,
      "--quant-data-root", quantDataRoot,
      "--quant-repo", quantRepo,
      "--paired-repo", pairedRepo,
      "--output", rebuilt,
    ],
    {
      cwd: pairedRepo,
      env: { ...process.env, PYTHONPATH: path.join(pairedRepo, "src") },
      encoding: "utf8",
    },
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.deepEqual(fs.readFileSync(rebuilt), fs.readFileSync(artifactPath));
} finally {
  fs.rmSync(temporary, { recursive: true, force: true });
}

console.log(JSON.stringify({ ok: true, parsed_option_file_observations: 14805, faithful_option_corpus: "blocked" }));
