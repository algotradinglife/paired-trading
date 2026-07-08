const SNAPSHOT_URL = "./fixtures/pa_feitian_snapshot_v1.json";

export const SUPPORTED_CONTRACT_VERSIONS = new Set([
  "pa_feitian_snapshot_v1",
  "pa_feitian_snapshot_v0",
]);

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

export function buildDashboardModel(snapshot) {
  if (!snapshot || !SUPPORTED_CONTRACT_VERSIONS.has(snapshot.schema_version)) {
    throw new Error(`Unsupported snapshot contract: ${snapshot?.schema_version ?? "missing"}`);
  }

  const signals = Array.isArray(snapshot.signals) ? snapshot.signals : [];
  const summary = snapshot.summary || {};
  const statusCounts = countStatuses(summary, signals);
  const totalSignals = Number(summary.signals_total ?? signals.length);
  const maxStatus = Math.max(1, ...Object.values(statusCounts));

  return {
    contract: snapshot.schema_version,
    generatedAt: snapshot.generated_at_utc,
    sourceCommit: snapshot.source_commit,
    runConfig: snapshot.run_config || {},
    dataQuality: snapshot.data_quality || {},
    summary,
    warnings: Array.isArray(snapshot.warnings) ? snapshot.warnings : [],
    statusCounts,
    totalSignals,
    maxStatus,
    signals: signals.map((signal) => ({
      ...signal,
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
        <span>Fixture mode</span>
        <strong>${escapeHtml(model.runConfig.mode || "Missing")}</strong>
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

      return `
        <tr>
          <td><span class="signal-id">${escapeHtml(signal.id)}</span></td>
          <td>
            <strong>${escapeHtml(signal.instrument)}</strong>
            <div class="muted">${escapeHtml(signal.contract || "Missing contract")}</div>
          </td>
          <td>${escapeHtml(signal.interval)}<div class="muted">${escapeHtml(formatDate(signal.ts_utc))}</div></td>
          <td>${statusBadge(signal.status)}</td>
          <td>${escapeHtml(pattern)}<div class="muted">${escapeHtml(direction)}</div></td>
          <td>${escapeHtml(optionSide)}<div class="muted">${escapeHtml(premiumState)}</div></td>
          <td>${escapeHtml(signal.decision || "Missing")}</td>
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
          <p>${escapeHtml(model.signals.length)} fixture signal(s)</p>
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
              <th>Underlying</th>
              <th>Option Leg</th>
              <th>Decision</th>
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

export function renderDashboard(snapshot) {
  const model = buildDashboardModel(snapshot);

  return `
    <div class="dashboard-grid">
      ${renderMeta(model)}
      ${renderStatusOverview(model)}
      ${renderWarnings(model)}
      ${renderDataQuality(model)}
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
    root.innerHTML = renderDashboard(snapshot);
  } catch (error) {
    root.innerHTML = renderError(error);
  }
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  window.addEventListener("DOMContentLoaded", () => {
    mountDashboard();
  });
}
