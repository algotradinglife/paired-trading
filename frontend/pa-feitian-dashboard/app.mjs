const SNAPSHOT_URL = "./fixtures/pa_feitian_snapshot_v1.json";
const MANIFEST_URL = "./fixtures/pa_feitian_run_manifest_v1.json";

export const SUPPORTED_CONTRACT_VERSIONS = new Set([
  "pa_feitian_snapshot_v1",
  "pa_feitian_snapshot_v0",
]);
export const SUPPORTED_DECISION_INTENT_VERSIONS = new Set(["pa_feitian_decision_intent_v1"]);
export const SUPPORTED_PREMIUM_OUTCOME_VERSIONS = new Set(["pa_feitian_premium_outcome_v1"]);

export const SNAPSHOT_MODE_DEFINITIONS = {
  fixture: "Fixture snapshot",
  generated: "Generated snapshot",
  review: "Review snapshot",
};

const REVIEW_MODE_STATUSES = new Set(["approved", "changes_requested", "rejected"]);

export const STATUS_DEFINITIONS = {
  keep: "Production-eligible signal",
  drop: "Rejected by contract policy",
  advisory: "Context signal only",
  data_blocked: "Waiting on explicit option data",
  model_dominated: "Model output dominates raw edge",
};

export const TRACE_NODE_STATUS_DEFINITIONS = {
  pass: "Node evidence satisfied",
  fail: "Node evidence rejected the path",
  blocked: "Node is waiting on causal data",
  advisory: "Node annotates the decision",
  not_applicable: "Node does not apply",
};

export const DECISION_STATE_DEFINITIONS = {
  reject: "Rejected by decision-intent readiness",
  watch: "Watch only; readiness remains incomplete",
  armed_watch: "Armed watch; near-ready but still blocked",
  trade_ready: "Trade-ready sidecar state",
  observation_runner: "Observation-only runner diagnostic",
};

export const DATA_ACCESS_DEFINITIONS = {
  real_data_available: "Explicit generated scorecard artifact",
  fixture_fallback: "Deterministic fixture fallback",
  data_blocked: "No generated data artifact available",
  unknown: "Data access was not classified",
};

export const PREMIUM_OUTCOME_STATUS_DEFINITIONS = {
  observed: "Observed premium path",
  ambiguous: "Observed bars with unresolved ordering",
  data_blocked: "Required premium data unavailable",
  not_evaluable: "Harness preconditions failed",
};

export const PREMIUM_PRICE_SOURCE_DEFINITIONS = {
  observed: "Observed premium sidecar evidence",
  model_derived: "Model-derived evidence only",
  unavailable: "Premium evidence unavailable",
};

export const HASH_STATUS_DEFINITIONS = {
  match: "Manifest hash link matches",
  mismatch: "Manifest hash link differs",
  missing: "Hash metadata is missing",
  untracked: "No manifest hash link recorded",
};

const DECISION_INTENT_EMPTY_STATE = {
  status: "not_referenced",
  schemaVersion: null,
  generatedAt: null,
  sourceCommit: null,
  provenance: {},
  artifact: null,
  intents: [],
  intentsBySignalId: new Map(),
  warnings: [],
  stateCounts: {},
  executionAllowedCount: 0,
  unmatchedSignalIds: [],
  duplicateSignalIds: [],
  error: null,
};

const PREMIUM_OUTCOME_EMPTY_STATE = {
  status: "not_referenced",
  schemaVersion: null,
  generatedAt: null,
  sourceCommit: null,
  provenance: {},
  artifact: null,
  outcomes: [],
  outcomesBySignalId: new Map(),
  warnings: [],
  evaluationCounts: {},
  duplicateOutcomeIds: [],
  duplicateSourceSignalIds: [],
  unmatchedSourceSignalIds: [],
  missingSignalIds: [],
  error: null,
};

const OPTIONAL_FIELDS = [
  ["Decision", "decision"],
  [
    "Decision trace",
    (signal) =>
      hasDecisionTraceV1Nodes(signal?.decision_trace_v1) ? "decision_trace_v1.nodes" : signal?.decision_trace,
  ],
  ["Option strike", "option_leg.strike"],
  ["Option DTE", "option_leg.dte"],
  ["OTM rank", "option_leg.otm_rank"],
  ["Delta estimate", "option_leg.delta_estimate"],
  ["IV rank", "iv_regime.iv_rank"],
  ["Option runner outcome", "option_runner_outcome"],
  ["Proxy outcome", "proxy_outcome"],
];

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function getPath(object, path) {
  return path.split(".").reduce((cursor, key) => {
    if (cursor === null || cursor === undefined) {
      return undefined;
    }
    return cursor[key];
  }, object);
}

function isMissing(value) {
  return value === null || value === undefined || value === "";
}

function labelValue(value) {
  if (isMissing(value)) {
    return '<span class="missing">Missing</span>';
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "object") {
    return escapeHtml(JSON.stringify(value));
  }
  return escapeHtml(value);
}

function percentageValue(value) {
  if (isMissing(value)) {
    return '<span class="missing">Missing</span>';
  }
  if (typeof value === "number") {
    return `${escapeHtml(value)}%`;
  }
  return escapeHtml(value);
}

function numberValue(value, maximumFractionDigits = 3) {
  if (isMissing(value)) {
    return '<span class="missing">Missing</span>';
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return escapeHtml(
      new Intl.NumberFormat("en-US", {
        maximumFractionDigits,
      }).format(value),
    );
  }
  return escapeHtml(value);
}

function traceValue(value) {
  if (value === undefined) {
    return '<span class="missing">Missing</span>';
  }
  if (value === null) {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "object") {
    return escapeHtml(JSON.stringify(value));
  }
  return escapeHtml(value);
}

function formatDate(value) {
  if (!value) {
    return "Missing";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return escapeHtml(value);
  }
  return date.toISOString().replace(".000Z", "Z");
}

function statusBadge(status) {
  const normalized = STATUS_DEFINITIONS[status] ? status : "drop";
  return `<span class="badge ${escapeHtml(normalized)}">${escapeHtml(status || "unknown")}</span>`;
}

function traceNodeBadge(status) {
  const normalized = TRACE_NODE_STATUS_DEFINITIONS[status] ? status : "unknown";
  return `<span class="trace-badge ${escapeHtml(normalized)}">${escapeHtml(status || "unknown")}</span>`;
}

function decisionStateBadge(state) {
  const normalized = DECISION_STATE_DEFINITIONS[state] ? state : "unknown";
  return `<span class="intent-badge state ${escapeHtml(normalized)}">${escapeHtml(state || "unknown")}</span>`;
}

function executionBadge(allowed) {
  if (allowed === true) {
    return '<span class="intent-badge execution allowed">execution_allowed: true</span>';
  }
  if (allowed === false) {
    return '<span class="intent-badge execution blocked">execution_allowed: false</span>';
  }
  return '<span class="intent-badge execution unknown">execution_allowed: Missing</span>';
}

function readinessBadge(value) {
  const normalized = (value || "unknown").replaceAll("_", "-");
  return `<span class="intent-badge readiness ${escapeHtml(normalized)}">${escapeHtml(value || "unknown")}</span>`;
}

function premiumOutcomeBadge(status) {
  const normalized = PREMIUM_OUTCOME_STATUS_DEFINITIONS[status] ? status : "unknown";
  return `<span class="outcome-badge ${escapeHtml(normalized)}">${escapeHtml(status || "unknown")}</span>`;
}

function premiumPriceSourceBadge(sourceType) {
  const normalized = PREMIUM_PRICE_SOURCE_DEFINITIONS[sourceType] ? sourceType : "unknown";
  return `<span class="price-source-badge ${escapeHtml(normalized)}">${escapeHtml(sourceType || "unknown")}</span>`;
}

function dataAccessBadge(status) {
  const normalized = DATA_ACCESS_DEFINITIONS[status] ? status : "unknown";
  return `<span class="data-access-badge ${escapeHtml(normalized)}">${escapeHtml(status || "unknown")}</span>`;
}

function hashStatusBadge(status) {
  const normalized = HASH_STATUS_DEFINITIONS[status] ? status : "missing";
  return `<span class="hash-badge ${escapeHtml(normalized)}">${escapeHtml(status || "missing")}</span>`;
}

function modeBadge(mode) {
  const normalized = SNAPSHOT_MODE_DEFINITIONS[mode] ? mode : "fixture";
  return `<span class="mode-badge ${escapeHtml(normalized)}">${escapeHtml(SNAPSHOT_MODE_DEFINITIONS[normalized])}</span>`;
}

function jsonBlock(value) {
  return `<pre>${escapeHtml(JSON.stringify(value ?? null, null, 2))}</pre>`;
}

function countStatuses(summary, signals) {
  const counts = Object.fromEntries(Object.keys(STATUS_DEFINITIONS).map((status) => [status, 0]));
  const summaryCounts = summary && typeof summary.by_status === "object" ? summary.by_status : null;

  if (summaryCounts) {
    for (const [status, count] of Object.entries(summaryCounts)) {
      counts[status] = Number(count) || 0;
    }
    return counts;
  }

  for (const signal of signals) {
    const status = signal.status || "drop";
    counts[status] = (counts[status] || 0) + 1;
  }
  return counts;
}

export function missingOptionalFields(signal) {
  return OPTIONAL_FIELDS.filter(([, accessor]) => {
    const value = typeof accessor === "function" ? accessor(signal) : getPath(signal, accessor);
    return isMissing(value);
  }).map(([label]) => label);
}

function hasDecisionTraceV1Nodes(trace) {
  return Boolean(trace && Array.isArray(trace.nodes) && trace.nodes.length > 0);
}

export function normalizeDecisionTrace(signal) {
  const trace = signal?.decision_trace_v1;
  if (hasDecisionTraceV1Nodes(trace)) {
    return {
      kind: "decision_trace_v1",
      traceVersion: trace.trace_version || "decision_trace_v1",
      action: trace.action,
      status: trace.status,
      summary: trace.summary || {},
      inputRefs: Array.isArray(trace.input_refs) ? trace.input_refs : [],
      nodes: trace.nodes,
    };
  }

  return {
    kind: "legacy",
    text: signal?.decision_trace ?? null,
    nodes: [],
  };
}

