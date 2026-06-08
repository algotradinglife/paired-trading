# DIR Verdict Alignment Audit — 2026-06-08

Annotation-only DIR landed in commit 6cc0b1f4 (8-source synthesiser
`pa_direction_assessment.py`).  Before promoting DIR to an emission
gate, this audit asks: **does DIR actually align with PA's existing
emit decisions on US / CN_METAL / CN_BOND over the last 7 days?**
7-day samples were thin so I also extended to 30 days for context.

## Headline

| pool       | window | emit | with DIR | long_call (agree) | skip (DIR rejects) | long_put |
|------------|--------|------|----------|-------------------|--------------------|----------|
| US         | 7 d    | 4    | 3        | 0 / 3 = 0%        | 3 / 3 = 100%       | 0        |
| CN_METAL   | 7 d    | 1    | 1        | 0 / 1             | 1 / 1              | 0        |
| CN_BOND    | 7 d    | 0    | 0        | n/a               | n/a                | n/a      |
| US         | 30 d   | 10   | 5        | 0 / 5 = 0%        | 5 / 5 = 100%       | 0        |
| CN_METAL   | 30 d   | 7    | 3        | 0 / 3 = 0%        | 3 / 3 = 100%       | 0        |
| CN_BOND    | 30 d   | 0    | 0        | n/a               | n/a                | n/a      |

**0/8 PA emissions earn DIR=long_call; 100% are flagged DIR=skip.**
This is not a marginal disagreement.  Max bull count observed = 3/8
(threshold = 4/8).  Per-source totals across the eight emit-with-DIR
records (US 30d + CN_METAL 30d combined):

```
daily_structure   bull=0 bear=0 neutral=8  ← always silent
hourly_state      bull=4 bear=2 neutral=2
context           bull=1 bear=0 neutral=7
divergence        bull=1 bear=0 neutral=7
weekly_trend      bull=2 bear=0 neutral=6
minute15_state    bull=2 bear=5 neutral=1  ← leans against PA
force_balance     bull=1 bear=2 neutral=5
exhaustion        bull=2 bear=0 neutral=6
```

## Root cause — two sources structurally miscalibrated

1. **`daily_structure` is always neutral** (8/8).  PA `pa_h2`
   on CN_METAL explicitly excludes BULL phase; `pa_us_dif_pos` lands
   in TR_FORMING because the `at_tr_bottom` gate was dropped 2026-06-08;
   `pa_us_60min` reads daily phase that is structurally TR-flavoured at
   the H2 bar.  DIR's mapping `TR / TR_FORMING / UNCLEAR → neutral`
   means daily_structure cannot ever confirm the setups PA is
   validated to emit.

2. **`minute15_state` votes against PA**: 5 bear vs 2 bull.  The
   polarity rule "h2_bottom wants 15m DIF<0" is the right principle,
   but at the daily H2 bar the 15m has already been turning up for
   hours — its DIF crosses positive often, getting tagged bear.

`context` and `divergence` lean correct but rarely fire (bull-only
patterns with strict geometry).  `weekly_trend` and `exhaustion`
are net positive but quiet.

## 4 worked examples — macro framing (W → D → 1h → 15m → 上下文 → 信号位置)

### Example 1 — `GDX` 2026-05-22, pa_us_60min, w=0.80 → DIR=skip conf=0.375
W: BULL/+ → **bull**.  D: TR_FORMING [68.20, 117.17] → neutral.  1h:
DIF=-0.84 vs margin 0.22 → **bull** (h=opp).  15m: DIF=+0.19 → bear.
Context A/B1: None → neutral.  Force: ratio 0.85 → neutral.  Exhaustion:
bear_exhausting → **bull**.  Divergence: none.  **3 bull, 1 bear, 4
neutral.** 周线确认大趋势上行, 1h h=opp 回踩, 空方耗竭 — 顺势回踩,
weight 0.80 名副其实.  **DIR-skip 是误杀**, 仅因 daily_structure 卡在
neutral + 15m polarity 翻负.

