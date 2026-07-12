import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { validateRecoveryMatrix } from "./authentic_rule_recovery_validation_v1.mjs";

const here = fileURLToPath(new URL(".", import.meta.url));
const contract = JSON.parse(await readFile(new URL("./authentic_rule_recovery_contract_v1.json", import.meta.url), "utf8"));
const matrix = JSON.parse(await readFile(new URL("./authentic_rule_recovery_evidence_matrix_v1.json", import.meta.url), "utf8"));

assert.equal(contract.contract_id, "authentic_rule_recovery_contract_v1");
assert.equal(contract.completion_policy.fail_closed, true);
assert.deepEqual(contract.evidence_statuses, [
  "exact_source_supported",
  "ambiguous_source_supported",
  "inferred_only",
  "unresolved"
]);
validateRecoveryMatrix(matrix);

const text = [];
for (const file of await readdir(here)) {
  if (file.endsWith(".json") || file.endsWith(".mjs")) {
    text.push(await readFile(new URL(`./${file}`, import.meta.url), "utf8"));
  }
}
const joined = text.join("\n");
assert.doesNotMatch(joined, /(?:^|[\s"'])\/(?:home|mnt|Users|var|tmp|root)\//, "public artifact contains an absolute local path");
assert.doesNotMatch(joined, /\bdrwho1985\b/i, "public artifact contains a local username");
assert.doesNotMatch(joined, /(?:api[_-]?key|access[_-]?token|private[_-]?key|password)\s*[:=]\s*["'][^"']+/i, "public artifact appears to contain a credential");

execFileSync(process.execPath, ["--test", "test_authentic_rule_recovery_validation_v1.mjs"], { cwd: here, stdio: "inherit" });
console.log("authentic rule recovery v1 verification passed");
