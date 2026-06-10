---
name: project_h_opposing_temporal_stability
description: h=opposing filter temporal stability — 2024 failure is CN commodity regime (not Fed rate cut); US pools maintained positive lift throughout
metadata: 
  node_type: memory
  type: project
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

Annual h=opposing filter lift (EV_opp − EV_non, bottom signals, 5 Scheme B pools):

| Year | Lift | Note |
|------|------|------|
| 2021 | +0.471R | ✓ |
| 2022 | +0.818R | ✓ Bear market — strongest year |
| 2023 | +0.753R | ✓ |
| 2024 | −0.107R | ✗ Filter fails — see below |
| 2025 | +0.791R | ✓ Full recovery |
| 2026 | −0.123R | ✗ Small n (27 bottom total) — unreliable |

**2024 failure root cause: China commodity regime, NOT Fed rate cut**

Per-pool breakdown in 2024:
- CN_METAL: lift = −0.981R (h=opp EV −0.481R vs non-opp +0.500R) — worst pool
- CN_AGRI: lift = −1.250R (h=opp +0.250R vs non-opp +1.500R) — CN non-opp outperformed
- CN_INDEX: lift = −0.150R (minor)
- US_EQUITY: lift = +0.167R — filter still positive
- US_MACRO: lift = +0.875R — filter strong

Quarterly resolution shows failure started 2024Q2 (April-June), months BEFORE the Fed rate cut on 2024-09-18. The CN commodity sector (CN_METAL, CN_AGRI) in 2024 was under structural stress: property market collapse → suppressed construction/industrial demand (rebar, Cu), weak domestic demand, currency pressure. This disrupted the normal exhaustion reversal pattern against 1h trend.

**US_EQUITY post-rate-cut weakness (separate issue):**
- Pre-cut: bottom+opp EV = +1.105R (n=19)
- Post-cut: bottom+opp EV = +0.375R (n=8)
- But: h=opposing signals become very sparse post-cut (0-1/quarter in US_EQUITY after Sep 2024)
- Bull market = fewer counter-trend exhaustion setups trigger
- When signals do fire, outcomes are mixed (small n makes conclusion unreliable)
- Filter lift is STILL positive for US_EQUITY in 2025Q2-Q3 when signals occurred

**How to apply:**
- 2024 CN commodity weakness is a regime risk, not a filter failure — the filter is fine; the signals themselves were lower quality in that CN macro context
- Do NOT add a "2024 exception" rule — regime classifiers at that precision would overfit
- US_EQUITY post-cut weakness is partly a signal frequency drop, not pure EV degradation
- Monitor rolling 20-signal EV per pool; alert if any pool falls below 0 for 2 consecutive windows

**Related:** [[project_crosspool_portfolio_oos]], [[project_h_opposing_validated_universal]]
