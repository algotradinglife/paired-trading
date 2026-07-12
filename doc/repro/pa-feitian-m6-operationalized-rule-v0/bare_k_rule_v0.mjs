/**
 * Deterministic evaluator for operationalized_bare_k_v0.
 *
 * The evaluator emits structural research states only.  It does not select an
 * instrument, place an order, calculate a price, or evaluate an outcome.
 */

export const RULE_ID = "operationalized_bare_k_v0";
export const STATUS_LABEL = "operationalized_hypothesis_not_authentic";
export const OBSERVATION_WINDOW_BARS = 9;

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function validateBar(bar) {
  if (!bar || typeof bar.id !== "string") return "id is required";
  for (const key of ["open", "high", "low", "close"]) {
    if (!isFiniteNumber(bar[key])) return `${key} must be finite`;
  }
  if (bar.high < Math.max(bar.open, bar.close)) return "high is below open or close";
  if (bar.low > Math.min(bar.open, bar.close)) return "low is above open or close";
  if (bar.high < bar.low) return "high is below low";
  return null;
}

function findPivots(bars, start, end, field, kind) {
  const pivots = [];
  for (let index = Math.max(start + 1, 1); index <= Math.min(end - 1, bars.length - 2); index += 1) {
    const value = bars[index][field];
    const before = bars[index - 1][field];
    const after = bars[index + 1][field];
    const isPivot = kind === "low"
      ? value < before && value < after
      : value > before && value > after;
    if (isPivot) pivots.push({ index, value });
  }
  return pivots;
}

function latestLine(pivots, expectedSlope) {
  if (pivots.length < 2) return null;
  const first = pivots[pivots.length - 2];
  const second = pivots[pivots.length - 1];
  const slope = (second.value - first.value) / (second.index - first.index);
  if ((expectedSlope === "descending" && slope >= 0) || (expectedSlope === "ascending" && slope <= 0)) {
    return null;
  }
  return { first, second, slope };
}

function project(line, index) {
  return line.second.value + line.slope * (index - line.second.index);
}

function lineTrace(line, index) {
  if (!line) return null;
  return {
    pivot_indices: [line.first.index, line.second.index],
    slope: line.slope,
    projected_at_decision: project(line, index)
  };
}

function traceBase(bars, decisionIndex, start) {
  return {
    rule_id: RULE_ID,
    status_label: STATUS_LABEL,
    decision_index: decisionIndex,
    observation_start_index: start,
    observation_end_index: decisionIndex,
    observed_bar_ids: bars.slice(start, decisionIndex + 1).map((bar) => bar.id),
    timing: "evaluated only after the decision bar is closed"
  };
}

function abstain(reason, base, details = {}) {
  return {
    decision: "abstain",
    direction: "none",
    state: reason,
    trace: { ...base, ...details }
  };
}

/**
 * Evaluate the last completed bar.  Bars must be ordered oldest to newest.
 */
