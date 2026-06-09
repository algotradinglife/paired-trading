# Codex 第三轮 review — Lane × Market session (P0→P3 + reject decisions)

来源：`codex exec --sandbox read-only` 对 commit range `0b70f915..abf4886f` (8 commits) + STATUS.md + baselines + new doc/repro/ 的独立审查。
日期：2026-06-09

---

## Findings

1. **VIX proxy claim is too strong.** [us_regime_gate.py:12](src/engine/regime/us_regime_gate.py) says SPY 20-day realized vol and VIX are "1:1 monotonic in practice." That is false as stated. VIX is forward implied vol; realized vol is backward looking. It can fail during high hedging demand with calm realized tape, post-shock IV crush while realized remains high, event-risk premia, and vol-control/dealer positioning regimes. The gate may still be useful, but the threshold is not VIX-equivalent and was not WF-calibrated.

2. **The regime gate fails open silently.** [score_today.py:397](src/scripts/score_today.py) returns `None` on missing/short SPY data, and [score_today.py:413](src/scripts/score_today.py) converts that to "not suppressed." For a production risk gate, that should at least emit a warning/alert and include a scorecard field saying the gate was unavailable. Silent fail-open is governance debt.

3. **Governance is not actually the "single source of truth" yet.** The live suppression lists include context_a `{DIA,SPY,XLU}` and pa_us_60min `{DIA,XLK,QQQ,XLRE,SPY}` in code, but `baselines/context_a_us_equity.json` and `baselines/pa_us_60min_us_equity.json` still list only long-bond exclusions. That is exactly the documentation rot risk you flagged. When XLP/XLV/etc. are added, there is no enforced classifier/default suppression policy.

4. **`max_hold=30` is deployable, but I would not call it "verified" without qualification.** The OOS gain is real in the documented replay, but F2 is only `+0.87R / n=75`, and the improvement is concentrated in bpull/context_a. This should be treated as a provisional global default with lane-level monitoring, not as a solved parameter. A per-lane default would be cleaner than globally lengthening stale or weak lanes.

5. **STATUS has at least one arithmetic/wording problem.** The "+23.39R / +0.297R EV/trade" headline in [STATUS.md:8](STATUS.md) does not match the fold table. `133.81R / 389 OOS trades ≈ 0.344R`; improvement is `23.39R / 389 ≈ 0.060R/trade`. The `+217% US pool` claim is arithmetically right for `0.082 → 0.260`.

6. **Counterfactual filtering is sound only for pre-trade filters.** It is acceptable for symbol exclusions and date-known regime gates, assuming no capital-slot interactions. It is weaker for claims involving max_hold/TP/outcome mechanics because replayed CSV paths bake in data snapshot, fills, stop priority, universe membership, and no portfolio-capacity feedback. Reusing the same K=3 dates is not leakage by itself, but repeated candidate testing on the same folds creates coupled overfitting risk.

7. **Rejected decisions mostly look justified.** TP1=0.75 failing because only 4 max_hold trades reached 0.75R also makes TP1=0.85 unlikely to help. The CN regime-gate reject is especially well-supported. I would not resurrect those before fixing monitoring and enforcement.

8. **`dce_p` work was low production impact** because the lane is `STALE`/weight 0, but not useless. The issue is that [backtest_full_stack.py:69](src/scripts/backtest_full_stack.py) still includes `kq_m_dce_p` while live scoring excludes it, so future replays can drift from production.

Baseline validation confirms the governance gap: default is `9 OK / 1 STALE / 1 PENDING`; `--strict` exits `1`. Also, many `valid_until` dates cluster on 2026-09-08/09, so expiry handling needs a scheduled cadence, not ad hoc end-of-quarter cleanup.

---

## Action items 处理（本 commit）

### Fixed
- **#5** STATUS.md +0.297R → 正确的 +0.060R/trade improvement, +0.344R OOS EV
- **#3** 把 DIA/SPY/XLU/XLK/QQQ/XLRE 加入 context_a_us_equity.json + pa_us_60min_us_equity.json 的 symbols_excluded
- **#1** us_regime_gate.py docstring 软化 "1:1 monotonic" claim
- **#8** 从 `backtest_full_stack.py` POOLS 移除 kq_m_dce_p（保持 replay 与 production 一致）

### Deferred to followup
- **#2** Silent fail-open warning + scorecard field (governance debt)
- **#4** Per-lane max_hold default (provisional global → per-lane) — 需要 backtest 时间
- **#6** Coupled K=3 folds overfitting risk — 长期问题，记 memory
- valid_until cadence — 季度复核机制
