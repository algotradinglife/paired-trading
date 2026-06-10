# Options-layer ag/au P&L attribution — slice 1 — 2026-06-10

**Headline verdict: MODEL_DOMINATED — not a market-validated edge.** Both ag and
au score `verdict=PROMOTE` on premium-multiple EV, but **79–95% of the simulated
P&L is Black-76 model-priced** (the exact emitted OTM strikes have almost no
daily market data), so the verdict reflects the **IV assumption**, not measured
market edge. It is **IV-sensitive**: au flips REGIME_ONLY↔PROMOTE between IV
0.20 and 0.085. Treat both as **monitoring-grade**, not promotions.

This is the intended, honest outcome of slice 1: it binds an auditable
attribution to the live emission and **quantifies why the options layer remains
effectively unverified from market data** at the emitted strikes.

## What was built

`backtest_options_attribution.py` replays the live ag/au `options_calls`
emission and attributes premium P&L. Spec/plan:
`docs/superpowers/specs/2026-06-10-options-attribution-design.md`,
`docs/superpowers/plans/2026-06-10-options-attribution.md`.

- **Replay (faithful to production):** 4 emitters — bpull, pa_h2, context_a,
  divergence — reproducing `score_today`'s exact gates (verified against
  `score_today.py:940-1303`): each gated on `policy_weight(symbol=sym) > 0`;
  pa_h2 additionally skips `PAStructure.phase == "BULL"`; emission requires
  `score >= 3` (= h=opposing for bpull/pa_h2, conditional-pass for context_a).
  **divergence emits 0** — the DIF-detector family is off in production
  (`include_dif_detectors=False`); guarded by a test.
- **Entry:** signal-day close on the Rank-1 (nearest-OTM) emitted call.
- **Exit:** validated DD-line model (`simulate_entry`): take1=2×/take2=4×,
  stop=5 ticks (ag 1.0 / au 2.0), max_hold=30d. `ev_mult` = premium multiple
  (1.0 = breakeven).
- **Pricing:** real contract daily OHLC where available, else Black-76 over the
  underlying path (`modeled_fraction` reported). IV pinned from observed
  market-covered ATM IV medians: **ag 0.13 (n=6), au 0.085 (n=32)**.
- **Folds:** IS ≤ 2023 / OOS ≥ 2024. **Verdict:** PROMOTE iff ev_mult>1 in both
  folds; REGIME_ONLY iff OOS-only; REJECT iff neither. **Reliability:**
  MODEL_DOMINATED iff modeled_fraction > 0.5.

## Results (pinned IV; `baselines/options_{ag,au}.json`)

| underlying | verdict | reliability | IS ev_mult (n) | OOS ev_mult (n) | modeled_fraction | market_n |
|---|---|---|---|---|---|---|
| ag | PROMOTE | MODEL_DOMINATED | 1.186 (50) | 1.093 (32) | 0.951 | 4 |
| au | PROMOTE | MODEL_DOMINATED | 1.097 (37) | 2.137 (48) | 0.788 | 18 |

By emitter (ev_mult): ag — bpull 1.213, pa_h2 1.147, context_a 1.026; au —
context_a 1.902, bpull 1.655, pa_h2 1.364. Win-rate is low (ag rank1 ~13%) with
ev_mult>1 — the option long-tail asymmetry (few large winners), consistent with
the validated DD-line shape.

(Numbers reflect the Codex-review fixes: the modeled path is truncated at
contract expiry — previously it priced past expiry, inflating au's multiples —
and the real-data loader now tries all dated snapshots before falling back to
the model. The expiry fix lowered au IS 1.31→1.097 / OOS 2.37→2.137; ag was
unaffected.)

## The decisive caveat: IV sensitivity under model dominance

au, by IV assumption (everything else fixed):

| IV | IS ev_mult | OOS ev_mult | verdict |
|---|---|---|---|
| 0.20 (placeholder) | 0.479 | 1.186 | REGIME_ONLY |
| 0.085 (pinned) | 1.097 | 2.137 | PROMOTE |

Lower entry IV → cheaper entry premium → larger premium multiples on the same
underlying move. With ~79% of au trades (and ~95% of ag) priced by the model,
the verdict is a function of the IV input. **We cannot validate the options
layer's edge from market data at the emitted strikes** — the daily coverage of
those exact strikes is too thin (ag market_n=4, au market_n=18 over full
history).

## Cross-check vs prior findings

au scoring REGIME_ONLY at the placeholder IV corroborates
`project_ddline_options_findings` (au B1/B2 IS validation fails — a 2025
gold-bull regime play, not a robust edge). **But** those DD-line findings were
computed on **real intraday option K-line data** with a DD-line entry — a richer
data path this slice deliberately does not use (we attribute the exact emitted
daily strike to bind to the live emission). The discrepancy is about the data
path, not a contradiction.

## Conclusion + next steps (out of slice-1 scope)

The harness is correct and faithful; it shows the live ag/au options emission is
**still not market-validated** at the emitted strikes, and quantifies why
(coverage + IV sensitivity). To get a market-backed verdict, a follow-on must
either:
1. **Fetch real option data for the emitted strikes** (TqSdk intraday/daily;
   `project_cn_options_intraday_tqsdk`) to drive `modeled_fraction` down, or
2. **Attribute on a liquid ATM proxy** (nearest liquid strike with data) rather
   than the exact emitted strike — accepting a small strike mismatch for market
   pricing.

Drift-gate / `validate_baselines --full` integration for these baselines also
remains deferred (slice-1 scope was baseline+harness+repro doc).

## Repro

```
cd src && .venv/bin/python scripts/backtest_options_attribution.py --underlying ag
cd src && .venv/bin/python scripts/backtest_options_attribution.py --underlying au
# write baselines:
cd src && .venv/bin/python scripts/backtest_options_attribution.py --underlying ag --out-json ../baselines/options_ag.json
```

Faithfulness guards: `src/tests/test_options_emission_faithfulness.py`. Exit-sim
(incl. TP1-at-boundary partial credit): `src/tests/test_option_exit.py`.
Price-loader (market/model/dispatch): `src/tests/test_option_price_loader.py`.