function normalizeRenderOptions(options) {
  if (!options) {
    return {};
  }
  if (options.schema_version === "pa_feitian_run_manifest_v1") {
    return { manifest: options };
  }
  if (options.schema_version === "pa_feitian_decision_intent_v1") {
    return { decisionIntent: options };
  }
  if (options.schema_version === "pa_feitian_premium_outcome_v1") {
    return { premiumOutcome: options };
  }
  return options;
}

export function normalizeRunManifest(manifest) {
  if (!manifest || manifest.schema_version !== "pa_feitian_run_manifest_v1") {
    return null;
  }

  return {
    schemaVersion: manifest.schema_version,
    generatedAt: manifest.generated_at_utc,
    sourceCommit: manifest.source_commit,
    scorecardArtifact: manifest.scorecard_artifact || null,
    snapshotArtifact: manifest.snapshot_artifact || null,
    decisionIntentArtifact: manifest.decision_intent_artifact || null,
    premiumOutcomeArtifact: manifest.premium_outcome_artifact || null,
    cliArgs: Array.isArray(manifest.cli_args) ? manifest.cli_args : [],
    runConfig: manifest.run_config || {},
    dataAccess: manifest.data_access || {},
    inputHashes: manifest.input_hashes || {},
    outputHashes: manifest.output_hashes || {},
    frontendCopyPath: manifest.frontend_copy_path ?? null,
    reviewState: manifest.review_state || {},
  };
}

function classifyHashStatus(actualHash, expectedHash) {
  if (!actualHash) {
    return "missing";
  }
  if (!expectedHash) {
    return "untracked";
  }
  return actualHash === expectedHash ? "match" : "mismatch";
}

function buildArtifactProvenanceRow(label, artifact, expectedHash, hashSource) {
  return {
    label,
    kind: artifact?.kind || null,
    path: artifact?.path || null,
    schemaVersion: artifact?.schema_version || null,
    actualHash: artifact?.sha256 || null,
    expectedHash: expectedHash || null,
    hashSource,
    hashStatus: classifyHashStatus(artifact?.sha256, expectedHash),
  };
}

function buildCopyProvenanceRow(label, { kind, path, actualHash, expectedHash, hashSource, schemaVersion = null }) {
  return {
    label,
    kind,
    path: path || null,
    schemaVersion,
    actualHash: actualHash || null,
    expectedHash: expectedHash || null,
    hashSource,
    hashStatus: classifyHashStatus(actualHash, expectedHash),
  };
}

function buildArtifactProvenanceRows(manifest) {
  if (!manifest) {
    return [];
  }

  const rows = [
    buildArtifactProvenanceRow(
      "Scorecard artifact",
      manifest.scorecardArtifact,
      manifest.inputHashes.scorecard_artifact,
      "input_hashes.scorecard_artifact",
    ),
    buildArtifactProvenanceRow(
      "Snapshot artifact",
      manifest.snapshotArtifact,
      manifest.outputHashes.snapshot_artifact,
      "output_hashes.snapshot_artifact",
    ),
    buildCopyProvenanceRow("Frontend snapshot copy", {
      kind: "snapshot_copy",
      path: manifest.frontendCopyPath,
      actualHash: manifest.outputHashes.frontend_copy,
      expectedHash: manifest.snapshotArtifact?.sha256,
      hashSource: "output_hashes.frontend_copy",
      schemaVersion: manifest.snapshotArtifact?.schema_version,
    }),
    buildArtifactProvenanceRow(
      "Decision intent artifact",
      manifest.decisionIntentArtifact,
      manifest.outputHashes.decision_intent_artifact,
      "output_hashes.decision_intent_artifact",
    ),
    buildArtifactProvenanceRow(
      "Premium outcome artifact",
      manifest.premiumOutcomeArtifact,
      manifest.outputHashes.premium_outcome_artifact,
      "output_hashes.premium_outcome_artifact",
    ),
  ];

  if (manifest.decisionIntentArtifact || manifest.outputHashes.frontend_decision_intent_copy) {
    rows.push(
      buildCopyProvenanceRow("Decision intent frontend copy", {
        kind: "decision_intent_copy",
        path: manifest.decisionIntentArtifact?.path,
        actualHash: manifest.outputHashes.frontend_decision_intent_copy,
        expectedHash: manifest.decisionIntentArtifact?.sha256,
        hashSource: "output_hashes.frontend_decision_intent_copy",
        schemaVersion: manifest.decisionIntentArtifact?.schema_version,
      }),
    );
  }

  if (manifest.premiumOutcomeArtifact || manifest.outputHashes.frontend_premium_outcome_copy) {
    rows.push(
      buildCopyProvenanceRow("Premium outcome frontend copy", {
        kind: "premium_outcome_copy",
        path: manifest.premiumOutcomeArtifact?.path,
        actualHash: manifest.outputHashes.frontend_premium_outcome_copy,
        expectedHash: manifest.premiumOutcomeArtifact?.sha256,
        hashSource: "output_hashes.frontend_premium_outcome_copy",
        schemaVersion: manifest.premiumOutcomeArtifact?.schema_version,
      }),
    );
  }

  return rows;
}

function chooseHashStatus(rows, kindFragment, fallbackLabel, fallbackSummary) {
  const sidecarRows = rows.filter((row) => row.kind?.includes(kindFragment));
  if (!sidecarRows.length) {
    return {
      label: fallbackLabel,
      status: "missing",
      summary: fallbackSummary,
    };
  }
  const priority = ["mismatch", "missing", "untracked", "match"];
  const selected =
    priority.map((status) => sidecarRows.find((row) => row.hashStatus === status)).find(Boolean) ||
    sidecarRows[0];
  return {
    label: selected.label,
    status: selected.hashStatus,
    summary: HASH_STATUS_DEFINITIONS[selected.hashStatus],
  };
}

function chooseSidecarHashStatus(rows) {
  return chooseHashStatus(
    rows,
    "decision_intent",
    "Decision intent artifact",
    "No decision-intent sidecar artifact is referenced.",
  );
}

function choosePremiumOutcomeHashStatus(rows) {
  return chooseHashStatus(
    rows,
    "premium_outcome",
    "Premium outcome artifact",
    "No premium outcome sidecar artifact is referenced.",
  );
}

function uniqueStrings(values) {
  return [...new Set(values.filter((value) => typeof value === "string" && value.trim()))];
}

function buildReviewerWarnings({
  manifest,
  artifactRows,
  dataAccessStatus,
  decisionIntent,
  decisionWarnings,
  premiumOutcome,
  premiumOutcomeWarnings,
  snapshotWarnings,
  signals,
}) {
  const warnings = [];

  if (!manifest) {
    warnings.push("Run manifest is missing; generated artifact provenance cannot be verified.");
  } else {
    const reviewStatus = manifest.reviewState?.status || "unknown";
    if (reviewStatus !== "approved") {
      warnings.push(`Review state is ${reviewStatus}; reviewer signoff is not recorded.`);
    }
    if (dataAccessStatus !== "real_data_available") {
      warnings.push(
        `data_access classification is ${dataAccessStatus}: ${DATA_ACCESS_DEFINITIONS[dataAccessStatus]}.`,
      );
    }
  }

  for (const row of artifactRows) {
    if (row.hashStatus !== "match") {
      warnings.push(`${row.label} hash status is ${row.hashStatus}: ${HASH_STATUS_DEFINITIONS[row.hashStatus]}.`);
    }
  }

  const dataBlockedCount = signals.filter((signal) => signal.status === "data_blocked").length;
  if (dataBlockedCount) {
    warnings.push(`${dataBlockedCount} signal(s) are data_blocked and need explicit option data review.`);
  }

  const modelDominatedCount = signals.filter((signal) => signal.status === "model_dominated").length;
  if (modelDominatedCount) {
    warnings.push(`${modelDominatedCount} signal(s) are model_dominated and should not be treated as raw edge.`);
  }

  if (decisionIntent.status !== "loaded") {
    warnings.push(`Decision-intent sidecar status is ${decisionIntent.status}.`);
  }

  if (premiumOutcome.status !== "loaded") {
    warnings.push(`Premium outcome sidecar status is ${premiumOutcome.status}.`);
  }

  return uniqueStrings([...warnings, ...snapshotWarnings, ...decisionWarnings, ...premiumOutcomeWarnings]);
}

function buildReviewOperationsModel({
  manifest,
  decisionIntent,
  decisionWarnings,
  premiumOutcome,
  premiumOutcomeWarnings,
  snapshotWarnings,
  signals,
}) {
  const artifactRows = buildArtifactProvenanceRows(manifest);
  const dataAccessStatus = DATA_ACCESS_DEFINITIONS[manifest?.dataAccess?.status]
    ? manifest.dataAccess.status
    : "unknown";
  const sidecarHashStatus = chooseSidecarHashStatus(artifactRows);
  const premiumOutcomeHashStatus = choosePremiumOutcomeHashStatus(artifactRows);
  const warnings = buildReviewerWarnings({
    manifest,
    artifactRows,
    dataAccessStatus,
    decisionIntent,
    decisionWarnings,
    premiumOutcome,
    premiumOutcomeWarnings,
    snapshotWarnings,
    signals,
  });

  return {
    dataAccess: {
      status: dataAccessStatus,
      definition: DATA_ACCESS_DEFINITIONS[dataAccessStatus],
      source: manifest?.dataAccess?.source || null,
      notes: Array.isArray(manifest?.dataAccess?.notes) ? manifest.dataAccess.notes : [],
    },
    artifactRows,
    sidecarHashStatus,
    premiumOutcomeHashStatus,
    sidecarProvenance: decisionIntent.status === "loaded" ? decisionIntent.provenance || {} : {},
    premiumOutcomeProvenance: premiumOutcome.status === "loaded" ? premiumOutcome.provenance || {} : {},
    warnings,
  };
}

