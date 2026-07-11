import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packetDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const repoRoot = resolve(packetDir, "../../..");
const python = process.env.PA_FEITIAN_PYTHON;
const quantDataRoot = process.env.QUANT_DATA_ROOT;
assert.ok(python, "PA_FEITIAN_PYTHON is required");
assert.ok(quantDataRoot?.trim(), "QUANT_DATA_ROOT is required");

const protocolPath = "docs/research/pa-feitian-m6-historical-asof-protocol-v1.json";
const packet = "doc/repro/pa-feitian-m6-historical-asof-2026-07-11";
const artifactPath = `${packet}/historical_asof_inputs_v1.json`;
const auditPath = `${packet}/coverage_feasibility_audit_v1.json`;
const pinned = {
  [protocolPath]: "sha256:1ee6e334ada94fa928d311f3d7992d1708e4334c5b16e8e39b51ffedafcd7a1d",
  [artifactPath]: "sha256:0622d75ec43347c1143dfc5ea7088167acac397785a0504fd024398e907cadd6",
  [auditPath]: "sha256:3639f224e41e5fe205184088a0a0724529b2a6fc005d8e2d5410dbb5d20c07f8",
};

function bytes(path) {
  return readFileSync(resolve(repoRoot, path));
}

function json(path) {
  return JSON.parse(bytes(path).toString("utf8"));
}

function digest(content) {
  return `sha256:${createHash("sha256").update(content).digest("hex")}`;
}

for (const [path, expected] of Object.entries(pinned)) {
  assert.equal(digest(bytes(path)), expected, `${path} pinned hash`);
  assert.doesNotMatch(bytes(path).toString("utf8"), /\/(?:home|mnt|Users)\//, `${path} path hygiene`);
}

const protocol = json(protocolPath);
assert.equal(protocol.candidate_sources.length, 6);
for (const source of protocol.candidate_sources) {
  const candidate = readFileSync(resolve(quantDataRoot, "continuous", source.filename));
  assert.equal(digest(candidate), source.sha256, `${source.filename} source identity`);
}

const artifact = json(artifactPath);
const audit = json(auditPath);
assert.equal(artifact.candidate_data_eligible_for_score_today, false);
assert.deepEqual(artifact.guardrails, {
  as_of_required: true,
  continuous_synthesis: false,
  contract_reselection: false,
  contract_selection: "none",
  date_today_used: false,
  explicit_source_paths_only: true,
  future_rows_allowed: false,
  json_fallback: false,
  raw_store_scan: false,
});
assert.equal(audit.source_audit.length, 6);
assert.ok(audit.source_audit.every((row) => row.source_identity_pinned));
assert.ok(
  audit.source_audit.every((row) => row.candidate_status === "data_present_but_unverified"),
);
assert.equal(audit.aggregation_audit.length, 16);
assert.ok(audit.aggregation_audit.every((row) => row.strict_asof_passed));
assert.ok(audit.aggregation_audit.every((row) => row.minimum_rows_met));
assert.ok(
  audit.aggregation_audit.every((row) => row.status === "data_present_but_unverified"),
);
const fiveMinute = audit.source_audit.filter((row) => row.kind === "underlying_5min");
assert.deepEqual(
  Object.fromEntries(fiveMinute.map((row) => [row.product, row.quality_and_roll.roll_change_times])),
  { ag: { "00:00": 9, "09:05": 1 }, au: { "00:00": 23, "09:05": 3 } },
);
assert.ok(fiveMinute.every((row) => row.quality_and_roll.roll_provenance_status === "data_present_but_unverified"));
assert.deepEqual(
  Object.fromEntries(audit.capabilities.map((row) => [row.capability, row.status])),
  {
    bid_ask: "blocked",
    causal_iv: "data_present_but_unverified",
    dd_line: "blocked",
    delta_dte: "blocked",
    option_price_cadence: "blocked",
    regime: "blocked",
    roll_provenance: "data_present_but_unverified",
    source_identity_pinning: "supported",
    strict_asof_aggregation_mechanics: "supported",
    underlying_ohlcv_asof: "data_present_but_unverified",
  },
);
assert.equal(audit.gate.classification, "candidate_sources_present_but_unverified");
assert.equal(audit.gate.faithful_feitian_ready, false);
assert.equal(audit.gate.performance_evaluation_allowed, false);
assert.equal(audit.gate.strategy_inference_allowed, false);
assert.equal(audit.gate.advance_m7, false);
for (const snapshot of artifact.snapshots) {
  const asOf = Date.parse(snapshot.decision_ts_utc);
  assert.ok(snapshot.series.every((row) => Date.parse(row.last_timestamp) <= asOf));
}

for (const sourcePath of [
  "src/engine/pa_feitian/historical_asof.py",
  "src/engine/pa_feitian/continuous_source_audit.py",
  "src/scripts/audit_pa_feitian_continuous_sources.py",
]) {
  const source = bytes(sourcePath).toString("utf8");
  assert.doesNotMatch(source, /\bdate\.today\s*\(/, `${sourcePath} date.today`);
  assert.doesNotMatch(source, /\bdatetime\.(?:now|utcnow)\s*\(/, `${sourcePath} implicit now`);
  assert.doesNotMatch(source, /\.glob\s*\(/, `${sourcePath} directory discovery`);
}

const temp = mkdtempSync(join(tmpdir(), "pa-feitian-m6-asof-audit-"));
try {
  const rebuiltArtifact = join(temp, "historical_asof_inputs_v1.json");
  const rebuiltAudit = join(temp, "coverage_feasibility_audit_v1.json");
  execFileSync(
    python,
    [
      "src/scripts/audit_pa_feitian_continuous_sources.py",
      "--protocol", protocolPath,
      "--continuous-root", resolve(quantDataRoot, "continuous"),
      "--artifact-out", rebuiltArtifact,
      "--audit-out", rebuiltAudit,
      "--generated-at-utc", "2026-07-11T16:00:00Z",
      "--source-commit", "9f5910e8a9b5708603d6bd183be07b30e7ea3942",
    ],
    { cwd: repoRoot, env: { ...process.env, PYTHONPATH: "src" }, stdio: "pipe" },
  );
  assert.deepEqual(readFileSync(rebuiltArtifact), bytes(artifactPath));
  assert.deepEqual(readFileSync(rebuiltAudit), bytes(auditPath));
} finally {
  rmSync(temp, { recursive: true, force: true });
}

console.log(JSON.stringify({
  ok: true,
  task: "t_f4920060",
  sources: 6,
  aggregation_cells: 16,
  promoted: ["source_identity_pinning", "strict_asof_aggregation_mechanics"],
  quarantined: ["underlying_ohlcv_asof", "roll_provenance", "causal_iv"],
  blocked: ["regime", "delta_dte", "option_price_cadence", "dd_line", "bid_ask"],
  advance_m7: false,
}));
