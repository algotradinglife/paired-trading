import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

const sources = {
  capability:
    "doc/repro/pa-feitian-phase1-data-capability-2026-07-30/candidate_capability_inventory_v1.json",
  interfaces:
    "doc/repro/pa-feitian-phase1-data-capability-2026-07-30/candidate_interface_audit_v1.json",
  underlying:
    "doc/repro/pa-feitian-m6-underlying-corpus-2026-07-12/underlying_signal_corpus_v1.json",
  underlyingContract:
    "docs/research/pa-feitian-m6-underlying-corpus-contract-v1.json",
  bareK:
    "doc/repro/pa-feitian-m6-historical-swing-induction-2026-07-12/historical_swing_atlas_v1.json",
  swingLine:
    "doc/repro/pa-feitian-m6-causal-swing-line-induction-2026-07-13/causal_swing_line_atlas_v1.json",
  swingLineProtocol:
    "docs/research/pa-feitian-m6-causal-swing-line-induction-protocol-v1.json",
  negativeGate:
    "doc/repro/pa-feitian-m6-premium-k-response-2026-07-13/premium_k_response_atlas_v1.json",
  swingViews:
    "doc/repro/pa-feitian-m6-exploratory-swing-views-2026-07-30/exploratory_swing_views_v1.json",
  xiaoSystem: "doc/xiao-feitian-options-timing-system-2026-06-16.md",
};

const expectedHashes = {
  capability:
    "7f3be73b04c797e849daf828e0d38783b60830c0dce0dd100324f7fac822afcb",
  interfaces:
    "becb9bc6b65c54908eac7ad4d3e39a3591d92e65e1e07f2a3b086e096a39f795",
  underlying:
    "cb3407910dd15f4327a2465da3a00d6797f81fd9124066695887ddb53d3bf080",
  underlyingContract:
    "e35d4567792a386270989b47af31d4e2e23d76b632eff92cabc6188f8ba37c34",
  bareK:
    "f8f4d678625764accf8af65cf8198e8c33504b00f2b32488145ac83e79251df1",
  swingLine:
    "f65eadb4c5e6468b02fb01e717b4997af53ed5db0be57d82dcfa3d72006c9de8",
  swingLineProtocol:
    "0b7bf0324cfa10627916ec009281a462c2aa23504fbd11b9038790c48156aa5f",
  negativeGate:
    "61c41f3de571f4f27da54665e14d3b0994524883d0aa34d1cbc568f6dc4bd0c8",
  swingViews:
    "e8e1e3ea2f6c6fc158055feda9a7662da6a1a16e695ea3693a1663c8cd0e1809",
  xiaoSystem:
    "67bf64a897a85fe034925a13954489e4a09765ef887aa33b9e2d4941001769cb",
};

const loaded = {};
for (const [name, path] of Object.entries(sources)) {
  const bytes = await readFile(path);
  const digest = createHash("sha256").update(bytes).digest("hex");
  assert.equal(digest, expectedHashes[name], `${name} source binding drifted`);
  loaded[name] =
    name === "xiaoSystem" ? bytes.toString("utf8") : JSON.parse(bytes);
}

assert.deepEqual(
  loaded.interfaces.decision_surface.map((row) => row.instrument_family),
  ["SHFE.au", "SHFE.ag", "CZCE.TA", "CZCE.MA", "SHFE.cu", "DCE.i"],
);
assert.equal(loaded.capability.decision.usable_family_count, 0);
assert.equal(loaded.capability.decision.p1_exp_001_action, "stop_as_data_blocked");

const levelOrder = ["D", "W", "60min", "15min"];
const expectedUnderlying = {
  au: {
    records: 333,
    minDate: "2025-01-02",
    maxDate: "2026-06-05",
    dailyBreakoutUp: 50,
    dailyBreakoutDown: 6,
    alignedUp: 48,
    alignedDown: 2,
    mixedAlignment: 198,
    expandedDaily: 61,
    intradayAnyBreakout: 29,
    intradayBreakoutDailyNone: 21,
  },
  ag: {
    records: 337,
    minDate: "2025-01-02",
    maxDate: "2026-06-05",
    dailyBreakoutUp: 44,
    dailyBreakoutDown: 4,
    alignedUp: 40,
    alignedDown: 0,
    mixedAlignment: 213,
    expandedDaily: 60,
    intradayAnyBreakout: 33,
    intradayBreakoutDailyNone: 27,
  },
};