export function normalizeDecisionIntentSidecar(sidecar) {
  if (!sidecar) {
    return null;
  }
  if (!SUPPORTED_DECISION_INTENT_VERSIONS.has(sidecar.schema_version)) {
    throw new Error(`Unsupported decision intent contract: ${sidecar?.schema_version ?? "missing"}`);
  }

  const intents = Array.isArray(sidecar.intents) ? sidecar.intents : [];
  const intentsBySignalId = new Map();
  const stateCounts = {};
  const duplicateSignalIds = [];
  let executionAllowedCount = 0;

  for (const intent of intents) {
    const signalId = intent?.signal_id;
    if (!signalId) {
      continue;
    }
    if (intentsBySignalId.has(signalId)) {
      duplicateSignalIds.push(signalId);
    }
    intentsBySignalId.set(signalId, intent);
    const state = intent.decision_state || "unknown";
    stateCounts[state] = (stateCounts[state] || 0) + 1;
    if (intent.execution_allowed === true) {
      executionAllowedCount += 1;
    }
  }

  return {
    status: "loaded",
    schemaVersion: sidecar.schema_version,
    generatedAt: sidecar.generated_at_utc,
    sourceCommit: sidecar.source_commit,
    provenance: sidecar.provenance || {},
    artifact: null,
    intents,
    intentsBySignalId,
    warnings: Array.isArray(sidecar.warnings) ? sidecar.warnings : [],
    stateCounts,
    executionAllowedCount,
    unmatchedSignalIds: [],
    duplicateSignalIds,
    error: null,
  };
}

function emptyPremiumOutcomeCounts() {
  return Object.fromEntries(Object.keys(PREMIUM_OUTCOME_STATUS_DEFINITIONS).map((status) => [status, 0]));
}

export function normalizePremiumOutcomeSidecar(sidecar) {
  if (!sidecar) {
    return null;
  }
  if (!SUPPORTED_PREMIUM_OUTCOME_VERSIONS.has(sidecar.schema_version)) {
    throw new Error(`Unsupported premium outcome contract: ${sidecar?.schema_version ?? "missing"}`);
  }

  const outcomes = Array.isArray(sidecar.outcomes) ? sidecar.outcomes : [];
  const outcomesBySignalId = new Map();
  const evaluationCounts = emptyPremiumOutcomeCounts();
  const seenOutcomeIds = new Set();
  const duplicateOutcomeIds = [];
  const duplicateSourceSignalIds = [];

  for (const outcome of outcomes) {
    const outcomeId = outcome?.outcome_id;
    const sourceSignalId = outcome?.source_signal_id;
    if (outcomeId) {
      if (seenOutcomeIds.has(outcomeId)) {
        duplicateOutcomeIds.push(outcomeId);
      }
      seenOutcomeIds.add(outcomeId);
    }
    if (sourceSignalId) {
      if (outcomesBySignalId.has(sourceSignalId)) {
        duplicateSourceSignalIds.push(sourceSignalId);
      }
      const existing = outcomesBySignalId.get(sourceSignalId) || [];
      outcomesBySignalId.set(sourceSignalId, [...existing, outcome]);
    }
    const status = outcome?.evaluation_status || "unknown";
    evaluationCounts[status] = (evaluationCounts[status] || 0) + 1;
  }

  return {
    status: "loaded",
    schemaVersion: sidecar.schema_version,
    generatedAt: sidecar.generated_at_utc,
    sourceCommit: sidecar.source_commit,
    provenance: sidecar.provenance || {},
    artifact: null,
    outcomes,
    outcomesBySignalId,
    warnings: Array.isArray(sidecar.warnings) ? sidecar.warnings : [],
    evaluationCounts,
    duplicateOutcomeIds: uniqueStrings(duplicateOutcomeIds),
    duplicateSourceSignalIds: uniqueStrings(duplicateSourceSignalIds),
    unmatchedSourceSignalIds: [],
    missingSignalIds: [],
    error: null,
  };
}

function inferSnapshotMode(snapshot, manifest) {
  const reviewStatus = manifest?.reviewState?.status;
  if (reviewStatus && REVIEW_MODE_STATUSES.has(reviewStatus)) {
    return "review";
  }
  if (manifest) {
    return "generated";
  }
  if (snapshot.run_config?.mode === "scorecard") {
    return "generated";
  }
  return "fixture";
}

function hasPosteriorDiagnosticFields(signal) {
  return [
    signal?.underlying_r_outcome,
    signal?.premium_r_outcome,
    signal?.option_runner_outcome,
    signal?.proxy_outcome,
  ].some((value) => value !== undefined && value !== null);
}

function deriveDecisionIntentWarnings(signals, decisionIntent, manifest, error) {
  const warnings = [...(decisionIntent?.warnings || [])];
  const artifact = manifest?.decisionIntentArtifact;

  if (error) {
    warnings.push(`Decision-intent sidecar failed to load: ${error.message || error}`);
  } else if (!artifact) {
    warnings.push("Manifest does not reference a decision-intent sidecar.");
  } else if (!decisionIntent || decisionIntent.status !== "loaded") {
    warnings.push("Manifest references a decision-intent sidecar, but no sidecar payload is loaded.");
  }

  if (decisionIntent?.duplicateSignalIds?.length) {
    warnings.push(
      `Duplicate decision-intent signal ids: ${decisionIntent.duplicateSignalIds.join(", ")}`,
    );
  }

  const matchedSignalIds = new Set(signals.map((signal) => signal.id));
  const unmatchedSignalIds =
    decisionIntent?.intents
      ?.map((intent) => intent.signal_id)
      .filter((signalId) => signalId && !matchedSignalIds.has(signalId)) || [];
  if (unmatchedSignalIds.length) {
    warnings.push(`Decision-intent records without snapshot signals: ${unmatchedSignalIds.join(", ")}`);
  }

  const missingSignalIds = signals
    .filter((signal) => decisionIntent?.status === "loaded" && !decisionIntent.intentsBySignalId.has(signal.id))
    .map((signal) => signal.id);
  if (missingSignalIds.length) {
    warnings.push(`Snapshot signals missing decision-intent records: ${missingSignalIds.join(", ")}`);
  }

  const observationOnlySignalIds =
    decisionIntent?.intents
      ?.filter((intent) => intent.product_direction_tier === "observation_only")
      .map((intent) => intent.signal_id) || [];
  if (observationOnlySignalIds.length) {
    warnings.push(
      `Observation-only product-direction warning: ${observationOnlySignalIds.join(", ")} is not executable.`,
    );
  }

  const posteriorSignals = signals.filter(hasPosteriorDiagnosticFields);
  if (posteriorSignals.length) {
    warnings.push(
      "Posterior diagnostic fields are present in snapshot outcomes; decision-intent no-lookahead inputs remain the decision-time source list.",
    );
  }

  return warnings;
}

function derivePremiumOutcomeWarnings(signals, premiumOutcome, manifest, error) {
  const warnings = [...(premiumOutcome?.warnings || [])];
  const artifact = manifest?.premiumOutcomeArtifact;

  if (error) {
    warnings.push(`Premium outcome sidecar failed to load: ${error.message || error}`);
  } else if (!artifact) {
    warnings.push("Manifest does not reference a premium outcome sidecar.");
  } else if (!premiumOutcome || premiumOutcome.status !== "loaded") {
    warnings.push("Manifest references a premium outcome sidecar, but no sidecar payload is loaded.");
  }

  if (premiumOutcome?.duplicateOutcomeIds?.length) {
    warnings.push(`Duplicate premium outcome ids: ${premiumOutcome.duplicateOutcomeIds.join(", ")}`);
  }

  if (premiumOutcome?.duplicateSourceSignalIds?.length) {
    warnings.push(
      `Multiple premium outcome policy records share source_signal_id: ${premiumOutcome.duplicateSourceSignalIds.join(", ")}.`,
    );
  }

  const matchedSignalIds = new Set(signals.map((signal) => signal.id));
  const unmatchedSourceSignalIds =
    premiumOutcome?.outcomes
      ?.map((outcome) => outcome.source_signal_id)
      .filter((signalId) => signalId && !matchedSignalIds.has(signalId)) || [];
  if (unmatchedSourceSignalIds.length) {
    warnings.push(`Premium outcome records without snapshot signals: ${uniqueStrings(unmatchedSourceSignalIds).join(", ")}`);
  }

  const missingSignalIds = signals
    .filter((signal) => premiumOutcome?.status === "loaded" && !premiumOutcome.outcomesBySignalId.has(signal.id))
    .map((signal) => signal.id);
  if (missingSignalIds.length) {
    warnings.push(`Snapshot signals missing premium outcome records: ${missingSignalIds.join(", ")}`);
  }

  const outcomes = premiumOutcome?.outcomes || [];
  const modelDerivedIds = outcomes
    .filter((outcome) => outcome.data_quality?.premium_price_source_type === "model_derived")
    .map((outcome) => outcome.outcome_id);
  if (modelDerivedIds.length) {
    warnings.push(`Model-derived premium outcome evidence is not observed: ${modelDerivedIds.join(", ")}.`);
  }

  const dailyIds = outcomes
    .filter((outcome) => outcome.data_quality?.bar_granularity === "daily")
    .map((outcome) => outcome.outcome_id);
  if (dailyIds.length) {
    warnings.push("Daily premium OHLC evidence is observation-only and cannot prove exact tick-level execution ordering.");
  }

  const ambiguousIds = outcomes
    .filter((outcome) => outcome.evaluation_status === "ambiguous" || outcome.data_quality?.ambiguity)
    .map((outcome) => outcome.outcome_id);
  if (ambiguousIds.length) {
    warnings.push(`Ambiguous premium outcome ordering requires reviewer caution: ${ambiguousIds.join(", ")}.`);
  }

  const blockedIds = outcomes
    .filter((outcome) => outcome.evaluation_status === "data_blocked" || outcome.data_quality?.data_gap)
    .map((outcome) => outcome.outcome_id);
  if (blockedIds.length) {
    warnings.push(`Data-blocked premium outcome records are not observed results: ${blockedIds.join(", ")}.`);
  }

  return warnings;
}

