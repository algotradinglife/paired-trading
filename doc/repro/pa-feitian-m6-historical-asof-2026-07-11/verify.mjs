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
assert.ok(python, "PA_FEITIAN_PYTHON is required");

const protocol = "docs/research/pa-feitian-m6-historical-asof-protocol-v1.json";
const packet = "doc/repro/pa-feitian-m6-historical-asof-2026-07-11";
const artifactPath = `${packet}/historical_asof_inputs_v1.json`;
const auditPath = `${packet}/coverage_feasibility_audit_v1.json`;
const files = {
  [protocol]: "sha256:55652f37b93db653b3259fb6e1a419565ba00d6101a83a66fb99b74edc57c7dc",
  [artifactPath]: "sha256:4eaa7251174a28fa1ae75bb0ca9425aaeb23725ff5f3f44e7b284bfd3f42cfe6",
  [auditPath]: "sha256:aeef4ad05ede7c4f988d1374cba560dc389453cdf99afbeb63782efe9acf77f1",
};

function bytes(path) {
  return readFileSync(resolve(repoRoot, path));
}

function json(path) {
  return JSON.parse(bytes(path).toString("utf8"));
}

function sha256(path) {
  return `sha256:${createHash("sha256").update(bytes(path)).digest("hex")}`;
}

for (const [path, expected] of Object.entries(files)) {
  assert.equal(sha256(path), expected, `${path} pinned hash`);
  assert.doesNotMatch(
    bytes(path).toString("utf8"),
    /\/(?:home|mnt|Users)\//,
    `${path} public path hygiene`,
  );
}

const artifact = json(artifactPath);
const audit = json(auditPath);
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
assert.deepEqual(audit.funnel, {
  data_blocked_series: 16,
  requested_series: 16,
  supported_series: 0,
});
assert.equal(audit.coverage.length, 16);
assert.ok(audit.coverage.every((row) => row.status === "data_blocked"));
assert.deepEqual(
  Object.fromEntries(audit.capabilities.map((row) => [row.capability, row.status])),
  {
    bid_ask: "blocked",
    causal_iv: "blocked",
    dd_line: "blocked",
    delta_dte: "blocked",
    option_price_cadence: "blocked",
    regime: "blocked",
    underlying_ohlcv_asof: "supported",
  },
);
assert.equal(audit.gate.faithful_feitian_ready, false);
assert.equal(audit.gate.performance_evaluation_allowed, false);
assert.equal(audit.gate.strategy_inference_allowed, false);
assert.equal(audit.gate.advance_m7, false);
for (const snapshot of artifact.snapshots) {
  const asOf = Date.parse(snapshot.decision_ts_utc);
  for (const series of snapshot.series) {
    assert.ok(series.bars.every((row) => Date.parse(row.timestamp) <= asOf));
  }
}

for (const sourcePath of [
  "src/engine/pa_feitian/historical_asof.py",
  "src/scripts/build_pa_feitian_historical_asof.py",
]) {
  const source = bytes(sourcePath).toString("utf8");
  assert.doesNotMatch(source, /\bdate\.today\s*\(/, `${sourcePath} date.today`);
  assert.doesNotMatch(source, /\bdatetime\.(?:now|utcnow)\s*\(/, `${sourcePath} implicit now`);
}

const temp = mkdtempSync(join(tmpdir(), "pa-feitian-m6-asof-"));
try {
  const emptyRoot = join(temp, "empty-quant-root");
  const rebuiltArtifact = join(temp, "historical_asof_inputs_v1.json");
  const rebuiltAudit = join(temp, "coverage_feasibility_audit_v1.json");
  execFileSync(
    python,
    [
      "src/scripts/build_pa_feitian_historical_asof.py",
      "--protocol", protocol,
      "--quant-data-root", emptyRoot,
      "--artifact-out", rebuiltArtifact,
      "--audit-out", rebuiltAudit,
      "--generated-at-utc", "2026-07-11T14:00:00Z",
      "--source-commit", "dacbec20d8c69d07aeaa64dde8f69c837a33632c",
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
  task: "t_efc47205",
  requested_series: 16,
  supported_series: 0,
  blocked_series: 16,
  faithful_feitian_ready: false,
  next_gate: "provision_exact_eight_underlying_files_then_rerun",
}));
