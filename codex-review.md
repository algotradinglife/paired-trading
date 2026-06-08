# Codex 第二意见 — pa_h2_climax 异常报告

来源：`codex exec --sandbox read-only` 对 `doc/repro/pa_h2_climax_anomaly_2026-06-08.md` 的独立审查。
日期：2026-06-08

---

**Verdict: mostly sound, but overstated in two places.**

The "docstring unreproducible" conclusion is credible. In the reviewed paths, `pa_h2_climax` uses `min_h_legs=2`, `min_quality=0.3`, `ema_threshold=0.0`, `min_gap=10`, `require_climax=True`, `climax_threshold=0.4`, plus `h_rel == opposing`. I do not see `q_quantile` or `dif_window` in this lane, so those are unlikely missing knobs.

Main caveat: the standalone harness is not perfectly identical to live detection. It scans with `min_gap=1` then post-filters/re-applies `min_gap=10`, and its climax post-filter uses `recent_climax_max_5` excluding the signal bar, while `PABottomDetector(require_climax=True)` checks `i - lookback` through `i`, inclusive. That could change sample membership. Still, full-stack uses the live detector shape and is negative, so this caveat weakens "same params" wording but does not rescue the docstring.

The 2025-regime claim is too strong. `EV=-0.904R / n=9` is a serious drawdown cluster, not proof of a new regime. With nine trades, confidence intervals are huge, and 2026 YTD being positive on `n=6` argues against declaring a persistent post-2025 break. Better wording: "2025 dominates the historical loss and warrants quarantine/monitoring," not "2025 regime is real."

The stop-framework section also underplays second-order effects. A 10bp average EV gap is not the whole story because structural stops change R denominator, trade duration, max-hold frequency, overlap/capital tie-up, and MAE/MFE shape. The `max_hold` count under structural stops is especially relevant. The right next test is paired signal-level ATR vs structural replay with same entries, reporting MAE, MFE, bars-held, and outcome transition matrix.

Recommendation: dropping from `0.65` is clearly justified. For production trading, `0.0` is defensible until a reproducible walk-forward exists, especially with costs/slippage omitted. If the team wants continuing evidence collection, make `0.15` annotation/watch-only, not a live sizing weight.

Missed risks: same-bar close entry assumes completed-bar availability; overlapping same-symbol signals may violate independence; unspecified cutoff/data snapshot makes the original K=3 result non-auditable. Overall: the report's core conclusion is right, but its regime diagnosis and stop interpretation should be more cautious.

---

## Action items（基于 codex review）

按重要性降序：

1. **缓和 2025 regime 叙事**：把报告 §"2025 是 PnL 杀手" 改成 "2025 集中亏损，n=9 不足以下 regime 结论；quarantine + monitor 即可"
2. **修正"same params"措辞**：脚注说明 `backtest_pa_standalone` 与 live `PABottomDetector(require_climax=True)` 在 min_gap / climax lookback 边界上不完全一致（standalone 后过滤 vs detector 内嵌、climax 窗口含信号 bar 与否）；这点影响 sample 集合但不改变 "docstring 不可复现" 的结论
3. **policy_weight 推荐**：`0.0` (live trading) 或 `0.15` (watch/annotation only)——codex 同意大方向
4. **Stop framework 需要 paired comparison**：在相同 entries 上同时跑 ATR×1.5 / structural 两种 stop，输出 MAE/MFE/bars_held/outcome transition matrix，而不是只看 EV
5. **未覆盖的风险**（codex 提醒）：
   - same-bar close entry 假设了 bar 已闭合，需要确认 production 实际是 next-bar-open
   - overlapping same-symbol 信号违反 sample 独立性，会让 t 检验偏乐观
   - 原 K=3 baseline 没有数据 snapshot，不可审计