export function buildDashboardModel(snapshot, options = {}) {
  if (!snapshot || !SUPPORTED_CONTRACT_VERSIONS.has(snapshot.schema_version)) {
    throw new Error(`Unsupported snapshot contract: ${snapshot?.schema_version ?? "missing"}`);
  }

  const renderOptions = normalizeRenderOptions(options);
  const manifest = normalizeRunManifest(renderOptions.manifest);
  const decisionIntentError = renderOptions.decisionIntentError || null;
  const premiumOutcomeError = renderOptions.premiumOutcomeError || null;
  const normalizedDecisionIntent = normalizeDecisionIntentSidecar(renderOptions.decisionIntent);
  const normalizedPremiumOutcome = normalizePremiumOutcomeSidecar(renderOptions.premiumOutcome);
  const snapshotMode = inferSnapshotMode(snapshot, manifest);
  const signals = Array.isArray(snapshot.signals) ? snapshot.signals : [];
  const summary = snapshot.summary || {};
  const statusCounts = countStatuses(summary, signals);
  const totalSignals = Number(summary.signals_total ?? signals.length);
  const maxStatus = Math.max(1, ...Object.values(statusCounts));
  const decisionIntent =
    normalizedDecisionIntent ||
    (decisionIntentError
      ? {
          ...DECISION_INTENT_EMPTY_STATE,
          status: "error",
          artifact: manifest?.decisionIntentArtifact || null,
          error: decisionIntentError,
        }
      : {
          ...DECISION_INTENT_EMPTY_STATE,
          status: manifest?.decisionIntentArtifact ? "referenced_missing" : "not_referenced",
          artifact: manifest?.decisionIntentArtifact || null,
        });
  decisionIntent.artifact = manifest?.decisionIntentArtifact || decisionIntent.artifact || null;
  decisionIntent.unmatchedSignalIds =
    decisionIntent.intents
      ?.map((intent) => intent.signal_id)
      .filter((signalId) => signalId && !signals.some((signal) => signal.id === signalId)) || [];
  const premiumOutcome =
    normalizedPremiumOutcome ||
    (premiumOutcomeError
      ? {
          ...PREMIUM_OUTCOME_EMPTY_STATE,
          status: "load_error",
          artifact: manifest?.premiumOutcomeArtifact || null,
          error: premiumOutcomeError,
        }
      : {
          ...PREMIUM_OUTCOME_EMPTY_STATE,
          status: manifest?.premiumOutcomeArtifact ? "referenced_missing" : "not_referenced",
          artifact: manifest?.premiumOutcomeArtifact || null,
        });
  premiumOutcome.artifact = manifest?.premiumOutcomeArtifact || premiumOutcome.artifact || null;
  premiumOutcome.unmatchedSourceSignalIds =
    premiumOutcome.outcomes
      ?.map((outcome) => outcome.source_signal_id)
      .filter((signalId) => signalId && !signals.some((signal) => signal.id === signalId)) || [];
  premiumOutcome.missingSignalIds = signals
    .filter((signal) => premiumOutcome.status === "loaded" && !premiumOutcome.outcomesBySignalId.has(signal.id))
    .map((signal) => signal.id);
  const decisionWarnings = deriveDecisionIntentWarnings(
    signals,
    decisionIntent.status === "loaded" ? decisionIntent : null,
    manifest,
    decisionIntentError,
  );
  const premiumOutcomeWarnings = derivePremiumOutcomeWarnings(
    signals,
    premiumOutcome.status === "loaded" ? premiumOutcome : null,
    manifest,
    premiumOutcomeError,
  );
  const reviewOperations = buildReviewOperationsModel({
    manifest,
    decisionIntent,
    decisionWarnings,
    premiumOutcome,
    premiumOutcomeWarnings,
    snapshotWarnings: Array.isArray(snapshot.warnings) ? snapshot.warnings : [],
    signals,
  });

  return {
    contract: snapshot.schema_version,
    snapshotMode,
    snapshotModeLabel: SNAPSHOT_MODE_DEFINITIONS[snapshotMode],
    generatedAt: snapshot.generated_at_utc,
    sourceCommit: snapshot.source_commit,
    runConfig: snapshot.run_config || {},
    dataQuality: snapshot.data_quality || {},
    manifest,
    summary,
    warnings: Array.isArray(snapshot.warnings) ? snapshot.warnings : [],
    statusCounts,
    totalSignals,
    maxStatus,
    decisionIntent: {
      ...decisionIntent,
      warnings: decisionWarnings,
    },
    premiumOutcome: {
      ...premiumOutcome,
      warnings: premiumOutcomeWarnings,
    },
    reviewOperations,
    signals: signals.map((signal) => ({
      ...signal,
      decisionIntent:
        decisionIntent.status === "loaded" ? decisionIntent.intentsBySignalId.get(signal.id) || null : null,
      premiumOutcomes:
        premiumOutcome.status === "loaded" ? premiumOutcome.outcomesBySignalId.get(signal.id) || [] : [],
      decisionTrace: normalizeDecisionTrace(signal),
      missingOptional: missingOptionalFields(signal),
    })),
  };
}

function renderMeta(model) {
  return `
    <section class="meta-strip" aria-label="Snapshot summary">
      <div class="metric">
        <span>Total signals</span>
        <strong>${escapeHtml(model.totalSignals)}</strong>
        <small>${escapeHtml(model.summary.integration_milestone || "fixture contract")}</small>
      </div>
      <div class="metric">
        <span>Generated UTC</span>
        <strong>${escapeHtml(formatDate(model.generatedAt))}</strong>
        <small>Snapshot timestamp</small>
      </div>
      <div class="metric">
        <span>Source commit</span>
        <strong>${escapeHtml(model.sourceCommit)}</strong>
        <small>${escapeHtml(model.runConfig.producer || "producer unavailable")}</small>
      </div>
      <div class="metric">
        <span>Snapshot mode</span>
        <strong>${modeBadge(model.snapshotMode)}</strong>
        <small>${escapeHtml(model.runConfig.contract || model.contract)}</small>
      </div>
    </section>
  `;
}

function renderStatusOverview(model) {
  const cells = Object.entries(STATUS_DEFINITIONS)
    .map(([status, definition]) => {
      const count = model.statusCounts[status] || 0;
      const width = Math.round((count / model.maxStatus) * 100);
      return `
        <div class="status-cell ${escapeHtml(status)}">
          <strong>${escapeHtml(count)}</strong>
          ${statusBadge(status)}
          <span>${escapeHtml(definition)}</span>
          <div class="status-meter" aria-hidden="true" style="--meter-width: ${width}%"><i></i></div>
        </div>
      `;
    })
    .join("");

  return `
    <section class="panel" aria-labelledby="status-heading">
      <div class="panel-header">
        <div>
          <h2 id="status-heading">Defensive States</h2>
          <p>advisory, data_blocked, model_dominated, and terminal statuses</p>
        </div>
      </div>
      <div class="status-grid">${cells}</div>
    </section>
  `;
}

function renderWarnings(model) {
  const warnings = model.warnings.length
    ? model.warnings
        .map((warning) => `<div class="warning-item">${escapeHtml(warning)}</div>`)
        .join("")
    : '<div class="warning-item muted">No contract warnings.</div>';

  return `
    <section class="panel" aria-labelledby="warnings-heading">
      <div class="panel-header">
        <div>
          <h2 id="warnings-heading">Warnings</h2>
          <p>${escapeHtml(model.warnings.length)} warning(s)</p>
        </div>
      </div>
      <div class="warnings-list">${warnings}</div>
    </section>
  `;
}

function renderDataQuality(model) {
  const entries = Object.entries(model.dataQuality);
  const items = entries.length
    ? entries
        .map(
          ([key, value]) => `
            <div class="quality-item">
              <span>${escapeHtml(key)}</span>
              <strong>${labelValue(value)}</strong>
            </div>
          `,
        )
        .join("")
    : '<div class="quality-item"><span>data_quality</span><strong class="missing">Missing</strong></div>';

  return `
    <section class="panel" aria-labelledby="quality-heading">
      <div class="panel-header">
        <div>
          <h2 id="quality-heading">Data Quality</h2>
          <p>Contract-provided fixture metadata</p>
        </div>
      </div>
      <div class="quality-grid">${items}</div>
    </section>
  `;
}

function renderArtifactRef(title, artifact) {
  if (!artifact) {
    return `
      <section class="artifact-block">
        <h3>${escapeHtml(title)}</h3>
        <p class="missing">Missing artifact metadata.</p>
      </section>
    `;
  }

  return `
    <section class="artifact-block">
      <h3>${escapeHtml(title)}</h3>
      <dl class="kv compact">
        <dt>Path</dt>
        <dd>${labelValue(artifact.path)}</dd>
        <dt>SHA-256</dt>
        <dd>${labelValue(artifact.sha256)}</dd>
        <dt>Schema</dt>
        <dd>${labelValue(artifact.schema_version)}</dd>
      </dl>
    </section>
  `;
}

