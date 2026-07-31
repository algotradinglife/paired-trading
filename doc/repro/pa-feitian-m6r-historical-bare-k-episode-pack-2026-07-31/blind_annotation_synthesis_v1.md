# Blind M6R bare-K first-pass synthesis

This note was written from the anonymous 40-bar pack only. It does not use
episode provenance, family, date, activity/control role, reveal data, raw
history, or later bars.

## Blind codebook

The annotator used only the 40 bars in each episode, including bar 0. These
are descriptive measurement procedures, not trade thresholds:

- Context is `rising` when close(0) minus close(-39) exceeds 1.2% of the
  median close; `falling` uses the negative counterpart; otherwise it is
  `mixed`.
- Local turns count sign changes in consecutive close differences, using all
  adjacent bars in the 40-bar window and no later information.
- For range behavior, candle range is high minus low (not true range, which
  includes prior-close gaps). Compare the mean of the last five candle ranges
  with the median of the preceding ten, non-overlapping ranges: above 1.25x
  is `expanding`, below 0.8x is `narrowing`, otherwise `comparable`.
- The recent boundary is the maximum high and minimum low over bars -5
  through -1. Bar 0 is a probe when its high/low crosses a boundary but its
  close returns inside; a boundary close is recorded when its close finishes
  outside; otherwise compute `(close0 - recent_low) / (recent_high -
  recent_low)`: upper is strictly above 2/3, lower strictly below 1/3, and
  middle is otherwise. A degenerate range is middle.

## Blind counts

All 72 episodes are represented. Context counts are rising 36, falling 27,
and mixed 9. Range counts are comparable 45, expanding 15, and narrowing 12.
Bar-0 descriptions count 14 middle-third closes, 14 upper-third closes, 14
lower-third closes, 10 lower-boundary closes, 6 upper-boundary closes, 10
upper probes, and 4 lower probes.

The largest context/range clusters are falling+comparable (20),
rising+comparable (19), rising+expanding (11), rising+narrowing (6),
mixed+comparable (6), falling+narrowing (5), mixed+expanding (2),
falling+expanding (2), and mixed+narrowing (1). These are blind structural
clusters only; they are not source, role, or performance groups.

Recurring observation vocabulary:

- rising, falling, or mixed close context;
- alternating local turns and swing congestion;
- recent range expansion, narrowing, or persistence;
- bar-0 probes beyond a recent boundary, closes beyond a boundary, or closes
  in the upper, middle, or lower portion of the local range.

Ambiguity is structural: a 40-bar window cannot establish persistence, cause,
identity, or what follows bar 0. A probe and a close beyond a boundary can be
described, but their continuation or failure is not knowable in the blind
window. A mixed close sequence can contain many turns without defining a
stable regime.

Ambiguous structural clusters include boundary probes that return inside the
recent range, mixed close movements with many local turns, and windows where
range expansion occurs without a single uninterrupted close movement. A 40-bar
window cannot decide whether these are continuation, rejection, or transient
shape.

Questions reserved for a later comparison issue:

1. Do the same structural descriptions recur consistently across revealed
   groups without adding identity or performance information?
2. Which boundary probes and close-location descriptions remain ambiguous
   when a separate comparison is authorized?
3. Which structural clusters require a more precise observation codebook before
   any hypothesis is considered?

No question here authorizes a direction label, threshold, entry, stop, outcome,
ranking, or strategy hypothesis.
