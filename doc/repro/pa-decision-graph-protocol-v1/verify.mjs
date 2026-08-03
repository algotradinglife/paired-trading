import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const here = dirname(new URL(import.meta.url).pathname);
const names = {
  readme: "README.md",
  manifest: "source_manifest_v1.json",
  registry: "decision_graph_registry_v1.json",
  lifecycle: "trade_lifecycle_contract_v1.json",
  adjudication: "pi_management_adjudication_v1.md",
  episode: "episode_semantics_v1.md",
  weights: "weight_learning_protocol_v1.md",
  downstream: "downstream_issue_graph_v1.md",
  verifier: "verify.mjs",
  replay: "fixtures/replay_cases_v1.json",
  eligibility: "fixtures/eligibility_cases_v1.json"
};
const expectedCommit = "d92ecd827fe671a589b7fdfdbba41e5e98081d87";
const expectedPolicyVersion = "pa-policy-v1-semantic-repair";
const expectedGraphVersion = "1.0.0";
const expectedTerminal = "needs_revision";
const allowedProvenance = new Set(["upstream_pa", "existing_paired_trading", "pi_policy_extension"]);
const expectedStates = new Set(["observe", "candidate", "armed", "entered", "unconfirmed", "confirmed", "weakened", "invalidated", "tp1_touch", "partial_exit", "trailing", "condition_exit", "protective_stop", "exited", "no_trade", "right_censored"]);
const integrityStatuses = new Set(["valid_policy_episode", "valid_human_override_episode", "invalid_causality", "invalid_state_transition", "invalid_version_binding", "invalid_data", "invalid_replay"]);
let lifecycleAuthority;

const bytes = (relative) => readFileSync(join(here, relative));
const text = (relative) => bytes(relative).toString("utf8");
const json = (relative) => JSON.parse(text(relative));
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const canonical = (value) => {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
};
const expectReject = (fn, label) => assert.throws(fn, undefined, `${label} must reject`);
const unique = (values, label) => assert.equal(new Set(values).size, values.length, `${label} must be unique`);
const setEquals = (actual, expected, label) => assert.deepEqual([...actual].sort(), [...expected].sort(), label);

function findRepoRoot() {
  let candidate = resolve(here, "../../..");
  while (candidate !== dirname(candidate)) {
    if (existsSync(join(candidate, "doc/design/pa-feitian-decision-trace-v1-2026-07-08.md"))) return candidate;
    candidate = dirname(candidate);
  }
  throw new Error("repository root with paired-trading reference artifacts was not found");
}

const repoRoot = findRepoRoot();

function sourcePath(refPath) {
  const packetPath = join(here, refPath);
  if (existsSync(packetPath)) return packetPath;
  return join(repoRoot, refPath);
}

