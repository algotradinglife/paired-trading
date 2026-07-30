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
  bareK:
    "doc/repro/pa-feitian-m6-historical-swing-induction-2026-07-12/historical_swing_atlas_v1.json",
  swingLine:
    "doc/repro/pa-feitian-m6-causal-swing-line-induction-2026-07-13/causal_swing_line_atlas_v1.json",
  negativeGate:
    "doc/repro/pa-feitian-m6-premium-k-response-2026-07-13/premium_k_response_atlas_v1.json",
};

const expectedHashes = {
  capability:
    "7f3be73b04c797e849daf828e0d38783b60830c0dce0dd100324f7fac822afcb",
  interfaces:
    "becb9bc6b65c54908eac7ad4d3e39a3591d92e65e1e07f2a3b086e096a39f795",
  underlying:
    "cb3407910dd15f4327a2465da3a00d6797f81fd9124066695887ddb53d3bf080",
  bareK:
    "f8f4d678625764accf8af65cf8198e8c33504b00f2b32488145ac83e79251df1",
  swingLine:
    "f65eadb4c5e6468b02fb01e717b4997af53ed5db0be57d82dcfa3d72006c9de8",
  negativeGate:
    "61c41f3de571f4f27da54665e14d3b0994524883d0aa34d1cbc568f6dc4bd0c8",
};

const loaded = {};
for (const [name, path] of Object.entries(sources)) {
  const bytes = await readFile(path);
  const digest = createHash("sha256").update(bytes).digest("hex");
  assert.equal(digest, expectedHashes[name], `${name} source binding drifted`);
  loaded[name] = JSON.parse(bytes);
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

assert.deepEqual(
  loaded.negativeGate.training_candidate_freeze.candidate_set,
  [],
);
assert.equal(
  loaded.negativeGate.holdout_application.status,
  "not_applied_no_training_candidates",
);

console.log(
  JSON.stringify({
    ok: true,
    issue: 52,
    decision: "stop_before_p1_exp_002_freeze",
    source_bindings: Object.keys(sources).length,
  }),
);