for (const product of ["au", "ag"]) {
  const records = loaded.underlying.records.filter(
    (record) => record.product === product,
  );
  const summary = {
    records: records.length,
    minDate: records.reduce(
      (minimum, record) =>
        minimum === null || record.trading_date < minimum
          ? record.trading_date
          : minimum,
      null,
    ),
    maxDate: records.reduce(
      (maximum, record) =>
        maximum === null || record.trading_date > maximum
          ? record.trading_date
          : maximum,
      null,
    ),
    dailyBreakoutUp: 0,
    dailyBreakoutDown: 0,
    alignedUp: 0,
    alignedDown: 0,
    mixedAlignment: 0,
    expandedDaily: 0,
    intradayAnyBreakout: 0,
    intradayBreakoutDailyNone: 0,
  };

  for (const record of records) {
    const dailyBreakout = record.levels.D.signals.breakout_20;
    const alignments = levelOrder.map(
      (level) => record.levels[level].signals.ema_alignment,
    );
    if (dailyBreakout === "up") summary.dailyBreakoutUp += 1;
    if (dailyBreakout === "down") summary.dailyBreakoutDown += 1;
    if (
      dailyBreakout === "up" &&
      alignments.every((alignment) => alignment === "above")
    ) {
      summary.alignedUp += 1;
    }
    if (
      dailyBreakout === "down" &&
      alignments.every((alignment) => alignment === "below")
    ) {
      summary.alignedDown += 1;
    }
    if (new Set(alignments).size > 1) summary.mixedAlignment += 1;
    if (record.levels.D.diagnostics.range_over_prior_20_mean >= 1.5) {
      summary.expandedDaily += 1;
    }
    const intradayBreakout = ["60min", "15min"].some(
      (level) => record.levels[level].signals.breakout_20 !== "none",
    );
    if (intradayBreakout) summary.intradayAnyBreakout += 1;
    if (intradayBreakout && dailyBreakout === "none") {
      summary.intradayBreakoutDailyNone += 1;
    }
  }
  assert.deepEqual(summary, expectedUnderlying[product]);
}

assert.equal(
  loaded.underlyingContract.aggregation.W,
  "OHLCV/OI over ISO year/week of causal D bars, including the decision-time partial week",
);
assert.equal(loaded.bareK.coverage.trace_class_counts.training.total, 122);
assert.equal(loaded.bareK.coverage.trace_class_counts.training.distinct, 54);
assert.equal(loaded.bareK.coverage.trace_class_counts.holdout.total, 449);
assert.equal(loaded.bareK.coverage.trace_class_counts.holdout.distinct, 132);
assert.equal(
  loaded.bareK.induced_definition.shared_training_trace_class_count,
  13,
);

const swingTraining = loaded.swingLine.coverage.global_label_counts.training;
const swingHoldout = loaded.swingLine.coverage.global_label_counts.holdout;
assert.equal(swingTraining.total, 434);
assert.equal(swingTraining.by_label.abstain, 194);
assert.equal(swingTraining.by_label.conflict, 46);
assert.equal(swingHoldout.total, 449);
assert.equal(swingHoldout.by_label.abstain, 169);
assert.equal(swingHoldout.by_label.conflict, 103);
assert.equal(
  loaded.swingLineProtocol.causal_proxy_semantics.tolerance.formula,
  "0.25 times the median of high-low ranges of exactly the 20 completed bars before the decision bar",
);
assert.match(loaded.xiaoSystem, /1B\/2B\/3B/);
assert.match(loaded.xiaoSystem, /DD 线/);

assert.deepEqual(
  loaded.negativeGate.training_candidate_freeze.candidate_set,
  [],
);
assert.equal(
  loaded.negativeGate.holdout_application.status,
  "not_applied_no_training_candidates",
);

const expectedSwingViews = [
  ["SHFE.au", 405, 405, 186],
  ["SHFE.ag", 651, 651, 319],
  ["CZCE.TA", 379, 351, 26],
  ["CZCE.MA", 379, 345, 30],
  ["SHFE.cu", 750, 750, 324],
  ["DCE.i", 662, 662, 109],
];
assert.deepEqual(
  loaded.swingViews.family_window_summaries.map((row) => [
    row.instrument_family,
    row.all_complete_windows.window_count,
    row.all_complete_windows.quality_counts.clean,
    row.representative_eligible_clean_windows.window_count,
  ]),
  expectedSwingViews,
);
assert.equal(
  loaded.swingViews.family_window_summaries.reduce(
    (total, row) => total + row.all_complete_windows.window_count,
    0,
  ),
  3226,
);
assert.equal(
  loaded.swingViews.family_window_summaries.reduce(
    (total, row) =>
      total + row.representative_eligible_clean_windows.window_count,
    0,
  ),
  994,
);
assert.equal(loaded.swingViews.representative_swing_views.length, 18);
assert.ok(
  loaded.swingViews.representative_swing_views.every(
    (view) =>
      view.normalized_ohlc_path.length === 20 &&
      view.input_quality.status === "clean" &&
      view.option_premium_overlay.quality_status === "invalid",
  ),
);
assert.equal(
  loaded.swingViews.representative_swing_views.filter(
    (view) =>
      view.option_premium_overlay.comparable_complete_path_metrics.status ===
      "unavailable",
  ).length,
  2,
);
assert.equal(loaded.swingViews.strategy_handoff.all_six_families_retained, true);
assert.equal(
  loaded.swingViews.evidence_separation.p1_exp_001_or_p1_exp_002_outcomes,
  "not accessed",
);
assert.equal(loaded.swingViews.evidence_separation.issue_51_unblocked, false);

console.log(
  JSON.stringify({
    ok: true,
    issue: 52,
    decision: "advance_sr_01_to_issue_49_definition_only",
    source_bindings: Object.keys(sources).length,
  }),
);