export function evaluateBareK(bars) {
  if (!Array.isArray(bars)) {
    return abstain("abstain_invalid_input", { rule_id: RULE_ID, status_label: STATUS_LABEL }, { reason: "bars must be an array" });
  }
  const decisionIndex = bars.length - 1;
  for (let index = 0; index < bars.length; index += 1) {
    const reason = validateBar(bars[index]);
    if (reason) {
      return abstain("abstain_invalid_bar", { rule_id: RULE_ID, status_label: STATUS_LABEL, decision_index: decisionIndex }, {
        invalid_bar_index: index,
        reason
      });
    }
  }
  if (bars.length < OBSERVATION_WINDOW_BARS) {
    return abstain("abstain_missing_window", { rule_id: RULE_ID, status_label: STATUS_LABEL, decision_index: decisionIndex }, {
      required_bars: OBSERVATION_WINDOW_BARS,
      observed_bars: bars.length
    });
  }

  const start = decisionIndex - OBSERVATION_WINDOW_BARS + 1;
  const base = traceBase(bars, decisionIndex, start);
  const current = bars[decisionIndex];

  // Every pivot is confirmed by its immediate successor, which is no later
  // than the decision bar.  This makes the geometry causal by construction.
  const lowPivots = findPivots(bars, start, decisionIndex + 1, "low", "low");
  const highPivots = findPivots(bars, start, decisionIndex + 1, "high", "high");
  const descendingLowLine = latestLine(lowPivots, "descending");
  const descendingHighLine = latestLine(highPivots, "descending");
  const ascendingHighLine = latestLine(highPivots, "ascending");
  const ascendingLowLine = latestLine(lowPivots, "ascending");

  const longDd = descendingLowLine ? project(descendingLowLine, decisionIndex) : null;
  const longBreak = descendingHighLine ? project(descendingHighLine, decisionIndex) : null;
  const shortDd = ascendingHighLine ? project(ascendingHighLine, decisionIndex) : null;
  const shortBreak = ascendingLowLine ? project(ascendingLowLine, decisionIndex) : null;

  const longInvalidated = longDd !== null && current.close < longDd;
  const shortInvalidated = shortDd !== null && current.close > shortDd;
  const longCandidate = longDd !== null
    && current.low <= longDd
    && current.close >= longDd
    && current.close > current.open;
  const shortCandidate = shortDd !== null
    && current.high >= shortDd
    && current.close <= shortDd
    && current.close < current.open;
  const longConfirmed = longBreak !== null && current.close > longBreak;
  const shortConfirmed = shortBreak !== null && current.close < shortBreak;

  const details = {
    pivot_indices: {
      lows: lowPivots.map((pivot) => pivot.index),
      highs: highPivots.map((pivot) => pivot.index)
    },
    lines: {
      descending_lows_dd: lineTrace(descendingLowLine, decisionIndex),
      descending_highs_break: lineTrace(descendingHighLine, decisionIndex),
      ascending_highs_dd_mirror: lineTrace(ascendingHighLine, decisionIndex),
      ascending_lows_break_mirror: lineTrace(ascendingLowLine, decisionIndex)
    },
    predicates: {
      long_invalidated: longInvalidated,
      short_invalidated: shortInvalidated,
      long_candidate: longCandidate,
      short_candidate: shortCandidate,
      long_confirmed: longConfirmed,
      short_confirmed: shortConfirmed
    }
  };

  // Conflict precedence is intentional: invalidation outranks all positive
  // states; a left-side candidate outranks a right-side confirmation.
  if (longInvalidated && shortInvalidated) return abstain("abstain_conflicting_invalidations", base, details);
  if (longInvalidated) return { decision: "invalidate", direction: "long_structural_reversal", state: "invalidated_long", trace: { ...base, ...details } };
  if (shortInvalidated) return { decision: "invalidate", direction: "short_structural_reversal", state: "invalidated_short", trace: { ...base, ...details } };
  if (longCandidate && shortCandidate) return abstain("abstain_conflicting_candidates", base, details);
  if (longCandidate) return { decision: "candidate", direction: "long_structural_reversal", state: "left_candidate_long", trace: { ...base, ...details } };
  if (shortCandidate) return { decision: "candidate", direction: "short_structural_reversal", state: "left_candidate_short", trace: { ...base, ...details } };
  if (longConfirmed && shortConfirmed) return abstain("abstain_conflicting_confirmations", base, details);
  if (longConfirmed) return { decision: "confirm", direction: "long_structural_reversal", state: "right_confirmation_long", trace: { ...base, ...details } };
  if (shortConfirmed) return { decision: "confirm", direction: "short_structural_reversal", state: "right_confirmation_short", trace: { ...base, ...details } };
  if (!descendingLowLine && !descendingHighLine && !ascendingHighLine && !ascendingLowLine) {
    return abstain("abstain_insufficient_structure", base, details);
  }
  return abstain("abstain_no_setup", base, details);
}