function renderManifestProvenance(model) {
  const manifest = model.manifest;
  if (!manifest) {
    return `
      <section class="panel" aria-labelledby="manifest-heading" data-testid="run-manifest-empty">
        <div class="panel-header">
          <div>
            <h2 id="manifest-heading">Run Manifest</h2>
            <p>No run manifest loaded for this snapshot.</p>
          </div>
          ${modeBadge(model.snapshotMode)}
        </div>
        <div class="manifest-empty">
          <strong>Manifest metadata unavailable</strong>
          <span>Fixture and legacy snapshots can still be reviewed without provenance.</span>
        </div>
      </section>
    `;
  }

  const review = manifest.reviewState || {};
  const dataAccess = manifest.dataAccess || {};
  return `
    <section class="panel" aria-labelledby="manifest-heading" data-testid="run-manifest-provenance">
      <div class="panel-header">
        <div>
          <h2 id="manifest-heading">Run Manifest</h2>
          <p>${escapeHtml(manifest.schemaVersion)} / ${escapeHtml(formatDate(manifest.generatedAt))}</p>
        </div>
        ${modeBadge(model.snapshotMode)}
      </div>
      <div class="manifest-grid">
        <div class="manifest-item">
          <span>Source commit</span>
          <strong>${labelValue(manifest.sourceCommit)}</strong>
        </div>
        <div class="manifest-item">
          <span>Data access</span>
          <strong>${labelValue(dataAccess.status)}</strong>
          <small>${labelValue(dataAccess.source)}</small>
        </div>
        <div class="manifest-item">
          <span>Frontend copy</span>
          <strong>${labelValue(manifest.frontendCopyPath)}</strong>
        </div>
        <div class="manifest-item">
          <span>Review state</span>
          <strong>${labelValue(review.status)}</strong>
          <small>${labelValue(review.reviewer)}</small>
        </div>
      </div>
      <div class="manifest-artifacts">
        ${renderArtifactRef("Scorecard artifact", manifest.scorecardArtifact)}
        ${renderArtifactRef("Snapshot artifact", manifest.snapshotArtifact)}
        ${renderArtifactRef("Decision intent artifact", manifest.decisionIntentArtifact)}
        ${renderArtifactRef("Premium outcome artifact", manifest.premiumOutcomeArtifact)}
      </div>
      <div class="manifest-details">
        <details>
          <summary>CLI args</summary>
          ${jsonBlock(manifest.cliArgs)}
        </details>
        <details>
          <summary>Run config</summary>
          ${jsonBlock(manifest.runConfig)}
        </details>
        <details>
          <summary>Input hashes</summary>
          ${jsonBlock(manifest.inputHashes)}
        </details>
        <details>
          <summary>Output hashes</summary>
          ${jsonBlock(manifest.outputHashes)}
        </details>
        <details>
          <summary>Data access notes</summary>
          ${jsonBlock(dataAccess.notes || [])}
        </details>
        <details>
          <summary>Review notes</summary>
          ${jsonBlock(review.notes || [])}
        </details>
      </div>
    </section>
  `;
}

function renderReviewOperations(model) {
  const operations = model.reviewOperations;
  const provenanceRows = operations.artifactRows.length
    ? operations.artifactRows
        .map(
          (row) => `
            <tr>
              <td>
                <strong>${escapeHtml(row.label)}</strong>
                <div class="muted">${labelValue(row.kind)}</div>
              </td>
              <td>${labelValue(row.path)}</td>
              <td>${labelValue(row.schemaVersion)}</td>
              <td><code>${labelValue(row.actualHash)}</code></td>
              <td>
                <code>${labelValue(row.expectedHash)}</code>
                <div class="muted">${escapeHtml(row.hashSource || "no hash source")}</div>
              </td>
              <td>${hashStatusBadge(row.hashStatus)}</td>
            </tr>
          `,
        )
        .join("")
    : `
      <tr>
        <td colspan="6" class="muted">No generated artifact provenance rows are available.</td>
      </tr>
    `;

  const warningItems = operations.warnings.length
    ? operations.warnings
        .map((warning) => `<div class="warning-item reviewer-warning">${escapeHtml(warning)}</div>`)
        .join("")
    : '<div class="warning-item muted">No reviewer-ready warnings.</div>';

  return `
    <section class="panel" aria-labelledby="review-ops-heading" data-testid="review-operations">
      <div class="panel-header">
        <div>
          <h2 id="review-ops-heading">Review Operations</h2>
          <p>Generated artifact provenance, hash status, and data_access classification</p>
        </div>
        ${hashStatusBadge(operations.sidecarHashStatus.status)}
      </div>
      <div class="review-ops-grid">
        <div class="manifest-item">
          <span>data_access classification</span>
          <strong>${dataAccessBadge(operations.dataAccess.status)}</strong>
          <small>${escapeHtml(operations.dataAccess.definition)}</small>
        </div>
        <div class="manifest-item">
          <span>data_access source</span>
          <strong>${labelValue(operations.dataAccess.source)}</strong>
        </div>
        <div class="manifest-item" data-testid="sidecar-hash-status">
          <span>Sidecar hash status</span>
          <strong>${hashStatusBadge(operations.sidecarHashStatus.status)}</strong>
          <small>${escapeHtml(operations.sidecarHashStatus.label)} / ${escapeHtml(operations.sidecarHashStatus.summary)}</small>
        </div>
        <div class="manifest-item" data-testid="premium-outcome-hash-status">
          <span>Premium outcome hash</span>
          <strong>${hashStatusBadge(operations.premiumOutcomeHashStatus.status)}</strong>
          <small>${escapeHtml(operations.premiumOutcomeHashStatus.label)} / ${escapeHtml(operations.premiumOutcomeHashStatus.summary)}</small>
        </div>
      </div>
      <div class="table-wrap">
        <table class="ops-table" data-testid="artifact-provenance-table">
          <thead>
            <tr>
              <th>Artifact</th>
              <th>Path</th>
              <th>Schema</th>
              <th>Artifact SHA-256</th>
              <th>Manifest Hash Link</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>${provenanceRows}</tbody>
        </table>
      </div>
      <details class="ops-provenance" data-testid="sidecar-provenance">
        <summary>Decision-intent sidecar provenance</summary>
        ${jsonBlock(operations.sidecarProvenance)}
      </details>
      <details class="ops-provenance" data-testid="premium-outcome-provenance">
        <summary>Premium outcome sidecar provenance</summary>
        ${jsonBlock(operations.premiumOutcomeProvenance)}
      </details>
      <div class="warnings-list" data-testid="reviewer-ready-warnings">${warningItems}</div>
    </section>
  `;
}

function renderReasonCodes(reasonCodes) {
  if (!Array.isArray(reasonCodes) || reasonCodes.length === 0) {
    return '<span class="missing">Missing</span>';
  }
  return `
    <ul class="reason-code-list">
      ${reasonCodes.map((code) => `<li>${escapeHtml(code)}</li>`).join("")}
    </ul>
  `;
}

function renderDecisionIntentOverview(model) {
  const sidecar = model.decisionIntent;
  const artifact = sidecar.artifact;
  const stateCells = Object.entries(DECISION_STATE_DEFINITIONS)
    .map(([state, definition]) => {
      const count = sidecar.stateCounts[state] || 0;
      return `
        <div class="intent-state-cell ${escapeHtml(state)}">
          <strong>${escapeHtml(count)}</strong>
          ${decisionStateBadge(state)}
          <span>${escapeHtml(definition)}</span>
        </div>
      `;
    })
    .join("");

  const warningItems = sidecar.warnings.length
    ? sidecar.warnings
        .map((warning) => `<div class="warning-item intent-warning">${escapeHtml(warning)}</div>`)
        .join("")
    : '<div class="warning-item muted">No decision-intent reviewer warnings.</div>';

  return `
    <section class="panel" aria-labelledby="decision-intent-heading" data-testid="decision-intent-review">
      <div class="panel-header">
        <div>
          <h2 id="decision-intent-heading">Decision Intent Reviewer</h2>
          <p>${escapeHtml(sidecar.status)} / ${escapeHtml(sidecar.schemaVersion || "no sidecar")}</p>
        </div>
        ${artifact ? readinessBadge(artifact.kind) : readinessBadge("missing_sidecar")}
      </div>
      <div class="intent-meta-grid">
        <div class="manifest-item">
          <span>Generated UTC</span>
          <strong>${labelValue(formatDate(sidecar.generatedAt))}</strong>
        </div>
        <div class="manifest-item">
          <span>Source commit</span>
          <strong>${labelValue(sidecar.sourceCommit)}</strong>
        </div>
        <div class="manifest-item">
          <span>Execution allowed</span>
          <strong>${escapeHtml(sidecar.executionAllowedCount || 0)}</strong>
        </div>
        <div class="manifest-item">
          <span>Artifact path</span>
          <strong>${labelValue(artifact?.path)}</strong>
        </div>
      </div>
      <div class="intent-state-grid">${stateCells}</div>
      <div class="warnings-list">${warningItems}</div>
    </section>
  `;
}

function renderPremiumOutcomeOverview(model) {
  const sidecar = model.premiumOutcome;
  const artifact = sidecar.artifact;
  const hashStatus = model.reviewOperations.premiumOutcomeHashStatus;
  const stateCells = Object.entries(PREMIUM_OUTCOME_STATUS_DEFINITIONS)
    .map(([status, definition]) => {
      const count = sidecar.evaluationCounts[status] || 0;
      return `
        <div class="outcome-state-cell ${escapeHtml(status)}">
          <strong>${escapeHtml(count)}</strong>
          ${premiumOutcomeBadge(status)}
          <span>${escapeHtml(definition)}</span>
        </div>
      `;
    })
    .join("");

  const warningItems = sidecar.warnings.length
    ? sidecar.warnings
        .map((warning) => `<div class="warning-item outcome-warning">${escapeHtml(warning)}</div>`)
        .join("")
    : '<div class="warning-item muted">No premium outcome reviewer warnings.</div>';

  const emptyState =
    sidecar.status === "loaded" && sidecar.outcomes.length === 0
      ? `
        <div class="manifest-empty" data-testid="premium-outcome-empty">
          <strong>No premium outcome records</strong>
          <span>The sidecar loaded, but its outcomes array is empty.</span>
        </div>
      `
      : "";

  return `
    <section class="panel" aria-labelledby="premium-outcome-heading" data-testid="premium-outcome-review">
      <div class="panel-header">
        <div>
          <h2 id="premium-outcome-heading">Premium Outcome Review</h2>
          <p>${escapeHtml(sidecar.status)} / ${escapeHtml(sidecar.schemaVersion || "no sidecar")}</p>
        </div>
        ${artifact ? readinessBadge(artifact.kind) : readinessBadge("missing_sidecar")}
      </div>
      <div class="outcome-meta-grid">
        <div class="manifest-item">
          <span>Generated UTC</span>
          <strong>${labelValue(formatDate(sidecar.generatedAt))}</strong>
        </div>
        <div class="manifest-item">
          <span>Source commit</span>
          <strong>${labelValue(sidecar.sourceCommit)}</strong>
        </div>
        <div class="manifest-item">
          <span>Outcome records</span>
          <strong>${escapeHtml(sidecar.outcomes.length)}</strong>
        </div>
        <div class="manifest-item">
          <span>Artifact path</span>
          <strong>${labelValue(artifact?.path)}</strong>
        </div>
        <div class="manifest-item">
          <span>Premium outcome hash</span>
          <strong>${hashStatusBadge(hashStatus.status)}</strong>
          <small>${escapeHtml(hashStatus.label)} / ${escapeHtml(hashStatus.summary)}</small>
        </div>
      </div>
      <div class="outcome-state-grid">${stateCells}</div>
      ${emptyState}
      <div class="warnings-list">${warningItems}</div>
    </section>
  `;
}

