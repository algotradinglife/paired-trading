import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const memoPath = join(dirname(fileURLToPath(import.meta.url)), "decision_v1.json");
const memo = JSON.parse(readFileSync(memoPath, "utf8"));

function sha256(path) {
  return `sha256:${createHash("sha256").update(readFileSync(join(root, path))).digest("hex")}`;
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, sortKeys(value[key])]),
    );
  }
  return value;
}

function canonicalJsonSha256(path) {
  const value = JSON.parse(readFileSync(join(root, path), "utf8"));
  const canonical = JSON.stringify(sortKeys(value));
  return `sha256:${createHash("sha256").update(canonical).digest("hex")}`;
}

const expected = {
  issue_59_audit_artifact_sha256: sha256("doc/repro/pa-feitian-m6-native-source-registration-2026-07-30/native_source_registration_audit_v1.json"),
  issue_59_registration_contract_sha256: sha256("docs/research/pa-feitian-m6-native-source-registration-contract-v1.json"),
  p1_exp_002_registry_sha256: sha256("docs/research/pa-feitian-phase1-hypothesis-registry-v2.json"),
  p1_exp_002_registry_lock_sha256: sha256("docs/research/pa-feitian-phase1-hypothesis-registry-v2.lock.json"),
  historical_gate_contract_sha256: canonicalJsonSha256(
    "docs/research/pa-feitian-m6-historical-backtest-data-gate-contract-v1.json",
  ),
};

if (memo.schema_version !== "pa_feitian_phase1_p1_exp_002_decision_v1") throw new Error("schema drift");
if (memo.issue_number !== 60 || memo.verdict !== "stop_p1_exp_002") throw new Error("decision drift");
for (const [key, value] of Object.entries(expected)) {
  if (memo.evidence_bindings[key] !== value) throw new Error(`evidence binding drift: ${key}`);
}
if (memo.evidence_bindings.approved_native_source_manifest !== null) throw new Error("native manifest must remain absent");
const c = memo.public_safe_classification;
if (c.captured_source_files !== 978 || c.captured_source_rows !== 2702545 || c.required_matrix_cells !== 18) throw new Error("source accounting drift");
if (c.intraday_cells_without_independent_provider_bar_end_semantics !== 12 || c.intraday_unexplained_timestamp_rows !== 521090) throw new Error("intraday blocker drift");
if (c.daily_price_findings.total !== 169 || c.daily_price_findings.family_aggregate["CZCE.TA"] !== 76 || c.daily_price_findings.family_aggregate["CZCE.MA"] !== 93) throw new Error("daily blocker drift");
if (memo.dependency_recommendation.issue_51 !== "remain_blocked") throw new Error("dependency drift");
console.log(JSON.stringify({ ok: true, issue: 60, verdict: memo.verdict, source_files: c.captured_source_files, source_rows: c.captured_source_rows }));