### Example 2 — `XLRE` 2026-06-02, pa_us_dif_pos, w=0.30 → DIR=skip conf=0.375
W: TR_FORMING/+ → neutral.  D: TR_FORMING [39.46, 44.91] → neutral.
1h: DIF=-0.29 vs 0.04 → **bull**.  15m: DIF=-0.12 vs 0.09 → **bull**.
Context: A (DIF>0 pullback) → **bull**.  Force/Exhaust/Div: neutral×3.
**3 bull, 0 bear, 5 neutral.** 区间内做底部反弹, 1h / 15m / Context
全部一致看多.  PA 0.30 因 TR_FORMING 半仓.  **DIR 又因 daily_structure
缺席而误杀完全一致的多方组件**.

### Example 3 — `kq_m_shfe_au` 2026-05-13, pa_h2, w=0.75 → DIR=skip conf=0.25 (informative!)
W: BULL/+ → bull.  D: TR_FORMING → neutral.  1h: DIF=+4.12 vs 0.65 →
**bear** (1h 已强势走多, h=opp 没了).  15m: 近 0 → neutral.  Context:
**B1** (新 cycle 首次回踩) → bull.  Force: bull 0.32 vs bear 0.56 →
bear.  Exhaustion: bull_exhausting → neutral.  **2 bull, 2 bear, 4
neutral.** 这是真正带矛盾的一条 — W+B1 长周期顺势, 但 1h 已透支,
短期力量在空方.  **DIR 真有信息**, 只是 verdict 选了 skip 而不是
long_put.  Read: 保留 PA emit + 加 DIR 提示"短周期已无 h=opp".

### Example 4 — `kq_m_shfe_ag` 2026-06-02, pa_h2, w=0.45 → DIR=skip conf=0.25 (correct veto)
W / D: TR_FORMING → neutral × 2.  1h: bear (h=aligned, 同向下跌).  15m:
bear.  Context: None.  Force / Exhaust / Div: neutral × 3.  **0 bull,
2 bear, 6 neutral** — 唯一一条 bear > bull.  PA 仍 emit 因 h=neutral
非 opp 降权到 0.45.  这种弱信号应该不进单, DIR 替我们守门.  **将来
gate 应该是不对称: bear_votes ≥ bull_votes + 1 时降权 / 否决, 而不是
当前对称的 4-of-8 阈值.**

## Verdict: gate-now vs gate-later vs gate-never

**Gate-never (today).**  Promoting DIR to gate at current 4-of-8 /
equal-weight settings zero-outs 100% of PA production emit traffic in
all three pools — the live system becomes silent.  PA detectors are
individually walk-forward validated (see `pa_baseline_2026-06-08.md`
and `pa_policy_validation_2026-06-08.md`); DIR has not been validated,
and the audit shows it disagrees with PA on every emit.

**Gate-later** is plausible after two specific fixes (below).

**Gate-now-as-asymmetric-veto-only** is the worth-considering interim:
keep PA emit unchanged, but when `bear_votes > bull_votes` (Example 4
shape), down-weight or annotate the record as "DIR objection".  This
captures the only sample where DIR added information without killing
the 5+ samples where DIR was simply absent.

## Follow-ups

1. **`daily_structure` mapping needs PA-aware logic.**  TR / TR_FORMING
   is not neutral when PA explicitly targets that phase — it's
   confirmation at minimum.  Proposed remap when `ambush_pattern=h2_bottom`:
   `BULL → bull`, `TR / TR_FORMING → bull (weak / half weight)`,
   `BEAR → bear`, `UNCLEAR → neutral`.  Re-run this audit to verify
   the remap lifts agreement to a non-trivial range before any gate.

2. **`minute15_state` polarity rule needs a wider indifferent zone.**
   When a daily / 60min H2 fires, the 15m DIF is by construction
   already turning — voting bear on every freshly-printed bottom is a
   false negative.  Either widen the neutrality band (e.g. require
   `|DIF| > 1.0 × ATR`, not the current `0.2 × ATR`), or skip 15m
   voting entirely when the daily/60min bar is the signal bar.

3. **Re-baseline DIR threshold from 4-of-8 to bear-only asymmetric.**
   The current symmetric 4-of-8 majority is a strict gate.  Replace
   with: PA emit stands; DIR adds a weight downgrade only when
   `bear_votes ≥ 3 AND bull_votes ≤ 1`.  That's "DIR may veto, not
   promote" — preserves the PA validated emit path while letting DIR
   earn its keep on the one record per pool where it was genuinely
   informative.
