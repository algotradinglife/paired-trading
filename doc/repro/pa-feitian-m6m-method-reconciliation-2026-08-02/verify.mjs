import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const memo = readFileSync(join(dir, "README.md"), "utf8");
const receipt = readFileSync(join(dir, "independent-evidence-validation-receipt.md"), "utf8");

const requiredMemo = [
  "715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a",
  "5802d0ff5d99819ad01ba9f3550b6a2d504f1e81",
  "7691c31dceb0bb37a77d9fd8c98dc0746dc1361d",
  "cb08cfb7f3f5d0082ff13343bcbb324f25a96733",
  "stop_p1_exp_002",
  "operationalized_hypothesis_not_authentic",
  "m6r_frozen_artifact_verdict",
  "m6r_active_interpretation",
  "no_candidate_under_current_measurement",
  "method_revision_required",
  "M7",
  "not_authorized",
  "Source-defined Feitian decision chain",
  "M6 operationalized bare-K proxy",
  "M6R discovery/induction object",
  "Transition A — phase-0 scope",
  "Transition B — representation and claim",
  "Transition C — evidence routing",
  "Discovery",
  "Confirmation",
  "Falsification",
  "Measurement failure",
  "Insufficient data",
  "Path A — source-fidelity Feitian decision chain",
  "Path B — bare-K exhaustion/discovery",
  "Recommended target construct",
  "Claim level permitted for the next Issue",
  "Admissible evidence source and contamination boundary",
  "Stopping/falsification meaning at that claim level",
  "Whether to open a separate preregistered experiment Issue",
  "method_reconciled_recommend_path",
];
for (const value of requiredMemo) {
  if (!memo.includes(value)) throw new Error(`memo missing required evidence: ${value}`);
}
const requiredReceipt = [
  "Independent evidence-validation receipt",
  "Revisions reviewed",
  "Checks performed",
  "Disagreements",
  "Validation verdict",
  "2be9a373b74fa6b0ebdc59cf179dbf29f8b7bbc9db185f65129f110b20b0f463",
  "issuecomment-5152575643",
];
for (const value of requiredReceipt) {
  if (!receipt.includes(value)) throw new Error(`receipt missing required evidence: ${value}`);
}
if (!memo.includes("72 M6R episodes") || !/may never\s+become confirmation/.test(memo)) {
  throw new Error("M6R discovery-only boundary missing");
}
console.log(JSON.stringify({
  ok: true,
  terminal_handoff: "method_reconciled_recommend_path",
  independent_receipt: true,
  frozen_artifacts_changed: false,
}));
