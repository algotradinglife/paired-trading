---
name: project-cn-bond-pool
description: "CN bond futures pool (TF/T/TS) — data, backtest, and OOS validation results"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

CFFEX treasury bond futures added as CN_BOND pool (2026-05-31).

**Symbols**: kq_m_cffex_tf (5Y), kq_m_cffex_t (10Y), kq_m_cffex_ts (2Y)
**THS codes**: TF00.CFE, T00.CFE, TS00.CFE
**Data**: daily (TF from 2013-09, T from 2018-01, TS from 2019-01) + 60min/15min 2021-05→2026-05
**Fetcher**: fetch_qveris.py (daily monthly-chunked via cn_financial_pro.history_quotation.v1; intraday single wide call via ths_ifind.hf_basic_quotation.v1)

**Backtest (stop=ATR×1.5, 2026-06-01)**:
- Total: n=150, EV=+0.379R (3 symbols: TF/T/TS)
- Bottom: n=81, EV=+0.612R, hit=65%
- Bottom×h=opposing: n=22, EV=+0.958R, hit=86%
- Top: n=69, EV=-0.063R — tops near zero; hidden top subtype is -0.889R (n=9, watch)

**Best sub-signals:**
- intra_cycle (heap) bottom: EV=+1.14R (supporting) / +1.07R (opposing)
- intra_cycle_hist (HICD) × h=opposing: +0.873R (n=13)
- Edge comes from intra_cycle/HICD, NOT inter_segment

**Walk-forward K=3 OOS — bottom×h=opposing: STRONG PASS**
- fold1 (cutoff 2022-06-27): EV=+0.978R, hit=100%, n=7
- fold2 (cutoff 2023-01-30): EV=+0.786R, hit=71%, n=7
- Temporal stability: 100% hit 2021–2024; slight softening in 2025 (60%, n=5)

**Status (2026-06-01): DEFAULT pool — promoted from opt-in.**
- scan_portfolio_b.py: in SCHEME_B_POOLS ✓ (ev_fold1=0.978, ev_fold2=0.786 updated)
- score_today.py: CN_BOND pool added ✓
- backtest_rr_pool.py: POOL_INSTRUMENT_CLASS["CN_BOND"] = "cn_futures" ✓

**Why**: Genuinely uncorrelated to equity/commodity pools. Rate-driven regime. Temporal stability 2021–2024 is exceptional. Top signals weak but not materially dragging the portfolio. Hidden top gate (n=9) too small to implement yet — observe until n≥20.

**How to apply**: Use `--pool CN_BOND` in any script. instrument_class=cn_futures (no pool-specific gate yet). Monitor hidden top subtype for future gate.