function validateSourceRef(ref, label) {
  assert.equal(typeof ref, "string", `${label}: source reference must be a string`);
  const hash = ref.indexOf("#");
  const refPath = hash < 0 ? ref : ref.slice(0, hash);
  const fragment = hash < 0 ? "" : ref.slice(hash + 1);
  const absolute = sourcePath(refPath);
  assert.ok(existsSync(absolute), `${label}: missing source ${refPath}`);
  if (!fragment) return;
  const raw = readFileSync(absolute, "utf8");
  const variants = [fragment, fragment.replace(/^§/, ""), fragment.replace(/^§/, "").replace(/^0+(?=\d)/, "")];
  const pieces = fragment.split(/-(?=§?\d|§?[一二三四五六七八九十])/).filter(Boolean);
  const normalize = (value) => value.toLowerCase().replace(/^§/, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  assert.ok(variants.some((candidate) => raw.includes(candidate)) || pieces.length > 1 && pieces.every((piece) => [piece, piece.replace(/^§/, "")].some((candidate) => raw.includes(candidate))) || normalize(raw).includes(normalize(fragment)), `${label}: unresolved source fragment ${ref}`);
}

function validateManifest(manifest, registry) {
  assert.equal(manifest.schema_version, "pa_decision_graph_source_manifest_v1");
  assert.equal(manifest.upstream.commit, expectedCommit);
  assert.equal(manifest.upstream.commit_is_immutable, true);
  assert.equal(manifest.fixtures_are_byte_exact_snapshots, true);
  assert.deepEqual(manifest.unmapped_branches, [], "unmapped branches fail readiness");
  assert.equal(manifest.selected_files.length, 3);
  const selectedBranches = manifest.selected_files.flatMap((entry) => entry.selected_branch_ids);
  unique(selectedBranches, "selected source branch IDs");
  const expectedFiles = new Map([
    ["prompt_engineering/二元决策.txt", ["fixtures/upstream/binary_decision.txt", 42207, "875a1a210b990ff2ade05c01fdfa8e93abccd87480e0e5dcd3d76f68e9d0fda5"]],
    ["prompt_engineering/文件17-止损和止盈与仓位管理.txt", ["fixtures/upstream/stop_target_risk.txt", 3979, "e953072fccb182bd391511132fa924ca5b2c5711292051348446df1da7b2a805"]],
    ["prompt_engineering/逐棒分析检查单.txt", ["fixtures/upstream/bar_by_bar_checklist.txt", 2304, "4e867202df9cba4dcb5a74a6c122bb112880534f9cfeeb24e6ca25df8ab996ea"]]
  ]);
  for (const entry of manifest.selected_files) {
    assert.ok(expectedFiles.has(entry.source_path), `unexpected source ${entry.source_path}`);
    const [fixture, length, digest] = expectedFiles.get(entry.source_path);
    assert.equal(entry.fixture_path, fixture);
    assert.equal(entry.byte_length, length);
    assert.equal(entry.sha256, digest);
    assert.equal(entry.provenance_class, "upstream_pa");
    const raw = bytes(entry.fixture_path);
    assert.equal(raw.byteLength, entry.byte_length, `${entry.fixture_path}: byte length`);
    assert.equal(sha256(raw), entry.sha256, `${entry.fixture_path}: SHA-256`);
    unique(entry.selected_branch_ids, `${entry.source_path}: branch IDs`);
  }
  for (const reference of manifest.existing_paired_trading_references) {
    assert.equal(reference.sha256_required_at_verification, true, `${reference.path}: digest requirement`);
    assert.match(reference.sha256 ?? "", /^[0-9a-f]{64}$/, `${reference.path}: expected SHA-256`);
    const absolute = join(repoRoot, reference.path);
    assert.ok(existsSync(absolute), `${reference.path}: reference exists`);
    assert.equal(sha256(readFileSync(absolute)), reference.sha256, `${reference.path}: SHA-256`);
  }
  const registryBranches = registry.nodes.filter((node) => node.branch_id).map((node) => node.branch_id);
  assert.deepEqual([...registryBranches].sort(), [...selectedBranches].sort(), "every selected branch maps once to a node");
  const edgeBranches = new Set(registry.edges.map((edge) => edge.branch_id).filter(Boolean));
  assert.deepEqual([...edgeBranches].sort(), [...selectedBranches].sort(), "every selected branch maps to an edge");
  return selectedBranches;
}

function lifecycleTransitionKey(from, action, to) {
  return `${from}|${action}|${to}`;
}

function derivedLifecycleTransitions(lifecycle) {
  return lifecycle.states.flatMap((state) => state.allowed_actions.flatMap((action) => (action.next_states ?? []).map((to) => ({ from: state.state_id, action: action.action, to }))));
}

function validateRegistry(registry, selectedBranches, lifecycle) {
  assert.equal(registry.schema_version, "pa_decision_graph_registry_v1");
  assert.equal(registry.topology_status, "frozen_within_protocol");
  assert.equal(registry.weight_mutability, "weights_only_between_declared_batches");
  const nodes = new Map(registry.nodes.map((node) => [node.node_id, node]));
  assert.equal(nodes.size, registry.nodes.length, "node IDs");
  assert.ok(!nodes.has("lifecycle.time_exit"), "arbitrary time-exit node is forbidden");
  unique(registry.edges.map((edge) => edge.edge_id), "edge IDs");
  const selectedNodeBranches = registry.nodes.filter((node) => node.branch_id).map((node) => node.branch_id);
  unique(selectedNodeBranches, "registry branch IDs");
  for (const node of registry.nodes) {
    assert.ok(node.node_id && node.label && node.semantics, `${node.node_id}: node fields`);
    assert.ok(allowedProvenance.has(node.provenance_class), `${node.node_id}: provenance`);
    assert.ok(Array.isArray(node.source_refs) && node.source_refs.length > 0, `${node.node_id}: source refs`);
    node.source_refs.forEach((ref) => validateSourceRef(ref, `${node.node_id}: source`));
    assert.ok(Array.isArray(node.required_closed_bar_inputs) && node.required_closed_bar_inputs.length > 0, `${node.node_id}: closed-bar inputs`);
  }
  assert.deepEqual(registry.selected_branch_coverage.unmapped_branch_ids, []);
  assert.equal(registry.selected_branch_coverage.every_selected_branch_has_node, true);
  assert.equal(registry.selected_branch_coverage.every_selected_branch_has_edge, true);
  const momentumNode = registry.nodes.find((node) => node.node_id === "direction.momentum_support");
  assert.equal(momentumNode?.branch_id, "BD-2.5-momentum-support", "PA §2.5 must be a selected registry branch");
  assert.ok(momentumNode.source_refs.some((ref) => ref.endsWith("binary_decision.txt#2.5")), "PA §2.5 source binding");
  for (const edge of registry.edges) {
    assert.ok(nodes.has(edge.from), `${edge.edge_id}: from`);
    assert.ok(nodes.has(edge.to), `${edge.edge_id}: to`);
    assert.ok(edge.when && edge.source_refs?.length, `${edge.edge_id}: guard/source`);
    edge.source_refs.forEach((ref) => validateSourceRef(ref, `${edge.edge_id}: source`));
    assert.ok(allowedProvenance.has(edge.provenance_class), `${edge.edge_id}: provenance`);
    assert.ok(typeof edge.semantics === "string" && edge.semantics.length > 0, `${edge.edge_id}: semantics`);
    if (edge.action !== undefined) assert.ok(lifecycle.action_vocabulary.includes(edge.action), `${edge.edge_id}: action vocabulary`);
    if (edge.from.startsWith("lifecycle.") || edge.to.startsWith("lifecycle.")) {
      assert.equal(edge.provenance_class, "pi_policy_extension", `${edge.edge_id}: lifecycle edge provenance`);
      assert.ok(edge.source_refs.some((ref) => ref.startsWith("pi_management_adjudication_v1.md#")), `${edge.edge_id}: PI source ref`);
    }
    assert.notEqual(edge.when, "time_limit_reached=true", `${edge.edge_id}: arbitrary time exit is forbidden`);
    if (edge.branch_id) assert.ok(selectedBranches.includes(edge.branch_id), `${edge.edge_id}: branch coverage`);
  }
  for (const branch of selectedBranches) {
    const node = registry.nodes.find((candidate) => candidate.branch_id === branch);
    assert.ok(node, `${branch}: node mapping`);
    assert.ok(registry.edges.some((edge) => edge.branch_id === branch && (edge.from === node.node_id || edge.to === node.node_id)), `${branch}: connected edge mapping`);
  }
  const adjacency = new Map(registry.nodes.map((node) => [node.node_id, []]));
  for (const edge of registry.edges) adjacency.get(edge.from).push(edge.to);
  const reachable = new Set(["observe.readable"]);
  const queue = ["observe.readable"];
  while (queue.length) for (const next of adjacency.get(queue.shift())) if (!reachable.has(next)) { reachable.add(next); queue.push(next); }
  assert.deepEqual([...reachable].sort(), [...nodes.keys()].sort(), "all registry nodes reachable from observe.readable");
  for (const node of registry.nodes.filter((candidate) => candidate.kind === "decision")) {
    const outgoing = registry.edges.filter((edge) => edge.from === node.node_id);
    assert.ok(outgoing.length > 0, `${node.node_id}: nonterminal liveness`);
    if (outgoing.length === 1) assert.ok(outgoing[0].to === "terminal.wait" || outgoing[0].to === "terminal.reject", `${node.node_id}: decision must have a fail-closed complement`);
  }
  return nodes;
}

function validateLifecycle(lifecycle, registryNodes) {
  assert.equal(lifecycle.schema_version, "pa_trade_lifecycle_contract_v1");
  assert.equal(lifecycle.policy_version, expectedPolicyVersion);
  assert.equal(lifecycle.closed_bar_only_for_graph_decisions, true);
  assert.equal(lifecycle.future_input_policy, "reject_as_invalid_causality");
  assert.equal(lifecycle.management_policy_status, "accepted");
  assert.equal(lifecycle.pi_adjudication.comment_id, 5169587241);
  unique(lifecycle.action_vocabulary, "lifecycle action vocabulary");
  const stateMap = new Map(lifecycle.states.map((state) => [state.state_id, state]));
  setEquals(new Set(stateMap.keys()), expectedStates, "lifecycle states");
  assert.equal(stateMap.size, lifecycle.states.length, "lifecycle state IDs");
  assert.deepEqual(Object.keys(lifecycle.state_action_matrix).sort(), [...expectedStates].sort(), "state×action matrix states");
  const usedActions = new Set();
  for (const state of lifecycle.states) {
    assert.ok(Array.isArray(state.required_closed_bar_inputs) && state.required_closed_bar_inputs.length > 0, `${state.state_id}: inputs`);
    assert.ok(Array.isArray(state.allowed_actions) && state.allowed_actions.length > 0, `${state.state_id}: allowed actions`);
    assert.ok(Array.isArray(state.rejected_actions) && state.rejected_actions.length > 0, `${state.state_id}: rejected actions`);
    unique([...state.allowed_actions, ...state.rejected_actions].map((action) => action.action), `${state.state_id}: total action rows`);
    assert.equal(state.allowed_actions.length + state.rejected_actions.length, lifecycle.action_vocabulary.length, `${state.state_id}: total state×action rows`);
    for (const action of state.allowed_actions) {
      usedActions.add(action.action);
      assert.ok(lifecycle.action_vocabulary.includes(action.action), `${state.state_id}/${action.action}: vocabulary`);
      assert.equal(action.disposition, "allow", `${state.state_id}/${action.action}: disposition`);
      for (const next of action.next_states ?? []) assert.ok(stateMap.has(next), `${state.state_id}/${action.action}: unknown next ${next}`);
    }
    for (const action of state.rejected_actions) {
      usedActions.add(action.action);
      assert.ok(lifecycle.action_vocabulary.includes(action.action), `${state.state_id}/${action.action}: vocabulary`);
      assert.equal(action.disposition, "reject", `${state.state_id}/${action.action}: disposition`);
      assert.deepEqual(action.next_states ?? [], [], `${state.state_id}/${action.action}: rejected action cannot transition`);
    }
    assert.deepEqual(Object.keys(lifecycle.state_action_matrix[state.state_id]).sort(), [...lifecycle.action_vocabulary].sort(), `${state.state_id}: total action matrix`);
    for (const action of lifecycle.action_vocabulary) {
      const cell = lifecycle.state_action_matrix[state.state_id][action];
      const allowed = state.allowed_actions.find((candidate) => candidate.action === action);
      const rejected = state.rejected_actions.find((candidate) => candidate.action === action);
      assert.ok(cell && (allowed || rejected), `${state.state_id}/${action}: matrix source`);
      assert.equal(cell.disposition, allowed ? "allow" : "reject", `${state.state_id}/${action}: matrix disposition`);
      assert.deepEqual(cell.next_states ?? [], allowed?.next_states ?? [], `${state.state_id}/${action}: matrix next states`);
    }
  }
  setEquals(new Set(lifecycle.action_vocabulary), usedActions, "action vocabulary has no undeclared or hidden actions");
  assert.deepEqual(lifecycle.transition_contract.map((row) => lifecycleTransitionKey(row.from, row.action, row.to)).sort(), derivedLifecycleTransitions(lifecycle).map((row) => lifecycleTransitionKey(row.from, row.action, row.to)).sort(), "transition contract is derived from the allow matrix");
  assert.equal(lifecycle.states.flatMap((state) => [...state.allowed_actions, ...state.rejected_actions]).filter((action) => action.disposition === "pending_pi").length, 0, "accepted lifecycle has no pending actions");
  assert.equal(stateMap.get("exited").terminal, true);
  assert.equal(stateMap.get("no_trade").terminal, true);
  assert.equal(stateMap.get("right_censored").terminal, true);
  assert.equal(stateMap.get("entered").terminal, false);
  assert.equal(lifecycle.unresolved_management_branches.length, 5);
  unique(lifecycle.unresolved_management_branches.map((row) => row.branch_id), "adjudication branch IDs");
  for (const row of lifecycle.unresolved_management_branches) {
    assert.ok(row.selected, `${row.branch_id}: explicit PI selection required`);
    assert.ok(row.decision, `${row.branch_id}: explicit decision required`);
    assert.equal(row.alternatives.length, 2);
  }
  for (const [nodeId, node] of registryNodes) if (nodeId.startsWith("lifecycle.")) assert.equal(node.provenance_class, "pi_policy_extension");
  return stateMap;
}

function validateGraphLifecycle(registry, lifecycle) {
  const registryLifecycleStates = new Set(registry.nodes.filter((node) => node.node_id.startsWith("lifecycle.")).map((node) => node.node_id.slice("lifecycle.".length)));
  const expected = new Set(derivedLifecycleTransitions(lifecycle).filter((row) => registryLifecycleStates.has(row.from)).map((row) => lifecycleTransitionKey(row.from, row.action, row.to)));
  const actual = new Set(registry.edges.filter((edge) => edge.from.startsWith("lifecycle.") && (edge.to.startsWith("lifecycle.") || edge.to === "terminal.exited")).map((edge) => lifecycleTransitionKey(edge.from.slice("lifecycle.".length), edge.action, edge.to === "terminal.exited" ? "exited" : edge.to.slice("lifecycle.".length))));
  setEquals(actual, expected, "registry lifecycle transitions equal lifecycle authority");
}

function validateAdjudication(adjudication, lifecycle) {
  assert.match(adjudication, /Status: `accepted`/);
  assert.match(adjudication, /5169587241/);
  assert.match(adjudication, /no implicit defaults|does not invent a default/i);
  for (const id of ["MA-01-invalidation", "MA-02-confirmation-weakening", "MA-03-tp1-partial", "MA-04-trailing", "MA-05-time-exit"]) assert.match(adjudication, new RegExp(id));
  for (const row of lifecycle.unresolved_management_branches) {
    assert.match(adjudication, new RegExp(row.branch_id));
    assert.match(adjudication, new RegExp(row.selected.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(adjudication, /hard protective price order/i);
  assert.match(adjudication, /intrabar_order_ambiguous/);
  assert.match(adjudication, /0\.5/);
  assert.match(adjudication, /three-bar pivot/i);
  assert.match(adjudication, /right_censored/);
}

function validateEpisodeDocs(episode, weights, downstream) {
  assert.match(episode, /policy_recommendation/);
  assert.match(episode, /human_override/);
  assert.match(episode, /market_outcome/);
  for (const status of integrityStatuses) assert.match(episode, new RegExp(status));
  assert.match(episode, /valid_policy_episode.*\|.*admit|admit.*valid_policy_episode/s);
  assert.match(episode, /valid_human_override_episode/);
  assert.match(episode, /profitable invalid episode remains quarantined/i);
  assert.match(episode, /observed_at_utc <= decision_or_transition_ts_utc/);
  assert.match(episode, /exhaustive|every row/i);
  assert.match(weights, /topology.*immutable|topology.*frozen/is);
  assert.match(weights, /node weight/i);
  assert.match(weights, /edge weight/i);
  assert.match(weights, /terminal weight/i);
  assert.match(weights, /10 forward rehearsal/i);
  assert.match(weights, /30 eligible forward/i);
  assert.match(weights, /20 sealed\s+unseen/i);
  assert.match(weights, /per-trade online updates/i);
  assert.match(weights, /shrinkage/i);
  assert.match(weights, /multi-metric objective/i);
  assert.match(weights, /promotion/i);
  assert.match(weights, /rollback/i);
  assert.match(downstream, /M7-DATA-EPISODE-CONTRACT/);
  assert.match(downstream, /M7-ENGINEER-WORKBENCH/);
  assert.match(downstream, /M7-STRATEGY-REHEARSAL-10/);
  assert.match(downstream, /M8-DATA-LEARNING-30-CONFIRM-20/);
  assert.match(downstream, /M8-STRATEGY-WEIGHT-DISPOSITION/);
  assert.match(downstream, /blockedBy/);
  assert.match(downstream, /owner/);
}

function transition(state, action, preferredNext) {
  const source = lifecycleAuthority.get(state);
  const row = source?.allowed_actions.find((candidate) => candidate.action === action);
  if (!row) return null;
  const nextStates = row.next_states ?? [];
  if (preferredNext && !nextStates.includes(preferredNext)) return null;
  return nextStates.length ? (preferredNext ?? nextStates[0]) : state;
}

function replayCase(fixture) {
  let state = "observe";
  let integrity = "valid_policy_episode";
  const actions = [];
  const path = [state];
  let overrideSeen = false;
  let confirmationCount = 0;
  let confirmationReady = true;
  let adverseCount = 0;
  let lastTs = null;
  const fail = (status) => { integrity = status; actions.push("quarantine"); };
  const emit = (action, next) => {
    const computed = transition(state, action, next);
    if (computed === null) return false;
    actions.push(action);
    state = computed;
    if (path.at(-1) !== state) path.push(state);
    return true;
  };
  for (const event of fixture.events) {
    if (integrity.startsWith("invalid_")) break;
    if (!event.ts || Number.isNaN(Date.parse(event.ts))) { fail("invalid_data"); break; }
    const ts = Date.parse(event.ts);
    if (lastTs !== null && ts < lastTs) { fail("invalid_causality"); break; }
    lastTs = ts;
    if (event.event !== "observe") {
      if (event.future_input || (event.observed_at && Date.parse(event.observed_at) > ts)) { fail("invalid_causality"); break; }
      if (event.policy_version !== expectedPolicyVersion || event.graph_version !== expectedGraphVersion) { fail("invalid_version_binding"); break; }
    }
    if (event.event === "observe" && ((event.policy_version !== undefined && event.policy_version !== expectedPolicyVersion) || (event.graph_version !== undefined && event.graph_version !== expectedGraphVersion))) { fail("invalid_version_binding"); break; }
    if (event.outcome_input || event.outcome_risk || event.outcome_reward || event.mfe !== undefined || event.mae !== undefined || (event.r !== undefined && event.event !== "exit")) { fail("invalid_data"); break; }
    const eventTimeStop = event.event === "stop_touch" || event.event === "stop_gap";
    if (eventTimeStop ? event.closed !== false : event.closed !== true) { fail("invalid_data"); break; }
    if (event.event === "observe") {
      if (state !== "observe" || event.bar_count !== undefined && event.bar_count < 0) { fail("invalid_state_transition"); break; }
      continue;
    }
    const explicitCollision = (event.same_bar_collision === true && event.finer_ordering !== true) || (event.stop_touched === true && (event.tp1_touched === true || event.tp2_touched === true) && event.finer_ordering !== true);
    const directionalStop = event.direction === "long" ? event.low <= event.stop : event.direction === "short" ? event.high >= event.stop : false;
    const directionalTarget = event.direction === "long" ? (event.high >= event.tp1 || event.high >= event.tp2) : event.direction === "short" ? (event.low <= event.tp1 || event.low <= event.tp2) : false;
    if (explicitCollision || (eventTimeStop && directionalStop && directionalTarget && event.finer_ordering !== true)) { fail("invalid_data"); break; }
    if (event.event === "recommendation") {
      if (state !== "observe" || !["enter", "wait"].includes(event.action)) { fail("invalid_state_transition"); break; }
      if (event.action === "enter" ? !emit("arm_entry", "armed") : !emit("wait", "no_trade")) { fail("invalid_state_transition"); break; }
      continue;
    }
    if (event.event === "human_override") {
      if (!["armed", "entered"].includes(state) || !event.rationale || !event.overridden_action) { fail("invalid_state_transition"); break; }
      overrideSeen = true;
      actions.push("override");
      continue;
    }
    if (event.event === "entry") {
      if (state !== "armed" || !event.direction || !Number.isFinite(event.entry_price)) { fail("invalid_state_transition"); break; }
      if (!emit("enter", "entered")) { fail("invalid_state_transition"); break; }
      continue;
    }
    if (event.event === "stop_touch" || event.event === "stop_gap") {
      if (!["entered", "unconfirmed", "confirmed", "weakened", "partial_exit", "trailing"].includes(state) || !event.direction || !Number.isFinite(event.stop)) { fail("invalid_state_transition"); break; }
      if (event.event === "stop_touch" && !directionalStop) { fail("invalid_data"); break; }
      if (event.event === "stop_gap") {
        const adverseGap = event.direction === "long" ? event.open < event.stop : event.direction === "short" ? event.open > event.stop : false;
        if (!adverseGap || event.fill !== event.open) { fail("invalid_data"); break; }
      }
      const action = event.event === "stop_touch" ? "hard_stop_touch" : "hard_stop_gap";
      if (!emit(action, "invalidated") || !emit("protective_stop", "protective_stop") || !emit("exit", "exited")) { fail("invalid_state_transition"); break; }
      actions.push("seal_outcome");
      continue;
    }
    if (event.event === "same_bar_collision") { fail("invalid_data"); break; }
    if (event.event === "confirmation") { fail("invalid_state_transition"); break; }
    if (event.event === "confirmation_bar") {
      const entryRelative = event.direction === "long" ? event.close > event.preceding_close && event.close > event.entry_price : event.direction === "short" ? event.close < event.preceding_close && event.close < event.entry_price : false;
      const paAligned = event.pa_direction === event.direction && event.pa_aligned === true;
      if (!["entered", "unconfirmed"].includes(state) || ![1, 2].includes(event.index) || event.index !== confirmationCount + 1 || event.hard_stop_triggered === true || typeof event.directional !== "boolean" || typeof event.pa_aligned !== "boolean" || !Number.isFinite(event.close) || !Number.isFinite(event.preceding_close) || !Number.isFinite(event.entry_price) || event.directional !== entryRelative || event.pa_aligned !== paAligned) { fail("invalid_state_transition"); break; }
      if (!emit("start_confirmation_window", "unconfirmed")) { fail("invalid_state_transition"); break; }
      confirmationCount += 1;
      confirmationReady &&= event.directional && event.pa_aligned;
      if (event.index === 2) {
        if (confirmationReady) {
          if (!emit("confirm", "confirmed")) { fail("invalid_state_transition"); break; }
        } else {
          if (!emit("failed_follow_through", "condition_exit") || !emit("exit", "exited")) { fail("invalid_state_transition"); break; }
          actions.push("seal_outcome");
        }
      }
      continue;
    }
    if (event.event === "adverse_close") {
      if (!["confirmed", "partial_exit", "trailing"].includes(state) || ![1, 2].includes(event.count) || event.count !== adverseCount + 1) { fail("invalid_state_transition"); break; }
      adverseCount = event.count;
      if (event.count === 1 || event.pa_context_supports !== false) {
        if (!emit("ordinary_pullback", "confirmed")) { fail("invalid_state_transition"); break; }
      } else if (!emit("weakening", "weakened")) { fail("invalid_state_transition"); break; }
      continue;
    }
    if (event.event === "weakening" || event.event === "trailing_ratchet") { fail("invalid_state_transition"); break; }
    if (event.event === "tp1_touch") {
      if (state !== "confirmed" || event.fraction !== undefined || event.same_bar_collision === true) { fail("invalid_state_transition"); break; }
      if (!emit("tp1_touch", "tp1_touch")) { fail("invalid_state_transition"); break; }
      continue;
    }
    if (event.event === "partial_exit") {
      if (state !== "tp1_touch" || event.fraction !== 0.5 || event.runner_fraction !== 0.5) { fail("invalid_data"); break; }
      if (!emit("tp1_half_exit", "partial_exit")) { fail("invalid_state_transition"); break; }
      continue;
    }
    if (event.event === "pivot_confirmed") {
      if (!["partial_exit", "trailing"].includes(state)) { fail("invalid_state_transition"); break; }
      const longCandidate = event.low_i - event.tick_size;
      const shortCandidate = event.high_i + event.tick_size;
      const longValid = event.direction === "long" && event.low_i < event.low_prev && event.low_i < event.low_next && event.candidate_stop === longCandidate && event.candidate_stop >= event.previous_stop;
      const shortValid = event.direction === "short" && event.high_i > event.high_prev && event.high_i > event.high_next && event.candidate_stop === shortCandidate && event.candidate_stop <= event.previous_stop;
      if (!longValid && !shortValid) { fail("invalid_replay"); break; }
      if (!emit("trailing_ratchet", "trailing")) { fail("invalid_state_transition"); break; }
      continue;
    }
    if (event.event === "study_cutoff") {
      if (!["entered", "unconfirmed", "confirmed", "partial_exit", "trailing", "weakened"].includes(state) || event.right_censored !== true) { fail("invalid_state_transition"); break; }
      if (!emit("right_censor", "right_censored")) { fail("invalid_state_transition"); break; }
      actions.push("record_right_censor");
      continue;
    }
    if (event.event === "exit") {
      if (event.reason === "tp2_terminal") {
        if (!["partial_exit", "trailing"].includes(state) || !emit("tp2", "exited")) { fail("invalid_state_transition"); break; }
      } else if (event.reason === "condition_exit") {
        if (state !== "condition_exit" || !emit("exit", "exited")) { fail("invalid_state_transition"); break; }
      } else if (event.reason === "structural_stop") {
        fail("invalid_state_transition");
        break;
      } else {
        fail("invalid_replay");
        break;
      }
      actions.push("seal_outcome");
      continue;
    }
    if (event.event === "management_input") { fail("invalid_replay"); break; }
    fail("invalid_replay");
  }
  if (!integrity.startsWith("invalid_") && state === "no_trade") actions.push("seal_no_trade");
  if (!integrity.startsWith("invalid_") && overrideSeen) integrity = "valid_human_override_episode";
  const terminal = integrity.startsWith("invalid_") ? integrity : state === "exited" ? "exited" : state === "no_trade" ? "no_trade" : state === "right_censored" ? "right_censored" : state;
  return { terminal, integrity, actions, path };
}

function validateReplayFixtures(replay) {
  assert.equal(replay.schema_version, "pa_decision_graph_replay_fixtures_v1");
  assert.equal(replay.policy_version, expectedPolicyVersion);
  assert.equal(replay.graph_version, expectedGraphVersion);
  const ids = replay.cases.map((fixture) => fixture.case_id);
  unique(ids, "replay fixture IDs");
  const requiredKinds = new Set(["no_trade", "valid_stop", "valid_trend", "human_override", "illegal_transition", "lookahead", "version_mismatch", "hard_stop_touch", "hard_stop_gap", "same_bar_collision", "single_pullback", "failed_follow_through", "tp1_runner", "pivot_ratchet", "right_censored", "human_override_lookahead", "tp1_before_entry", "weakening_before_confirmation", "trailing_before_tp1", "direct_structural_exit", "stop_target_collision"]);
  setEquals(new Set(replay.cases.map((fixture) => fixture.kind)), requiredKinds, "replay fixture coverage");
  assert.equal(replay.cases.length, requiredKinds.size, "one replay fixture per required kind");
  for (const fixture of replay.cases) {
    const first = replayCase(fixture);
    const second = replayCase(fixture);
    assert.equal(JSON.stringify(first), JSON.stringify(second), `${fixture.case_id}: replay must be byte-deterministic`);
    assert.equal(first.terminal, fixture.expected_terminal, `${fixture.case_id}: terminal`);
    assert.equal(first.integrity, fixture.expected_integrity, `${fixture.case_id}: integrity`);
    assert.deepEqual(first.actions, fixture.expected_actions, `${fixture.case_id}: actions`);
    if (fixture.expected_path) assert.deepEqual(first.path, fixture.expected_path, `${fixture.case_id}: state path`);
    if (fixture.expected_integrity.startsWith("invalid_")) assert.match(fixture.counterexample ?? "", /reject|invalid|ambiguous|before|without/i, `${fixture.case_id}: exact counterexample description`);
    if (fixture.eligible_for_learning !== undefined) assert.equal(fixture.eligible_for_learning, first.integrity === "valid_policy_episode" && first.terminal === "exited");
  }
}

function eligibility(row) {
  const validPolicyShape = row.integrity === "valid_policy_episode" && row.policy_present === true && row.override_present === false;
  const validOverrideShape = row.integrity === "valid_human_override_episode" && row.policy_present === true && row.override_present === true;
  const shapeValid = validPolicyShape || validOverrideShape;
  const quarantined = row.integrity.startsWith("invalid_") || !shapeValid;
  return {
    baseline_eligible: validPolicyShape && row.outcome_complete === true,
    outcome_eligible: shapeValid && row.outcome_complete === true,
    quarantined
  };
}

function validateEligibilityFixtures(fixture) {
  assert.equal(fixture.schema_version, "pa_episode_eligibility_fixtures_v1");
  assert.equal(fixture.rows.length, integrityStatuses.size * 8, "eligibility matrix is exhaustive");
  unique(fixture.rows.map((row) => row.case_id), "eligibility fixture IDs");
  const combinations = new Set();
  for (const row of fixture.rows) {
    assert.ok(integrityStatuses.has(row.integrity), `${row.case_id}: integrity vocabulary`);
    const key = `${row.integrity}|${row.policy_present ? 1 : 0}|${row.override_present ? 1 : 0}|${row.outcome_complete ? 1 : 0}`;
    assert.ok(!combinations.has(key), `${row.case_id}: duplicate matrix cell`);
    combinations.add(key);
    assert.deepEqual(eligibility(row), { baseline_eligible: row.baseline_eligible, outcome_eligible: row.outcome_eligible, quarantined: row.quarantined }, row.case_id);
  }
  assert.equal(combinations.size, integrityStatuses.size * 8);
  for (const row of fixture.rows.filter((candidate) => candidate.integrity.startsWith("invalid_") && candidate.outcome_r > 0)) assert.equal(eligibility(row).quarantined, true, `${row.case_id}: profitable invalid row`);
}

function validateDocumentation(readme, manifest, lifecycle) {
  const terminalMatches = [...readme.matchAll(/Terminal: `([^`]+)`/g)].map((match) => match[1]);
  assert.deepEqual(terminalMatches, [expectedTerminal], "README records exactly one terminal");
  assert.match(readme, /source_fidelity_measurement_failure/);
  assert.match(readme, /no automatic order routing/i);
  assert.match(readme, /no.*execution/i);
  assert.match(readme, /protocol_ready_for_m7.*authorizes creation of the M7/i);
  assert.match(readme, /needs_revision.*authorize none/is);
  assert.match(readme, /pi_management_adjudication_v1\.md/);
  assert.ok(Array.isArray(manifest.unmapped_branches), "manifest records unmapped_branches");
  assert.equal(lifecycle.management_policy_status, "accepted");
  const required = [names.readme, names.manifest, names.registry, names.lifecycle, names.adjudication, names.episode, names.weights, names.downstream, names.verifier, names.replay, names.eligibility];
  for (const relative of required) assert.ok(existsSync(join(here, relative)), `required artifact ${relative}`);
}

function validatePackage() {
  const manifest = json(names.manifest);
  const registry = json(names.registry);
  const lifecycle = json(names.lifecycle);
  const replay = json(names.replay);
  const eligibilityFixture = json(names.eligibility);
  const readme = text(names.readme);
  const adjudication = text(names.adjudication);
  const episode = text(names.episode);
  const weights = text(names.weights);
  const downstream = text(names.downstream);
  const selectedBranches = validateManifest(manifest, registry);
  const registryNodes = validateRegistry(registry, selectedBranches, lifecycle);
  lifecycleAuthority = validateLifecycle(lifecycle, registryNodes);
  validateGraphLifecycle(registry, lifecycle);
  validateAdjudication(adjudication, lifecycle);
  validateEpisodeDocs(episode, weights, downstream);
  validateReplayFixtures(replay);
  validateEligibilityFixtures(eligibilityFixture);
  validateDocumentation(readme, manifest, lifecycle);
  assert.equal(expectedTerminal, "needs_revision");
  assert.ok(lifecycle.unresolved_management_branches.every((row) => row.selected), "all PI rows must be explicitly selected");
  return { manifest, registry, lifecycle, replay, eligibilityFixture };
}

function validateNegative(base) {
  let count = 0;
  const replayMutation = (kind) => {
    const fixture = base.replay.cases.find((candidate) => candidate.kind === kind);
    return replayCase({ ...fixture, expected_terminal: "exited", expected_integrity: "valid_policy_episode", expected_actions: [] });
  };
  const mutations = [
    ["manifest commit drift", () => validateManifest({ ...base.manifest, upstream: { ...base.manifest.upstream, commit: "0".repeat(40) } }, base.registry)],
    ["manifest hash drift", () => validateManifest({ ...base.manifest, selected_files: base.manifest.selected_files.map((entry, index) => index === 0 ? { ...entry, sha256: "0".repeat(64) } : entry) }, base.registry)],
    ["manifest reference digest drift", () => validateManifest({ ...base.manifest, existing_paired_trading_references: base.manifest.existing_paired_trading_references.map((entry, index) => index === 0 ? { ...entry, sha256: "0".repeat(64) } : entry) }, base.registry)],
    ["registry duplicate edge", () => validateRegistry({ ...base.registry, edges: [...base.registry.edges, base.registry.edges[0]] }, base.manifest.selected_files.flatMap((entry) => entry.selected_branch_ids), base.lifecycle)],
    ["registry unknown node", () => validateRegistry({ ...base.registry, edges: base.registry.edges.map((edge, index) => index === 0 ? { ...edge, to: "unknown" } : edge) }, base.manifest.selected_files.flatMap((entry) => entry.selected_branch_ids), base.lifecycle)],
    ["lifecycle edge provenance inflation", () => validateRegistry({ ...base.registry, edges: base.registry.edges.map((edge) => edge.from.startsWith("lifecycle.") ? { ...edge, provenance_class: "upstream_pa" } : edge) }, base.manifest.selected_files.flatMap((entry) => entry.selected_branch_ids), base.lifecycle)],
    ["registry lifecycle divergence", () => validateGraphLifecycle({ ...base.registry, edges: base.registry.edges.filter((edge) => edge.edge_id !== "e.unconfirmed.window") }, base.lifecycle)],
    ["lifecycle hidden default", () => validateLifecycle({ ...base.lifecycle, unresolved_management_branches: base.lifecycle.unresolved_management_branches.map((row, index) => index === 0 ? { ...row, selected: null } : row) }, new Map(base.registry.nodes.map((node) => [node.node_id, node])))],
    ["lifecycle action vocabulary drift", () => validateLifecycle({ ...base.lifecycle, action_vocabulary: base.lifecycle.action_vocabulary.filter((action) => action !== "hard_stop_gap") }, new Map(base.registry.nodes.map((node) => [node.node_id, node])))],
    ["future input accepted", () => assert.equal(replayMutation("lookahead").integrity, "valid_policy_episode")],
    ["future human override accepted", () => assert.equal(replayMutation("human_override_lookahead").integrity, "valid_human_override_episode")],
    ["TP1 before entry accepted", () => assert.equal(replayMutation("tp1_before_entry").integrity, "valid_policy_episode")],
    ["weakening before confirmation accepted", () => assert.equal(replayMutation("weakening_before_confirmation").integrity, "valid_policy_episode")],
    ["trailing before TP1 accepted", () => assert.equal(replayMutation("trailing_before_tp1").integrity, "valid_policy_episode")],
    ["direct structural exit accepted", () => assert.equal(replayMutation("direct_structural_exit").integrity, "valid_policy_episode")],
    ["stop target collision accepted", () => assert.equal(replayMutation("stop_target_collision").integrity, "valid_policy_episode")],
    ["eligibility profitable invalid", () => assert.equal(eligibility({ policy_present: true, override_present: false, outcome_complete: true, integrity: "invalid_causality", outcome_r: 4 }).baseline_eligible, true)]
  ];
  for (const [label, mutation] of mutations) {
    expectReject(mutation, label);
    count += 1;
  }
  return count;
}

const result = validatePackage();
if (process.argv.includes("--negative")) {
  const count = validateNegative(result);
  console.log(`negative mutations: PASS (${count}/${count} rejected)`);
} else {
  console.log(`PA decision-graph protocol verification: PASS (${expectedTerminal}; PI semantic repair under review)`);
}