function renderSignalTable(model) {
  if (model.signals.length === 0) {
    return `
      <section class="empty-state" data-testid="empty-signals" role="status">
        <h2>No signals in this snapshot</h2>
        <p>The contract loaded successfully and produced an empty signals array.</p>
      </section>
    `;
  }

  const rows = model.signals
    .map((signal) => {
      const pattern = signal.underlying_signal?.pattern || "Missing";
      const direction = signal.underlying_signal?.direction || "Missing";
      const premiumState = signal.features_det?.premium_space_signal || "Missing";
      const optionSide = signal.option_leg?.side || "Missing";
      const missing = signal.missingOptional.length;
      const intent = signal.decisionIntent;
      const outcomes = Array.isArray(signal.premiumOutcomes) ? signal.premiumOutcomes : [];
      const outcomeStatuses = uniqueStrings(outcomes.map((outcome) => outcome.evaluation_status));

      return `
        <tr>
          <td><span class="signal-id">${escapeHtml(signal.id)}</span></td>
          <td>
            <strong>${escapeHtml(signal.instrument)}</strong>
            <div class="muted">${escapeHtml(signal.contract || "Missing contract")}</div>
          </td>
          <td>${escapeHtml(signal.interval)}<div class="muted">${escapeHtml(formatDate(signal.ts_utc))}</div></td>
          <td>${statusBadge(signal.status)}</td>
          <td>
            ${intent ? decisionStateBadge(intent.decision_state) : '<span class="missing">Missing</span>'}
            <div class="muted">${intent ? executionBadge(intent.execution_allowed) : "No sidecar record"}</div>
          </td>
          <td>${escapeHtml(pattern)}<div class="muted">${escapeHtml(direction)}</div></td>
          <td>${escapeHtml(optionSide)}<div class="muted">${escapeHtml(premiumState)}</div></td>
          <td>
            <strong>${escapeHtml(outcomes.length)}</strong>
            <div class="outcome-status-stack">
              ${
                outcomeStatuses.length
                  ? outcomeStatuses.map((status) => premiumOutcomeBadge(status)).join("")
                  : '<span class="missing">No outcome record</span>'
              }
            </div>
          </td>
          <td>${intent ? renderReasonCodes(intent.reason_codes) : labelValue(signal.decision)}</td>
          <td>${missing ? `<span class="missing">${missing}</span>` : "0"}</td>
        </tr>
      `;
    })
    .join("");

  return `
    <section class="panel" aria-labelledby="signals-heading">
      <div class="panel-header">
        <div>
          <h2 id="signals-heading">Signal Table</h2>
          <p>${escapeHtml(model.signals.length)} contract signal(s)</p>
        </div>
      </div>
      <div class="table-wrap">
        <table data-testid="signal-table">
          <thead>
            <tr>
              <th>Signal</th>
              <th>Instrument</th>
              <th>Interval / Time</th>
              <th>Status</th>
              <th>Decision State</th>
              <th>Underlying</th>
              <th>Option Leg</th>
              <th>Premium Outcome</th>
              <th>Reason Codes</th>
              <th>Missing Optional</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderMissingList(signal) {
  if (!signal.missingOptional.length) {
    return '<p class="muted">No missing optional fields.</p>';
  }
  return `
    <ul class="missing-list">
      ${signal.missingOptional.map((field) => `<li>${escapeHtml(field)}</li>`).join("")}
    </ul>
  `;
}

function renderTraceInputRefs(inputRefs) {
  if (!Array.isArray(inputRefs) || inputRefs.length === 0) {
    return '<p class="muted trace-empty">No trace input references.</p>';
  }

  return `
    <ul class="trace-input-refs" data-testid="decision-trace-v1-input-refs">
      ${inputRefs
        .map(
          (input) => `
            <li>
              <strong>${labelValue(input.id)}</strong>
              <span>${escapeHtml(input.kind || "unknown")} / ${escapeHtml(input.source || "unknown")}</span>
              <code>${labelValue(input.digest)}</code>
              <small>index ${labelValue(input.record_index)} / ${escapeHtml(formatDate(input.asof_ts_utc))}</small>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

function renderIntentInputRefs(inputRefs) {
  if (!Array.isArray(inputRefs) || inputRefs.length === 0) {
    return '<p class="muted trace-empty">No no-lookahead input references.</p>';
  }

  return `
    <ul class="trace-input-refs intent-input-refs" data-testid="decision-intent-no-lookahead">
      ${inputRefs
        .map(
          (input) => `
            <li>
              <strong>${labelValue(input.id)}</strong>
              <span>${escapeHtml(input.kind || "unknown")} / ${escapeHtml(input.source || "unknown")}</span>
              <code>${labelValue(input.digest)}</code>
              <small>index ${labelValue(input.record_index)} / ${escapeHtml(formatDate(input.asof_ts_utc))}</small>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

function renderOutcomeInputRefs(inputRefs) {
  if (!Array.isArray(inputRefs) || inputRefs.length === 0) {
    return '<p class="muted trace-empty">No premium outcome no-lookahead input references.</p>';
  }

  return `
    <ul class="trace-input-refs outcome-input-refs" data-testid="premium-outcome-no-lookahead">
      ${inputRefs
        .map(
          (input) => `
            <li>
              <strong>${labelValue(input.id)}</strong>
              <span>${escapeHtml(input.kind || "unknown")} / ${escapeHtml(input.source || "unknown")}</span>
              <code>${labelValue(input.digest)}</code>
              <small>index ${labelValue(input.record_index)} / ${escapeHtml(formatDate(input.asof_ts_utc))}</small>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

function renderTraceEvidence(evidence) {
  if (!Array.isArray(evidence) || evidence.length === 0) {
    return '<p class="muted trace-empty">No evidence entries.</p>';
  }

  return `
    <ul class="trace-evidence">
      ${evidence
        .map(
          (entry) => `
            <li>
              <span class="trace-key">${escapeHtml(entry.key || "unknown")}</span>
              <strong>${traceValue(entry.value)}</strong>
              <span class="trace-source">${labelValue(entry.source_ref)}</span>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

function renderDecisionIntent(intent) {
  if (!intent) {
    return `
      <section class="drill-section intent-section" data-testid="decision-intent-missing">
        <h3>Decision Intent</h3>
        <div class="intent-missing">
          <strong>Decision-intent sidecar record missing</strong>
          <span>Review remains available from snapshot v0/v1 fields, but readiness gates are not loaded.</span>
        </div>
      </section>
    `;
  }

  const premiumStop = intent.premium_stop || {};
  const confirmation = intent.confirmation || {};
  const liquidity = intent.liquidity || {};

  return `
    <section class="drill-section intent-section" data-testid="decision-intent-sidecar">
      <h3>Decision Intent</h3>
      <div class="intent-summary">
        <div class="trace-summary-item">
          <span>decision_state</span>
          ${decisionStateBadge(intent.decision_state)}
        </div>
        <div class="trace-summary-item">
          <span>execution_allowed</span>
          ${executionBadge(intent.execution_allowed)}
        </div>
        <div class="trace-summary-item wide">
          <span>product_direction_tier</span>
          ${readinessBadge(intent.product_direction_tier)}
        </div>
        <div class="trace-summary-item wide">
          <span>reason_codes</span>
          ${renderReasonCodes(intent.reason_codes)}
        </div>
      </div>
      <div class="intent-gate-grid">
        <section class="intent-gate">
          <h4>Premium Stop</h4>
          <dl class="kv">
            <dt>Status</dt>
            <dd>${readinessBadge(premiumStop.status)}</dd>
            <dt>Source</dt>
            <dd>${labelValue(premiumStop.source)}</dd>
            <dt>Entry premium</dt>
            <dd>${labelValue(premiumStop.entry_premium)}</dd>
            <dt>Stop premium</dt>
            <dd>${labelValue(premiumStop.stop_premium)}</dd>
            <dt>Stop distance</dt>
            <dd>${percentageValue(premiumStop.stop_distance_pct)}</dd>
            <dt>Soft gate</dt>
            <dd>${percentageValue(premiumStop.soft_gate_min_pct)} to ${percentageValue(premiumStop.soft_gate_max_pct)}</dd>
            <dt>As-of UTC</dt>
            <dd>${labelValue(formatDate(premiumStop.asof_ts_utc))}</dd>
            <dt>Evidence</dt>
            <dd>${labelValue(premiumStop.evidence_ref)}</dd>
          </dl>
        </section>
        <section class="intent-gate">
          <h4>Confirmation</h4>
          <dl class="kv">
            <dt>Status</dt>
            <dd>${readinessBadge(confirmation.status)}</dd>
            <dt>Source</dt>
            <dd>${labelValue(confirmation.source)}</dd>
            <dt>Confirmed UTC</dt>
            <dd>${labelValue(formatDate(confirmation.confirmed_at_utc))}</dd>
            <dt>Evidence</dt>
            <dd>${labelValue(confirmation.evidence_ref)}</dd>
          </dl>
        </section>
        <section class="intent-gate">
          <h4>Liquidity</h4>
          <dl class="kv">
            <dt>Status</dt>
            <dd>${readinessBadge(liquidity.status)}</dd>
            <dt>Quote count</dt>
            <dd>${labelValue(liquidity.quote_count)}</dd>
            <dt>Quote age</dt>
            <dd>${labelValue(liquidity.last_quote_age_seconds)} seconds</dd>
            <dt>Recovery required</dt>
            <dd>${labelValue(liquidity.recovery_required)}</dd>
            <dt>Evidence</dt>
            <dd>${labelValue(liquidity.evidence_ref)}</dd>
          </dl>
        </section>
      </div>
      <section class="intent-input-section">
        <h4>No-lookahead Inputs</h4>
        ${renderIntentInputRefs(intent.no_lookahead_inputs)}
      </section>
    </section>
  `;
}

function policyStopLabel(params) {
  if (params?.price_level_mode === "entry_relative") {
    const stopFraction = params.stop_fraction_of_entry;
    return typeof stopFraction === "number"
      ? `${numberValue(stopFraction * 100, 2)}% of entry`
      : '<span class="missing">Missing</span>';
  }
  return labelValue(params?.stop_premium);
}

function policyTargetLabel(params) {
  if (params?.price_level_mode === "entry_relative") {
    const targets = Array.isArray(params.target_multiples_of_entry) ? params.target_multiples_of_entry : [];
    return targets.length
      ? targets.map((target) => `${numberValue(target, 3)}x entry`).join(", ")
      : '<span class="missing">Missing</span>';
  }
  const targets = Array.isArray(params?.target_premiums) ? params.target_premiums : [];
  return targets.length ? targets.map((target) => numberValue(target, 3)).join(", ") : '<span class="missing">Missing</span>';
}

function renderFillSummary(fill) {
  if (!fill) {
    return '<span class="missing">Missing</span>';
  }
  return `
    <span>${numberValue(fill.fill_premium, 4)}</span>
    <small>${escapeHtml(formatDate(fill.ts_utc))} / ${escapeHtml(fill.fill_rule || "unknown")}</small>
  `;
}

function renderOutcomeEvidence(dataQuality = {}) {
  const sourceType = dataQuality.premium_price_source_type;
  const granularity = dataQuality.bar_granularity || "unknown";
  const granularityLabel =
    granularity === "daily"
      ? "daily OHLC; observation-only, not exact tick execution proof"
      : granularity;

  return `
    <section class="outcome-card-section">
      <h5>Evidence</h5>
      <dl class="kv compact">
        <dt>Premium evidence</dt>
        <dd>
          ${premiumPriceSourceBadge(sourceType)}
          <small>${escapeHtml(PREMIUM_PRICE_SOURCE_DEFINITIONS[sourceType] || "Unknown premium evidence source")}</small>
        </dd>
        <dt>Bar granularity</dt>
        <dd>${labelValue(granularityLabel)}</dd>
        <dt>Required bars</dt>
        <dd>${labelValue(dataQuality.required_premium_bars_available)}</dd>
        <dt>Observed window</dt>
        <dd>${escapeHtml(formatDate(dataQuality.first_premium_observation_ts_utc))} to ${escapeHtml(formatDate(dataQuality.last_premium_observation_ts_utc))}</dd>
      </dl>
      ${
        dataQuality.ambiguity
          ? `<div class="warning-item outcome-warning"><strong>Ambiguity</strong> ${escapeHtml(dataQuality.ambiguity.kind || "unknown")}: ${escapeHtml(dataQuality.ambiguity.description || "No description")}</div>`
          : ""
      }
      ${
        dataQuality.data_gap
          ? `<div class="warning-item outcome-warning"><strong>Data blocked</strong> ${escapeHtml(dataQuality.data_gap.kind || "unknown")}: ${escapeHtml(dataQuality.data_gap.description || "No description")}</div>`
          : ""
      }
      ${
        Array.isArray(dataQuality.notes) && dataQuality.notes.length
          ? `<ul class="outcome-note-list">${dataQuality.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>`
          : ""
      }
    </section>
  `;
}

function renderPremiumMetrics(metrics) {
  if (!metrics) {
    return `
      <section class="outcome-card-section">
        <h5>Premium Metrics</h5>
        <p class="muted">No premium fill metrics are recorded for this non-observed outcome.</p>
      </section>
    `;
  }

  return `
    <section class="outcome-card-section">
      <h5>Premium Metrics</h5>
      <dl class="kv compact">
        <dt>Premium multiple</dt>
        <dd>${numberValue(metrics.premium_multiple, 3)}x</dd>
        <dt>Premium R</dt>
        <dd>
          ${numberValue(metrics.premium_r, 3)}
          <small>${labelValue(metrics.risk?.denominator_label)}</small>
        </dd>
        <dt>Premium MFE</dt>
        <dd>${numberValue(metrics.premium_mfe, 3)}</dd>
        <dt>Premium MAE</dt>
        <dd>${numberValue(metrics.premium_mae, 3)}</dd>
        <dt>Net return</dt>
        <dd>${numberValue(metrics.net_premium_return, 3)}</dd>
        <dt>Declared risk</dt>
        <dd>${numberValue(metrics.risk?.declared_risk_premium, 4)}</dd>
      </dl>
    </section>
  `;
}

function renderUnderlyingContext(context) {
  if (!context) {
    return `
      <section class="outcome-card-section underlying-context">
        <h5>Underlying-R Context</h5>
        <p class="muted">No separately labelled underlying-R context is recorded.</p>
      </section>
    `;
  }

  return `
    <section class="outcome-card-section underlying-context">
      <h5>Underlying-R Context</h5>
      <dl class="kv compact">
        <dt>Context source</dt>
        <dd>${labelValue(context.context_source)}</dd>
        <dt>Underlying R context</dt>
        <dd>
          ${numberValue(context.underlying_r, 3)}
          <small>${labelValue(context.underlying_r_denominator)}</small>
        </dd>
        <dt>Underlying return</dt>
        <dd>${numberValue(context.underlying_return, 4)}</dd>
        <dt>Entry / exit</dt>
        <dd>${numberValue(context.entry_underlying, 3)} to ${numberValue(context.exit_underlying, 3)}</dd>
      </dl>
      ${
        Array.isArray(context.notes) && context.notes.length
          ? `<ul class="outcome-note-list">${context.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>`
          : ""
      }
    </section>
  `;
}

function renderPremiumOutcomeCard(outcome) {
  const contract = outcome.selected_contract || {};
  const policy = outcome.policy || {};
  const params = policy.params || {};
  const dataQuality = outcome.data_quality || {};

  return `
    <article class="outcome-card ${escapeHtml(outcome.evaluation_status || "unknown")}" data-testid="premium-outcome-card">
      <div class="outcome-card-head">
        <div>
          <strong>${labelValue(outcome.outcome_id)}</strong>
          <small>${labelValue(outcome.source_signal_id)}</small>
        </div>
        <div class="outcome-card-badges">
          ${premiumOutcomeBadge(outcome.evaluation_status)}
          ${premiumPriceSourceBadge(dataQuality.premium_price_source_type)}
        </div>
      </div>
      <div class="outcome-card-grid">
        <section class="outcome-card-section">
          <h5>Selected Contract</h5>
          <dl class="kv compact">
            <dt>Contract</dt>
            <dd>${labelValue(contract.contract_symbol)}</dd>
            <dt>Type</dt>
            <dd>${labelValue(contract.option_type)}</dd>
            <dt>Exchange / product</dt>
            <dd>${labelValue(contract.exchange)} / ${labelValue(contract.product)}</dd>
            <dt>Strike / expiry</dt>
            <dd>${numberValue(contract.strike, 4)} / ${labelValue(contract.expiry)}</dd>
            <dt>DTE</dt>
            <dd>${labelValue(contract.dte_at_decision)}</dd>
          </dl>
        </section>
        <section class="outcome-card-section">
          <h5>Policy</h5>
          <dl class="kv compact">
            <dt>Policy</dt>
            <dd>${labelValue(policy.policy_id)} / ${labelValue(policy.policy_version)}</dd>
            <dt>Origin</dt>
            <dd>${labelValue(policy.origin)}</dd>
            <dt>Entry-relative stop</dt>
            <dd>${policyStopLabel(params)}</dd>
            <dt>Entry-relative target</dt>
            <dd>${policyTargetLabel(params)}</dd>
            <dt>Max hold</dt>
            <dd>${labelValue(params.max_holding_bars)} bars / ${labelValue(params.max_holding_days)} days</dd>
          </dl>
        </section>
        <section class="outcome-card-section">
          <h5>Entry / Exit</h5>
          <dl class="kv compact">
            <dt>Decision UTC</dt>
            <dd>${escapeHtml(formatDate(outcome.decision_ts_utc))}</dd>
            <dt>Entry fill</dt>
            <dd>${renderFillSummary(outcome.entry_fill)}</dd>
            <dt>Exit fill</dt>
            <dd>${renderFillSummary(outcome.exit_fill)}</dd>
            <dt>Fill reason</dt>
            <dd>${labelValue(outcome.exit_reason)}</dd>
          </dl>
        </section>
        ${renderPremiumMetrics(outcome.premium_metrics)}
        ${renderUnderlyingContext(outcome.underlying_context)}
        ${renderOutcomeEvidence(dataQuality)}
        <section class="outcome-card-section outcome-provenance">
          <h5>Provenance / Hashes</h5>
          <dl class="kv compact">
            <dt>Policy digest</dt>
            <dd><code>${labelValue(policy.digest)}</code></dd>
            <dt>Hash key</dt>
            <dd>${labelValue(policy.provenance_hash_key)}</dd>
            <dt>No-lookahead refs</dt>
            <dd>${escapeHtml(Array.isArray(outcome.no_lookahead_inputs) ? outcome.no_lookahead_inputs.length : 0)}</dd>
          </dl>
          ${renderOutcomeInputRefs(outcome.no_lookahead_inputs)}
        </section>
      </div>
    </article>
  `;
}

function renderPremiumOutcomeReview(signal, premiumOutcomeStatus) {
  const outcomes = Array.isArray(signal.premiumOutcomes) ? signal.premiumOutcomes : [];
  if (!outcomes.length) {
    return `
      <section class="drill-section outcome-section" data-testid="premium-outcome-missing">
        <h3>Premium Outcome</h3>
        <div class="intent-missing">
          <strong>Premium outcome record missing</strong>
          <span>Sidecar status: ${escapeHtml(premiumOutcomeStatus)}. This dashboard does not infer outcomes from price data.</span>
        </div>
      </section>
    `;
  }

  return `
    <section class="drill-section outcome-section" data-testid="premium-outcome-signal-review">
      <h3>Premium Outcome</h3>
      <div class="outcome-card-list">
        ${outcomes.map((outcome) => renderPremiumOutcomeCard(outcome)).join("")}
      </div>
    </section>
  `;
}

function renderDecisionTrace(trace) {
  if (trace.kind !== "decision_trace_v1") {
    return `
      <section class="drill-section trace-section" data-testid="legacy-decision-trace">
        <h3>Decision Trace</h3>
        <dl class="kv">
          <dt>Source</dt>
          <dd>legacy decision_trace</dd>
          <dt>Trace</dt>
          <dd>${labelValue(trace.text)}</dd>
        </dl>
      </section>
    `;
  }

  const summary = trace.summary || {};
  const nodes = trace.nodes
    .map(
      (node) => `
        <li class="trace-node ${escapeHtml(node.status || "unknown")}">
          <div class="trace-node-head">
            <div>
              <strong>${escapeHtml(node.label || node.id || "Unnamed node")}</strong>
              <small>${escapeHtml(node.id || "missing-id")} / ${escapeHtml(node.kind || "unknown")}</small>
            </div>
            <div class="trace-node-badges">
              ${traceNodeBadge(node.status)}
              <span class="trace-effect">${escapeHtml(node.decision_effect || "none")}</span>
            </div>
          </div>
          <p>${labelValue(node.reason)}</p>
          ${renderTraceEvidence(node.evidence)}
        </li>
      `,
    )
    .join("");

  return `
    <section class="drill-section trace-section" data-testid="decision-trace-v1">
      <h3>Decision Trace v1</h3>
      <div class="trace-summary">
        <div class="trace-summary-item wide">
          <span>Headline</span>
          <strong>${labelValue(summary.headline)}</strong>
        </div>
        <div class="trace-summary-item">
          <span>Action</span>
          <strong>${labelValue(trace.action)}</strong>
        </div>
        <div class="trace-summary-item">
          <span>Status</span>
          ${statusBadge(trace.status)}
        </div>
        <div class="trace-summary-item">
          <span>Primary blocker</span>
          <strong>${labelValue(summary.primary_blocker)}</strong>
        </div>
        <div class="trace-summary-item">
          <span>Selected option</span>
          <strong>${labelValue(summary.selected_option_contract)}</strong>
        </div>
        <div class="trace-summary-item">
          <span>Confidence</span>
          <strong>${labelValue(summary.confidence)}</strong>
        </div>
        <div class="trace-summary-item">
          <span>Inputs</span>
          <strong>${escapeHtml(trace.inputRefs.length)}</strong>
        </div>
      </div>
      ${renderTraceInputRefs(trace.inputRefs)}
      <ol class="trace-node-list" data-testid="decision-trace-v1-nodes">${nodes}</ol>
    </section>
  `;
}

function renderSignalDrilldown(model) {
  if (model.signals.length === 0) {
    return "";
  }

  const items = model.signals
    .map(
      (signal, index) => `
        <details class="drilldown" ${index === 0 ? "open" : ""} data-testid="signal-drill-down">
          <summary>
            <span class="summary-title">
              <span class="signal-id">${escapeHtml(signal.id)}</span>
              ${statusBadge(signal.status)}
              <span>${escapeHtml(signal.instrument)}</span>
            </span>
            <span class="chevron">details</span>
          </summary>
          <div class="drill-grid">
            <section class="drill-section">
              <h3>Decision</h3>
              <dl class="kv">
                <dt>Decision</dt>
                <dd>${labelValue(signal.decision)}</dd>
                <dt>Caveats</dt>
                <dd>${signal.caveats?.length ? escapeHtml(signal.caveats.join("; ")) : labelValue(null)}</dd>
              </dl>
            </section>
            ${renderDecisionIntent(signal.decisionIntent)}
            ${renderPremiumOutcomeReview(signal, model.premiumOutcome.status)}
            ${renderDecisionTrace(signal.decisionTrace)}
            <section class="drill-section">
              <h3>Option Selection</h3>
              <dl class="kv">
                <dt>Side</dt>
                <dd>${labelValue(signal.option_leg?.side)}</dd>
                <dt>Strike</dt>
                <dd>${labelValue(signal.option_leg?.strike)}</dd>
                <dt>DTE</dt>
                <dd>${labelValue(signal.option_leg?.dte)}</dd>
                <dt>Selection</dt>
                <dd>${statusBadge(signal.option_leg?.selection_status || "drop")}</dd>
              </dl>
            </section>
            <section class="drill-section">
              <h3>IV / Exit</h3>
              <dl class="kv">
                <dt>IV rank</dt>
                <dd>${labelValue(signal.iv_regime?.iv_rank)}</dd>
                <dt>IV keep</dt>
                <dd>${labelValue(signal.iv_regime?.keep)}</dd>
                <dt>IV reason</dt>
                <dd>${labelValue(signal.iv_regime?.reason)}</dd>
                <dt>Exit mode</dt>
                <dd>${labelValue(signal.exit_policy?.mode)} ${statusBadge(signal.exit_policy?.status || "drop")}</dd>
                <dt>Exit reason</dt>
                <dd>${labelValue(signal.exit_policy?.reason)}</dd>
              </dl>
            </section>
            <section class="drill-section">
              <h3>Missing Optional Fields</h3>
              ${renderMissingList(signal)}
            </section>
            <section class="drill-section">
              <h3>Underlying / Features</h3>
              ${jsonBlock({
                underlying_signal: signal.underlying_signal,
                features_det: signal.features_det,
              })}
            </section>
            <section class="drill-section">
              <h3>Separated Outcomes</h3>
              ${jsonBlock({
                underlying_r_outcome: signal.underlying_r_outcome,
                premium_r_outcome: signal.premium_r_outcome,
                option_runner_outcome: signal.option_runner_outcome,
                proxy_outcome: signal.proxy_outcome,
              })}
            </section>
          </div>
        </details>
      `,
    )
    .join("");

  return `
    <section class="panel" aria-labelledby="drilldown-heading">
      <div class="panel-header">
        <div>
          <h2 id="drilldown-heading">Signal Drill-Down</h2>
          <p>Contract fields per signal</p>
        </div>
      </div>
      ${items}
    </section>
  `;
}

export function renderDashboard(snapshot, options = {}) {
  const model = buildDashboardModel(snapshot, options);

  return `
    <div class="dashboard-grid">
      ${renderMeta(model)}
      ${renderStatusOverview(model)}
      ${renderWarnings(model)}
      ${renderDataQuality(model)}
      ${renderManifestProvenance(model)}
      ${renderReviewOperations(model)}
      ${renderDecisionIntentOverview(model)}
      ${renderPremiumOutcomeOverview(model)}
      ${renderSignalTable(model)}
      ${renderSignalDrilldown(model)}
    </div>
  `;
}

export async function loadSnapshot(fetchImpl = globalThis.fetch, snapshotUrl = SNAPSHOT_URL) {
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch is not available");
  }
  const response = await fetchImpl(new URL(snapshotUrl, import.meta.url));
  if (!response.ok) {
    throw new Error(`Failed to load snapshot: HTTP ${response.status}`);
  }
  return response.json();
}

export async function loadManifest(fetchImpl = globalThis.fetch, manifestUrl = MANIFEST_URL) {
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch is not available");
  }
  const response = await fetchImpl(new URL(manifestUrl, import.meta.url));
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Failed to load manifest: HTTP ${response.status}`);
  }
  return response.json();
}

export function artifactPathToUrl(path) {
  if (!path) {
    return null;
  }
  if (/^(https?:)?\/\//.test(path) || path.startsWith("/") || path.startsWith("./") || path.startsWith("../")) {
    return path;
  }
  return `/${path.replace(/^\/+/, "")}`;
}

export async function loadDecisionIntent(fetchImpl = globalThis.fetch, manifest = null) {
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch is not available");
  }
  const normalizedManifest = normalizeRunManifest(manifest);
  const artifactUrl = artifactPathToUrl(normalizedManifest?.decisionIntentArtifact?.path);
  if (!artifactUrl) {
    return null;
  }

  const response = await fetchImpl(new URL(artifactUrl, import.meta.url));
  if (response.status === 404) {
    throw new Error(`Failed to load decision intent: ${artifactUrl} returned HTTP 404`);
  }
  if (!response.ok) {
    throw new Error(`Failed to load decision intent: HTTP ${response.status}`);
  }
  return response.json();
}

export async function loadPremiumOutcome(fetchImpl = globalThis.fetch, manifest = null) {
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch is not available");
  }
  const normalizedManifest = normalizeRunManifest(manifest);
  const artifactUrl = artifactPathToUrl(normalizedManifest?.premiumOutcomeArtifact?.path);
  if (!artifactUrl) {
    return null;
  }

  const response = await fetchImpl(new URL(artifactUrl, import.meta.url));
  if (response.status === 404) {
    throw new Error(`Failed to load premium outcome: ${artifactUrl} returned HTTP 404`);
  }
  if (!response.ok) {
    throw new Error(`Failed to load premium outcome: HTTP ${response.status}`);
  }
  return response.json();
}

export function renderError(error) {
  return `
    <section class="error-panel" role="alert">
      <h2>Dashboard failed to load</h2>
      <p>${escapeHtml(error?.message || error)}</p>
    </section>
  `;
}

export async function mountDashboard(root = document.getElementById("dashboard-root")) {
  if (!root) {
    return;
  }
  try {
    const snapshot = await loadSnapshot();
    let manifest = null;
    let decisionIntent = null;
    let decisionIntentError = null;
    let premiumOutcome = null;
    let premiumOutcomeError = null;
    try {
      manifest = await loadManifest();
    } catch (error) {
      console.warn?.("PA Feitian manifest unavailable", error);
    }
    try {
      decisionIntent = await loadDecisionIntent(globalThis.fetch, manifest);
    } catch (error) {
      decisionIntentError = error;
      console.warn?.("PA Feitian decision intent unavailable", error);
    }
    try {
      premiumOutcome = await loadPremiumOutcome(globalThis.fetch, manifest);
    } catch (error) {
      premiumOutcomeError = error;
      console.warn?.("PA Feitian premium outcome unavailable", error);
    }
    root.innerHTML = renderDashboard(snapshot, {
      manifest,
      decisionIntent,
      decisionIntentError,
      premiumOutcome,
      premiumOutcomeError,
    });
  } catch (error) {
    root.innerHTML = renderError(error);
  }
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  window.addEventListener("DOMContentLoaded", () => {
    mountDashboard();
  });
}
