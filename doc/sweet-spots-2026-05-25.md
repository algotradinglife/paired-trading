# Sweet-Spot Discovery — 2026-05-25 (with Z3 volume + OOS validation)

Updated to add OOS train/test split. Train-only bucket edges + horizon-overlap purge applied (codex 2026-05-25 review).

## In-window analysis (full pool)

### Pool US (10 ETFs)
```
Pool: 10 symbol(s) — ['SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'GDX', 'XLF', 'XLK', 'TLT', 'NVDA']
Instrument class: us_equity  Horizon: 20d
  SPY:   43 signals
  QQQ:   25 signals
  IWM:   25 signals
  DIA:   24 signals
  GLD:   20 signals
  GDX:   24 signals
  XLF:   30 signals
  XLK:   31 signals
  TLT:   20 signals
  NVDA:   24 signals

Total pooled signals: 266 from 10 symbols
Baseline (all pooled signals): hit_rate=63.9%  mean=+2.04%

=== Direction × wick tercile ===
direction wick_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
   bottom    wick_low 61.0       10.0        72.1%        +8.2pp       +2.63%         +2.80%    +1.42%    +3.82%
   bottom   wick_high 60.0       10.0        71.7%        +7.8pp       +4.27%         +2.45%    +2.22%    +6.65%
   bottom    wick_mid 58.0       10.0        63.8%        -0.1pp       +2.61%         +2.72%    +1.03%    +4.17%
      top    wick_mid 30.0       10.0        63.3%        -0.6pp       +0.59%         +1.73%    -1.35%    +2.32%
      top    wick_low 28.0        9.0        50.0%       -13.9pp       -1.54%         -0.00%    -5.10%    +1.38%
      top   wick_high 29.0        7.0        44.8%       -19.1pp       +0.07%         -0.88%    -1.86%    +1.99%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    top / wick_low                                           n= 28  hit=50.0% (-13.9pp)  mean=-1.54%  CI [-5.10, +1.38]%
    top / wick_high                                          n= 29  hit=44.8% (-19.1pp)  mean=+0.07%  CI [-1.86, +1.99]%

=== Direction × prior_swing tercile ===
direction swing_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
   bottom    swing_mid 57.0       10.0        77.2%       +13.3pp       +3.67%         +2.88%    +2.50%    +4.91%
   bottom    swing_low 82.0        9.0        67.1%        +3.2pp       +2.79%         +2.32%    +1.12%    +4.55%
   bottom   swing_high 40.0        9.0        62.5%        -1.4pp       +3.25%         +2.62%    +1.25%    +5.50%
      top    swing_mid 31.0       10.0        61.3%        -2.6pp       +1.41%         +1.68%    -0.29%    +3.14%
      top   swing_high 49.0        9.0        51.0%       -12.9pp       -0.29%         +0.09%    -2.39%    +1.41%
      top    swing_low  7.0        4.0        28.6%       -35.3pp       -7.58%         -6.93%   -13.01%    -2.23%

  >>> SWEET SPOTS (n≥15, hit_uplift ≥ +10.0pp):
    bottom / swing_mid                                       n= 57  hit=77.2% (+13.3pp)  mean=+3.67%  CI [+2.50, +4.91]%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    top / swing_high                                         n= 49  hit=51.0% (-12.9pp)  mean=-0.29%  CI [-2.39, +1.41]%

=== Direction × candidate_volume_ratio tercile ===
direction vol_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
      top         na  1.0        1.0       100.0%       +36.1pp       +4.83%         +4.83%    +4.83%    +4.83%
   bottom   vol_high 71.0       10.0        71.8%        +7.9pp       +2.96%         +2.66%    +1.96%    +4.00%
   bottom    vol_low 51.0       10.0        70.6%        +6.7pp       +3.47%         +1.94%    +1.13%    +6.11%
   bottom    vol_mid 57.0       10.0        64.9%        +1.0pp       +3.16%         +2.95%    +1.33%    +5.09%
      top    vol_mid 31.0        9.0        58.1%        -5.8pp       -0.69%         +0.47%    -2.73%    +1.15%
      top   vol_high 18.0        7.0        55.6%        -8.4pp       +1.58%         +1.26%    -0.60%    +3.84%
      top    vol_low 37.0       10.0        45.9%       -18.0pp       -0.95%         -0.69%    -3.80%    +1.32%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    top / vol_low                                            n= 37  hit=45.9% (-18.0pp)  mean=-0.95%  CI [-3.80, +1.32]%

=== Direction × wick × swing ===
direction wick_bucket swing_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
      top    wick_low    swing_mid  7.0        5.0        85.7%       +21.8pp       +4.38%         +2.51%    +0.30%    +8.57%
   bottom    wick_low    swing_mid 18.0        7.0        83.3%       +19.4pp       +4.12%         +3.36%    +2.40%    +6.08%
      top    wick_mid   swing_high 12.0        6.0        83.3%       +19.4pp       +2.41%         +2.89%    +0.58%    +4.16%
   bottom   wick_high    swing_mid 20.0        9.0        80.0%       +16.1pp       +3.92%         +2.49%    +1.71%    +6.46%
   bottom    wick_low   swing_high 17.0        8.0        70.6%        +6.7pp       +3.32%         +2.99%    +0.96%    +5.94%
   bottom    wick_mid    swing_mid 19.0        7.0        68.4%        +4.5pp       +2.97%         +2.88%    +0.95%    +4.94%
   bottom    wick_mid    swing_low 25.0        8.0        68.0%        +4.1pp       +2.60%         +2.85%    -0.19%    +5.44%
   bottom   wick_high    swing_low 31.0        9.0        67.7%        +3.8pp       +4.32%         +2.48%    +1.01%    +8.33%
   bottom   wick_high   swing_high  9.0        6.0        66.7%        +2.8pp       +4.86%         +2.06%    -0.21%   +11.93%
   bottom    wick_low    swing_low 26.0        9.0        65.4%        +1.5pp       +1.14%         +1.95%    -0.65%    +2.79%
      top   wick_high    swing_mid  8.0        6.0        62.5%        -1.4pp       +1.24%         +2.26%    -0.46%    +2.73%
      top    wick_mid    swing_low  2.0        1.0        50.0%       -13.9pp       -7.30%         -7.30%   -15.06%    +0.47%
      top    wick_mid    swing_mid 16.0        8.0        50.0%       -13.9pp       +0.21%         +0.16%    -2.21%    +2.55%
   bottom    wick_mid   swing_high 14.0        4.0        50.0%       -13.9pp       +2.12%         +0.93%    -1.18%    +5.40%
      top    wick_low   swing_high 17.0        6.0        41.2%       -22.7pp       -2.84%         -0.77%    -7.54%    +0.43%
      top   wick_high   swing_high 20.0        7.0        40.0%       -23.9pp       +0.25%         -1.85%    -1.98%    +2.62%
      top    wick_low    swing_low  4.0        3.0        25.0%       -38.9pp       -6.39%         -5.85%   -14.33%    +1.01%
      top   wick_high    swing_low  1.0        1.0         0.0%       -63.9pp      -12.88%        -12.88%   -12.88%   -12.88%

  >>> SWEET SPOTS (n≥15, hit_uplift ≥ +10.0pp):
    bottom / wick_low / swing_mid                            n= 18  hit=83.3% (+19.4pp)  mean=+4.12%  CI [+2.40, +6.08]%
    bottom / wick_high / swing_mid                           n= 20  hit=80.0% (+16.1pp)  mean=+3.92%  CI [+1.71, +6.46]%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    top / wick_mid / swing_mid                               n= 16  hit=50.0% (-13.9pp)  mean=+0.21%  CI [-2.21, +2.55]%
    top / wick_low / swing_high                              n= 17  hit=41.2% (-22.7pp)  mean=-2.84%  CI [-7.54, +0.43]%
    top / wick_high / swing_high                             n= 20  hit=40.0% (-23.9pp)  mean=+0.25%  CI [-1.98, +2.62]%

=== Direction × wick × volume ===
direction wick_bucket vol_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
      top    wick_low         na  1.0        1.0       100.0%       +36.1pp       +4.83%         +4.83%    +4.83%    +4.83%
   bottom   wick_high    vol_low 16.0        7.0        81.2%       +17.3pp      +10.04%         +7.42%    +4.81%   +16.20%
   bottom    wick_low   vol_high 27.0       10.0        77.8%       +13.9pp       +4.46%         +3.93%    +2.80%    +6.32%
   bottom    wick_low    vol_low 21.0       10.0        76.2%       +12.3pp       +1.35%         +1.51%    -0.29%    +2.81%
   bottom   wick_high   vol_high 21.0        9.0        71.4%        +7.5pp       +1.26%         +0.99%    -0.20%    +2.83%
   bottom    wick_mid    vol_mid 21.0        9.0        71.4%        +7.5pp       +4.77%         +5.62%    +1.94%    +7.63%
      top    wick_mid    vol_mid 13.0        9.0        69.2%        +5.3pp       +0.87%         +1.92%    -2.01%    +3.44%
      top    wick_mid   vol_high  3.0        3.0        66.7%        +2.8pp       +0.96%         +2.92%    -6.56%    +6.53%
   bottom    wick_mid   vol_high 23.0        9.0        65.2%        +1.3pp       +2.74%         +2.85%    +1.00%    +4.47%
   bottom   wick_high    vol_mid 23.0        8.0        65.2%        +1.3pp       +3.00%         +3.73%    -0.00%    +6.52%
      top    wick_low   vol_high  5.0        4.0        60.0%        -3.9pp       +1.73%         +0.83%    -2.52%    +7.18%
      top    wick_mid    vol_low 14.0        8.0        57.1%        -6.8pp       +0.25%         +1.36%    -2.59%    +2.53%
      top    wick_low    vol_mid  9.0        6.0        55.6%        -8.4pp       -1.66%         +0.66%    -6.48%    +2.04%
   bottom    wick_low    vol_mid 13.0        8.0        53.8%       -10.1pp       +0.86%         +1.95%    -2.00%    +3.71%
   bottom    wick_mid    vol_low 14.0        8.0        50.0%       -13.9pp       -0.86%         -0.15%    -4.36%    +2.56%
      top   wick_high   vol_high 10.0        5.0        50.0%       -13.9pp       +1.68%         +1.73%    -0.85%    +4.18%
      top   wick_high    vol_mid  9.0        5.0        44.4%       -19.5pp       -1.98%         -3.34%    -4.74%    +0.59%
      top   wick_high    vol_low 10.0        5.0        40.0%       -23.9pp       +0.30%         -0.82%    -3.62%    +4.28%
      top    wick_low    vol_low 13.0        6.0        38.5%       -25.4pp       -3.21%         -1.20%    -9.66%    +1.75%

  >>> SWEET SPOTS (n≥15, hit_uplift ≥ +10.0pp):
    bottom / wick_high / vol_low                             n= 16  hit=81.2% (+17.3pp)  mean=+10.04%  CI [+4.81, +16.20]%
    bottom / wick_low / vol_high                             n= 27  hit=77.8% (+13.9pp)  mean=+4.46%  CI [+2.80, +6.32]%
    bottom / wick_low / vol_low                              n= 21  hit=76.2% (+12.3pp)  mean=+1.35%  CI [-0.29, +2.81]%

=== SWEET-SPOT SEARCH: direction × wick × swing × volume ===
direction wick_bucket swing_bucket vol_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
      top    wick_mid   swing_high    vol_low  3.0        3.0       100.0%       +36.1pp       +4.85%         +4.12%    +2.70%    +7.72%
      top   wick_high    swing_mid    vol_mid  3.0        3.0       100.0%       +36.1pp       +2.77%         +2.74%    +2.67%    +2.89%
      top    wick_low    swing_mid         na  1.0        1.0       100.0%       +36.1pp       +4.83%         +4.83%    +4.83%    +4.83%
   bottom    wick_mid   swing_high    vol_mid  3.0        2.0       100.0%       +36.1pp       +7.74%         +8.58%    +2.59%   +12.04%
      top    wick_mid    swing_low    vol_mid  1.0        1.0       100.0%       +36.1pp       +0.47%         +0.47%    +0.47%    +0.47%
      top    wick_low    swing_mid   vol_high  2.0        2.0       100.0%       +36.1pp       +6.67%         +6.67%    +1.68%   +11.66%
   bottom   wick_high    swing_mid    vol_low  4.0        4.0       100.0%       +36.1pp       +9.33%         +7.42%    +3.90%   +16.68%
      top    wick_low    swing_mid    vol_mid  1.0        1.0       100.0%       +36.1pp       +1.42%         +1.42%    +1.42%    +1.42%
   bottom    wick_low   swing_high    vol_low  2.0        2.0       100.0%       +36.1pp       +2.28%         +2.28%    +1.51%    +3.05%
   bottom    wick_low    swing_mid    vol_low  7.0        5.0       100.0%       +36.1pp       +2.70%         +1.75%    +1.06%    +4.44%
      top    wick_mid   swing_high   vol_high  1.0        1.0       100.0%       +36.1pp       +2.92%         +2.92%    +2.92%    +2.92%
   bottom    wick_low    swing_low   vol_high  8.0        5.0        87.5%       +23.6pp       +3.79%         +3.76%    +2.09%    +5.51%
   bottom   wick_high    swing_mid    vol_mid  6.0        5.0        83.3%       +19.4pp       +5.08%         +5.21%    +1.98%    +8.32%
   bottom    wick_mid    swing_mid    vol_low  5.0        4.0        80.0%       +16.1pp       +5.69%         +6.84%    +2.51%    +8.33%
   bottom   wick_high    swing_low    vol_low 10.0        4.0        80.0%       +16.1pp      +12.42%        +12.08%    +4.64%   +21.55%
   bottom    wick_low    swing_mid   vol_high  8.0        5.0        75.0%       +11.1pp       +4.74%         +3.89%    +1.94%    +8.06%
      top    wick_mid   swing_high    vol_mid  8.0        6.0        75.0%       +11.1pp       +1.43%         +2.40%    -0.90%    +3.47%
   bottom   wick_high    swing_low   vol_high  8.0        5.0        75.0%       +11.1pp       +1.00%         +0.81%    -1.46%    +3.59%
   bottom   wick_high   swing_high    vol_mid  4.0        4.0        75.0%       +11.1pp       +9.18%         +5.51%    -1.22%   +23.26%
   bottom    wick_low   swing_high   vol_high 11.0        7.0        72.7%        +8.8pp       +4.76%         +3.93%    +1.49%    +8.48%
   bottom    wick_mid    swing_low    vol_mid 14.0        7.0        71.4%        +7.5pp       +5.15%         +5.84%    +1.56%    +8.63%
   bottom    wick_mid    swing_mid   vol_high 10.0        5.0        70.0%        +6.1pp       +2.32%         +0.79%    -0.05%    +4.85%
   bottom   wick_high    swing_mid   vol_high 10.0        7.0        70.0%        +6.1pp       +1.05%         +1.13%    -0.96%    +3.23%
      top    wick_low    swing_mid    vol_low  3.0        2.0        66.7%        +2.8pp       +3.68%         +2.51%    -4.27%   +12.80%
   bottom   wick_high   swing_high   vol_high  3.0        2.0        66.7%        +2.8pp       +2.62%         +2.06%    -1.39%    +7.19%
   bottom    wick_mid    swing_low   vol_high  6.0        4.0        66.7%        +2.8pp       +2.03%         +3.78%    -1.07%    +5.13%
   bottom    wick_low    swing_mid    vol_mid  3.0        3.0        66.7%        +2.8pp       +5.75%         +7.22%    -0.14%   +10.18%
   bottom    wick_mid    swing_low    vol_low  5.0        4.0        60.0%        -3.9pp       -3.87%         +0.07%    -9.88%    +1.21%
      top    wick_low   swing_high    vol_mid  5.0        4.0        60.0%        -3.9pp       +0.89%         +0.66%    -1.68%    +3.54%
   bottom    wick_low    swing_low    vol_low 12.0        7.0        58.3%        -5.6pp       +0.41%         +0.33%    -2.12%    +2.62%
      top   wick_high   swing_high   vol_high  7.0        4.0        57.1%        -6.8pp       +2.34%         +4.78%    -0.81%    +5.35%
   bottom    wick_mid   swing_high   vol_high  7.0        3.0        57.1%        -6.8pp       +3.94%         +6.48%    +0.34%    +7.46%
   bottom   wick_high    swing_low    vol_mid 13.0        7.0        53.8%       -10.1pp       +0.13%         +1.14%    -2.86%    +3.12%
   bottom   wick_high   swing_high    vol_low  2.0        2.0        50.0%       -13.9pp       -0.45%         -0.45%    -2.47%    +1.57%
      top    wick_mid    swing_mid    vol_low 10.0        6.0        50.0%       -13.9pp       +0.40%         +0.16%    -0.98%    +1.82%
      top    wick_mid    swing_mid   vol_high  2.0        2.0        50.0%       -13.9pp       -0.02%         -0.02%    -6.56%    +6.53%
   bottom    wick_low   swing_high    vol_mid  4.0        4.0        50.0%       -13.9pp       -0.12%         +0.40%    -3.07%    +2.82%
   bottom    wick_low    swing_low    vol_mid  6.0        5.0        50.0%       -13.9pp       -0.92%         -0.90%    -5.10%    +3.52%
      top    wick_mid    swing_mid    vol_mid  4.0        3.0        50.0%       -13.9pp       -0.16%         +1.14%    -8.16%    +6.54%
   bottom    wick_mid    swing_mid    vol_mid  4.0        4.0        50.0%       -13.9pp       +1.21%         +0.54%    -3.50%    +6.26%
      top    wick_low   swing_high   vol_high  2.0        2.0        50.0%       -13.9pp       +0.03%         +0.03%    -0.77%    +0.83%
      top   wick_high    swing_mid    vol_low  2.0        2.0        50.0%       -13.9pp       +0.58%         +0.58%    -0.69%    +1.84%
      top   wick_high   swing_high    vol_low  7.0        4.0        42.9%       -21.1pp       +2.11%         -0.96%    -1.47%    +6.22%
      top   wick_high    swing_mid   vol_high  3.0        3.0        33.3%       -30.6pp       +0.15%         -0.88%    -2.99%    +4.34%
      top    wick_low    swing_low    vol_mid  3.0        2.0        33.3%       -30.6pp       -6.93%         -6.93%   -17.53%    +3.66%
      top    wick_low   swing_high    vol_low 10.0        4.0        30.0%       -33.9pp       -5.28%         -2.39%   -12.70%    -0.27%
      top   wick_high   swing_high    vol_mid  6.0        3.0        16.7%       -47.2pp       -4.36%         -4.20%    -6.47%    -2.15%
   bottom    wick_mid   swing_high    vol_low  4.0        2.0         0.0%       -63.9pp       -5.27%         -4.66%    -7.63%    -3.20%
      top    wick_low    swing_low   vol_high  1.0        1.0         0.0%       -63.9pp       -4.76%         -4.76%    -4.76%    -4.76%
      top    wick_mid    swing_low    vol_low  1.0        1.0         0.0%       -63.9pp      -15.06%        -15.06%   -15.06%   -15.06%
      top   wick_high    swing_low    vol_low  1.0        1.0         0.0%       -63.9pp      -12.88%        -12.88%   -12.88%   -12.88%
```

### Pool CN index (4 symbols)
```
Pool: 4 symbol(s) — ['kq_m_cffex_if', 'kq_m_cffex_ih', 'kq_m_cffex_ic', 'kq_m_cffex_im']
Instrument class: cn_futures  Horizon: 20d
  kq_m_cffex_if:   72 signals
  kq_m_cffex_ih:   67 signals
  kq_m_cffex_ic:   77 signals
  kq_m_cffex_im:   21 signals

Total pooled signals: 237 from 4 symbols
Baseline (all pooled signals): hit_rate=60.3%  mean=+0.90%

=== Direction × wick tercile ===
direction wick_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
   bottom    wick_low 41.0        4.0        68.3%        +8.0pp       +1.82%         +1.51%    -0.02%    +3.82%
   bottom   wick_high 37.0        4.0        67.6%        +7.2pp       +2.41%         +1.81%    -0.16%    +5.37%
   bottom    wick_mid 41.0        4.0        65.9%        +5.5pp       +1.79%         +1.19%    +0.47%    +3.13%
      top    wick_low 38.0        4.0        65.8%        +5.5pp       +1.51%         +1.54%    +0.13%    +2.99%
      top    wick_mid 38.0        3.0        50.0%       -10.3pp       -0.96%         -0.50%    -2.73%    +0.74%
      top   wick_high 42.0        4.0        45.2%       -15.1pp       -1.04%         -0.50%    -3.24%    +0.82%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    top / wick_mid                                           n= 38  hit=50.0% (-10.3pp)  mean=-0.96%  CI [-2.73, +0.74]%
    top / wick_high                                          n= 42  hit=45.2% (-15.1pp)  mean=-1.04%  CI [-3.24, +0.82]%

=== Direction × prior_swing tercile ===
direction swing_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
   bottom    swing_mid 30.0        4.0        70.0%        +9.7pp       +1.68%         +1.97%    +0.07%    +3.35%
   bottom   swing_high 41.0        4.0        68.3%        +8.0pp       +3.74%         +2.02%    +1.34%    +6.43%
      top    swing_low 31.0        4.0        67.7%        +7.4pp       +1.57%         +2.27%    +0.08%    +3.02%
   bottom    swing_low 48.0        4.0        64.6%        +4.2pp       +0.69%         +0.75%    -0.83%    +2.17%
      top   swing_high 38.0        4.0        50.0%       -10.3pp       -0.16%         +0.01%    -1.59%    +1.24%
      top    swing_mid 49.0        4.0        46.9%       -13.4pp       -1.34%         -1.11%    -3.50%    +0.54%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    top / swing_high                                         n= 38  hit=50.0% (-10.3pp)  mean=-0.16%  CI [-1.59, +1.24]%
    top / swing_mid                                          n= 49  hit=46.9% (-13.4pp)  mean=-1.34%  CI [-3.50, +0.54]%

=== Direction × candidate_volume_ratio tercile ===
direction vol_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
   bottom    vol_mid 42.0        4.0        69.0%        +8.7pp       +3.62%         +2.82%    +1.32%    +6.12%
   bottom   vol_high 45.0        4.0        66.7%        +6.3pp       +1.45%         +0.99%    -0.26%    +3.20%
   bottom    vol_low 32.0        4.0        65.6%        +5.3pp       +0.62%         +0.75%    -0.88%    +2.12%
      top    vol_low 47.0        4.0        63.8%        +3.5pp       +1.39%         +1.52%    -0.08%    +2.84%
      top    vol_mid 37.0        4.0        48.6%       -11.7pp       -0.57%         -0.08%    -2.12%    +0.97%
      top   vol_high 34.0        4.0        44.1%       -16.2pp       -1.98%         -1.28%    -4.62%    +0.30%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    top / vol_mid                                            n= 37  hit=48.6% (-11.7pp)  mean=-0.57%  CI [-2.12, +0.97]%
    top / vol_high                                           n= 34  hit=44.1% (-16.2pp)  mean=-1.98%  CI [-4.62, +0.30]%

=== Direction × wick × swing ===
direction wick_bucket swing_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
   bottom   wick_high    swing_mid  8.0        4.0        87.5%       +27.2pp       +3.28%         +2.77%    +0.90%    +5.69%
   bottom    wick_mid   swing_high 13.0        4.0        76.9%       +16.6pp       +4.28%         +2.91%    +1.79%    +6.92%
   bottom    wick_low    swing_low 15.0        4.0        73.3%       +13.0pp       +1.65%         +1.29%    -1.78%    +5.09%
      top    wick_low    swing_low 11.0        4.0        72.7%       +12.4pp       +3.23%         +4.54%    +0.86%    +5.42%
   bottom    wick_low    swing_mid 14.0        3.0        71.4%       +11.1pp       +1.97%         +1.96%    -0.39%    +4.77%
      top    wick_mid    swing_low 10.0        3.0        70.0%        +9.7pp       -0.28%         +1.89%    -3.19%    +2.29%
   bottom   wick_high   swing_high 16.0        4.0        68.8%        +8.4pp       +4.72%         +1.92%    -0.10%   +10.18%
      top    wick_low    swing_mid 15.0        4.0        66.7%        +6.3pp       +0.84%         +1.05%    -1.61%    +3.38%
   bottom    wick_mid    swing_low 20.0        4.0        65.0%        +4.7pp       +1.05%         +0.67%    -0.27%    +2.43%
      top   wick_high    swing_low 10.0        3.0        60.0%        -0.3pp       +1.61%         +2.00%    -0.41%    +3.70%
   bottom    wick_low   swing_high 12.0        4.0        58.3%        -2.0pp       +1.84%         +2.27%    -1.86%    +5.85%
      top    wick_low   swing_high 12.0        4.0        58.3%        -2.0pp       +0.77%         +1.03%    -1.49%    +3.16%
   bottom   wick_high    swing_low 13.0        4.0        53.8%        -6.5pp       -0.97%         +0.19%    -4.16%    +2.27%
   bottom    wick_mid    swing_mid  8.0        4.0        50.0%       -10.3pp       -0.41%         -0.18%    -3.44%    +2.59%
      top   wick_high   swing_high 15.0        4.0        46.7%       -13.7pp       -0.48%         -0.08%    -3.13%    +1.92%
      top    wick_mid   swing_high 11.0        3.0        45.5%       -14.9pp       -0.75%         -1.46%    -3.10%    +1.54%
      top    wick_mid    swing_mid 17.0        3.0        41.2%       -19.2pp       -1.50%         -1.15%    -4.78%    +1.51%
      top   wick_high    swing_mid 17.0        4.0        35.3%       -25.0pp       -3.10%         -2.04%    -7.79%    +0.54%

  >>> SWEET SPOTS (n≥15, hit_uplift ≥ +10.0pp):
    bottom / wick_low / swing_low                            n= 15  hit=73.3% (+13.0pp)  mean=+1.65%  CI [-1.78, +5.09]%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    top / wick_high / swing_high                             n= 15  hit=46.7% (-13.7pp)  mean=-0.48%  CI [-3.13, +1.92]%
    top / wick_mid / swing_mid                               n= 17  hit=41.2% (-19.2pp)  mean=-1.50%  CI [-4.78, +1.51]%
    top / wick_high / swing_mid                              n= 17  hit=35.3% (-25.0pp)  mean=-3.10%  CI [-7.79, +0.54]%

=== Direction × wick × volume ===
direction wick_bucket vol_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
   bottom    wick_low    vol_mid 13.0        3.0        76.9%       +16.6pp       +2.49%         +2.41%    -0.04%    +5.52%
      top    wick_low    vol_low 20.0        4.0        75.0%       +14.7pp       +3.16%         +2.53%    +1.40%    +5.01%
   bottom   wick_high   vol_high 10.0        2.0        70.0%        +9.7pp       +0.60%         +1.11%    -2.68%    +3.30%
   bottom    wick_mid   vol_high 20.0        4.0        70.0%        +9.7pp       +1.67%         +1.06%    +0.02%    +3.28%
   bottom    wick_low    vol_low 13.0        4.0        69.2%        +8.9pp       +1.26%         +0.86%    -0.82%    +3.68%
   bottom   wick_high    vol_mid 16.0        4.0        68.8%        +8.4pp       +4.96%         +3.40%    +0.05%   +10.91%
   bottom   wick_high    vol_low 11.0        4.0        63.6%        +3.3pp       +0.35%         +0.65%    -2.75%    +3.47%
   bottom    wick_mid    vol_low  8.0        4.0        62.5%        +2.2pp       -0.06%         +0.83%    -2.12%    +1.87%
      top    wick_mid    vol_low 16.0        3.0        62.5%        +2.2pp       +0.36%         +0.57%    -2.05%    +2.85%
   bottom    wick_mid    vol_mid 13.0        4.0        61.5%        +1.2pp       +3.11%         +4.59%    +0.26%    +5.95%
   bottom    wick_low   vol_high 15.0        4.0        60.0%        -0.3pp       +1.72%         +0.18%    -2.35%    +6.00%
      top    wick_low    vol_mid 10.0        4.0        60.0%        -0.3pp       +0.38%         +0.53%    -2.42%    +2.98%
      top    wick_mid    vol_mid 13.0        3.0        53.8%        -6.5pp       -0.63%         +0.49%    -3.08%    +1.72%
      top   wick_high   vol_high 17.0        4.0        52.9%        -7.4pp       -1.38%         +0.74%    -5.96%    +2.01%
      top    wick_low   vol_high  8.0        4.0        50.0%       -10.3pp       -1.20%         -1.88%    -3.90%    +1.65%
      top   wick_high    vol_low 11.0        4.0        45.5%       -14.9pp       -0.34%         -0.75%    -3.49%    +2.43%
      top   wick_high    vol_mid 14.0        4.0        35.7%       -24.6pp       -1.18%         -1.92%    -4.29%    +1.35%
      top    wick_mid   vol_high  9.0        3.0        22.2%       -38.1pp       -3.79%         -2.88%    -8.69%    -0.08%

  >>> SWEET SPOTS (n≥15, hit_uplift ≥ +10.0pp):
    top / wick_low / vol_low                                 n= 20  hit=75.0% (+14.7pp)  mean=+3.16%  CI [+1.40, +5.01]%

=== SWEET-SPOT SEARCH: direction × wick × swing × volume ===
direction wick_bucket swing_bucket vol_bucket   n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
      top    wick_low    swing_low   vol_high 1.0        1.0       100.0%       +39.7pp       +4.80%         +4.80%    +4.80%    +4.80%
   bottom   wick_high    swing_mid    vol_mid 2.0        2.0       100.0%       +39.7pp       +6.09%         +6.09%    +2.33%    +9.84%
   bottom    wick_mid   swing_high    vol_low 1.0        1.0       100.0%       +39.7pp       +1.73%         +1.73%    +1.73%    +1.73%
   bottom   wick_high    swing_mid   vol_high 3.0        2.0       100.0%       +39.7pp       +2.64%         +1.61%    +0.60%    +5.70%
   bottom   wick_high   swing_high    vol_mid 8.0        4.0        87.5%       +27.2pp      +10.06%         +5.80%    +1.86%   +18.79%
      top    wick_low    swing_mid    vol_low 6.0        2.0        83.3%       +23.0pp       +3.40%         +1.54%    -0.36%    +8.12%
   bottom    wick_low    swing_mid    vol_mid 5.0        3.0        80.0%       +19.7pp       +2.63%         +3.08%    +0.82%    +3.98%
      top    wick_low    swing_low    vol_low 5.0        3.0        80.0%       +19.7pp       +4.42%         +4.54%    +1.19%    +7.16%
   bottom    wick_low    swing_mid   vol_high 5.0        3.0        80.0%       +19.7pp       +2.76%         +0.18%    -2.15%    +9.80%
      top    wick_mid    swing_low    vol_low 5.0        3.0        80.0%       +19.7pp       -0.03%         +1.52%    -4.86%    +3.22%
   bottom    wick_low    swing_low    vol_low 9.0        4.0        77.8%       +17.4pp       +1.75%         +0.86%    -0.61%    +4.69%
   bottom    wick_mid   swing_high   vol_high 9.0        3.0        77.8%       +17.4pp       +3.67%         +2.91%    +1.30%    +5.94%
   bottom    wick_mid    swing_low   vol_high 8.0        4.0        75.0%       +14.7pp       +1.04%         +0.67%    -0.42%    +2.59%
      top    wick_mid    swing_low    vol_mid 4.0        3.0        75.0%       +14.7pp       +0.59%         +2.71%    -3.94%    +3.20%
   bottom    wick_low    swing_low    vol_mid 4.0        2.0        75.0%       +14.7pp       +4.67%         +1.92%    -0.97%   +13.06%
   bottom   wick_high    swing_low   vol_high 4.0        2.0        75.0%       +14.7pp       -1.62%         +1.00%    -8.27%    +2.49%
   bottom    wick_low   swing_high    vol_mid 4.0        2.0        75.0%       +14.7pp       +0.12%         +2.27%    -4.75%    +2.97%
      top    wick_mid   swing_high    vol_mid 3.0        2.0        66.7%        +6.3pp       -0.37%         +0.49%    -4.33%    +2.71%
      top    wick_low   swing_high    vol_low 9.0        4.0        66.7%        +6.3pp       +2.29%         +2.18%    +0.31%    +4.61%
   bottom    wick_mid    swing_mid    vol_mid 3.0        2.0        66.7%        +6.3pp       +1.78%         +4.71%    -4.61%    +5.24%
      top   wick_high    swing_low    vol_mid 3.0        2.0        66.7%        +6.3pp       +0.72%         +1.89%    -3.75%    +4.01%
   bottom    wick_mid   swing_high    vol_mid 3.0        3.0        66.7%        +6.3pp       +6.97%         +9.68%    -2.87%   +14.09%
   bottom   wick_high    swing_mid    vol_low 3.0        1.0        66.7%        +6.3pp       +2.05%         +3.20%    -2.55%    +5.50%
      top    wick_mid    swing_mid    vol_low 6.0        3.0        66.7%        +6.3pp       +1.94%         +1.19%    -1.43%    +6.55%
   bottom   wick_high    swing_low    vol_low 3.0        3.0        66.7%        +6.3pp       +2.40%         +0.65%    -4.29%   +10.85%
      top   wick_high    swing_low   vol_high 5.0        2.0        60.0%        -0.3pp       +2.52%         +2.12%    -0.39%    +5.44%
      top    wick_low    swing_low    vol_mid 5.0        3.0        60.0%        -0.3pp       +1.72%         +0.91%    -1.91%    +5.21%
   bottom    wick_mid    swing_low    vol_low 5.0        3.0        60.0%        -0.3pp       -0.31%         +0.27%    -2.93%    +2.03%
      top    wick_low    swing_mid    vol_mid 5.0        3.0        60.0%        -0.3pp       -0.95%         +0.15%    -4.65%    +2.74%
   bottom   wick_high   swing_high    vol_low 5.0        3.0        60.0%        -0.3pp       -1.90%         +0.44%    -6.41%    +1.62%
   bottom    wick_mid    swing_low    vol_mid 7.0        3.0        57.1%        -3.2pp       +2.02%         +1.95%    -0.65%    +4.60%
      top   wick_high    swing_low    vol_low 2.0        2.0        50.0%       -10.3pp       +0.68%         +0.68%    -2.10%    +3.47%
      top   wick_high   swing_high    vol_low 4.0        3.0        50.0%       -10.3pp       -0.89%         +1.79%    -8.01%    +4.66%
      top   wick_high    swing_mid   vol_high 6.0        4.0        50.0%       -10.3pp       -4.59%         -0.06%   -16.06%    +2.74%
   bottom    wick_mid    swing_mid    vol_low 2.0        2.0        50.0%       -10.3pp       -0.33%         -0.33%    -3.70%    +3.04%
   bottom    wick_low    swing_mid    vol_low 4.0        2.0        50.0%       -10.3pp       +0.16%         -0.11%    -3.58%    +3.89%
   bottom    wick_low    swing_low   vol_high 2.0        2.0        50.0%       -10.3pp       -4.85%         -4.85%   -14.84%    +5.14%
      top    wick_low    swing_mid   vol_high 4.0        3.0        50.0%       -10.3pp       -0.77%         -1.43%    -4.12%    +2.58%
   bottom    wick_low   swing_high   vol_high 8.0        3.0        50.0%       -10.3pp       +2.70%         +1.34%    -2.23%    +8.09%
      top   wick_high   swing_high   vol_high 6.0        3.0        50.0%       -10.3pp       -1.43%         -0.73%    -5.42%    +2.17%
      top   wick_high   swing_high    vol_mid 5.0        2.0        40.0%       -20.3pp       +1.00%         -0.08%    -1.97%    +3.96%
      top   wick_high    swing_mid    vol_low 5.0        3.0        40.0%       -20.3pp       -0.31%         -2.27%    -3.16%    +3.39%
      top    wick_mid   swing_high    vol_low 5.0        2.0        40.0%       -20.3pp       -1.15%         -1.46%    -5.36%    +3.01%
   bottom   wick_high   swing_high   vol_high 3.0        2.0        33.3%       -27.0pp       +1.51%         -0.25%    -2.42%    +7.20%
      top    wick_mid   swing_high   vol_high 3.0        2.0        33.3%       -27.0pp       -0.46%         -2.33%    -2.88%    +3.83%
      top    wick_low   swing_high   vol_high 3.0        3.0        33.3%       -27.0pp       -3.77%         -5.58%    -5.87%    +0.14%
   bottom    wick_mid    swing_mid   vol_high 3.0        3.0        33.3%       -27.0pp       -2.66%         -1.55%    -7.62%    +1.19%
   bottom   wick_high    swing_low    vol_mid 6.0        3.0        33.3%       -27.0pp       -2.22%         -3.00%    -6.21%    +1.94%
      top    wick_mid    swing_mid    vol_mid 6.0        3.0        33.3%       -27.0pp       -1.58%         -2.03%    -5.51%    +2.57%
      top    wick_mid    swing_mid   vol_high 5.0        3.0        20.0%       -40.3pp       -5.54%         -3.32%   -13.64%    -0.02%
      top   wick_high    swing_mid    vol_mid 6.0        4.0        16.7%       -43.7pp       -3.95%         -2.34%    -9.72%    +0.45%
      top    wick_mid    swing_low   vol_high 1.0        1.0         0.0%       -60.3pp       -4.99%         -4.99%    -4.99%    -4.99%
```

### Pool CN commodity (15 symbols)
```
Pool: 15 symbol(s) — ['kq_m_shfe_rb', 'kq_m_shfe_cu', 'kq_m_shfe_au', 'kq_m_shfe_ag', 'kq_m_dce_m', 'kq_m_dce_i', 'kq_m_dce_j', 'kq_m_dce_jm', 'kq_m_dce_p', 'kq_m_dce_y', 'kq_m_czce_ta', 'kq_m_czce_ma', 'kq_m_czce_cf', 'kq_m_czce_sr', 'kq_m_ine_sc']
Instrument class: cn_futures  Horizon: 20d
  kq_m_shfe_rb:   75 signals
  kq_m_shfe_cu:   53 signals
  kq_m_shfe_au:   54 signals
  kq_m_shfe_ag:   71 signals
  kq_m_dce_m:   76 signals
  kq_m_dce_i:   74 signals
  kq_m_dce_j:   76 signals
  kq_m_dce_jm:   68 signals
  kq_m_dce_p:   69 signals
  kq_m_dce_y:   68 signals
  kq_m_czce_ta:   61 signals
  kq_m_czce_ma:   55 signals
  kq_m_czce_cf:   56 signals
  kq_m_czce_sr:   83 signals
  kq_m_ine_sc:   46 signals

Total pooled signals: 985 from 15 symbols
Baseline (all pooled signals): hit_rate=53.6%  mean=+0.95%

=== Direction × wick tercile ===
direction wick_bucket     n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
      top    wick_low 161.0       15.0        57.1%        +3.5pp       +0.84%         +1.00%    -0.30%    +2.02%
   bottom    wick_low 165.0       15.0        57.0%        +3.4pp       +2.45%         +0.56%    +1.07%    +3.86%
   bottom    wick_mid 160.0       15.0        54.4%        +0.8pp       +1.15%         +1.08%    +0.10%    +2.19%
      top    wick_mid 170.0       15.0        51.8%        -1.8pp       +0.18%         +0.40%    -1.03%    +1.39%
      top   wick_high 169.0       15.0        50.9%        -2.7pp       +0.77%         +0.17%    -0.48%    +2.00%
   bottom   wick_high 160.0       15.0        50.6%        -3.0pp       +0.36%         +0.22%    -0.83%    +1.56%

=== Direction × prior_swing tercile ===
direction swing_bucket     n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
      top   swing_high 141.0       15.0        58.2%        +4.6pp       +1.50%         +1.97%    -0.03%    +3.02%
   bottom   swing_high 188.0       15.0        56.4%        +2.8pp       +1.68%         +0.96%    +0.67%    +2.72%
   bottom    swing_low 135.0       15.0        52.6%        -1.0pp       +0.85%         +0.48%    -0.65%    +2.38%
   bottom    swing_mid 162.0       15.0        52.5%        -1.1pp       +1.32%         +0.47%    +0.13%    +2.60%
      top    swing_mid 166.0       15.0        51.8%        -1.8pp       +0.35%         +0.40%    -0.85%    +1.55%
      top    swing_low 193.0       15.0        50.8%        -2.8pp       +0.13%         +0.17%    -0.82%    +1.12%

=== Direction × candidate_volume_ratio tercile ===
direction vol_bucket     n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
   bottom   vol_high 134.0       15.0        60.4%        +6.8pp       +2.58%         +1.17%    +1.17%    +4.12%
      top    vol_mid 156.0       15.0        58.3%        +4.7pp       +1.38%         +1.04%    +0.15%    +2.58%
   bottom    vol_mid 172.0       15.0        51.7%        -1.9pp       +0.60%         +0.51%    -0.53%    +1.74%
   bottom    vol_low 179.0       15.0        51.4%        -2.2pp       +1.10%         +0.35%    +0.03%    +2.21%
      top   vol_high 194.0       15.0        51.0%        -2.6pp       +0.34%         +0.03%    -0.67%    +1.33%
      top    vol_low 149.0       15.0        51.0%        -2.6pp       +0.11%         +0.85%    -1.36%    +1.61%
      top         na   1.0        1.0         0.0%       -53.6pp       -2.56%         -2.56%    -2.56%    -2.56%

=== Direction × wick × swing ===
direction wick_bucket swing_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
   bottom    wick_mid   swing_high 63.0       13.0        68.3%       +14.6pp       +2.30%         +1.86%    +0.83%    +3.80%
      top    wick_low    swing_mid 57.0       14.0        63.2%        +9.6pp       +1.53%         +1.19%    -0.49%    +3.62%
   bottom    wick_low    swing_low 51.0       13.0        62.7%        +9.1pp       +2.60%         +0.80%    -0.36%    +5.71%
      top   wick_high   swing_high 49.0       14.0        59.2%        +5.6pp       +2.50%         +1.77%    -0.09%    +5.13%
      top    wick_low   swing_high 44.0       13.0        59.1%        +5.5pp       +0.50%         +2.50%    -2.10%    +2.93%
   bottom    wick_low    swing_mid 55.0       15.0        58.2%        +4.6pp       +2.92%         +0.70%    +0.89%    +5.37%
   bottom   wick_high    swing_mid 54.0       15.0        57.4%        +3.8pp       +0.77%         +0.93%    -1.21%    +2.62%
      top    wick_mid   swing_high 48.0       14.0        56.2%        +2.6pp       +1.40%         +1.22%    -1.26%    +4.13%
      top    wick_mid    swing_low 63.0       14.0        54.0%        +0.4pp       +0.16%         +0.44%    -1.60%    +1.89%
   bottom    wick_low   swing_high 59.0       14.0        50.8%        -2.8pp       +1.87%         +0.18%    -0.06%    +3.77%
      top    wick_low    swing_low 60.0       14.0        50.0%        -3.6pp       +0.45%         -0.01%    -1.03%    +1.95%
   bottom   wick_high   swing_high 66.0       14.0        50.0%        -3.6pp       +0.92%         -0.11%    -0.88%    +2.91%
   bottom    wick_mid    swing_low 44.0       13.0        50.0%        -3.6pp       +0.61%         +0.28%    -1.21%    +2.48%
      top   wick_high    swing_low 70.0       13.0        48.6%        -5.0pp       -0.17%         -0.13%    -1.92%    +1.49%
      top   wick_high    swing_mid 50.0       15.0        46.0%        -7.6pp       +0.37%         -0.43%    -1.89%    +2.71%
      top    wick_mid    swing_mid 59.0       15.0        45.8%        -7.8pp       -0.80%         -0.52%    -2.73%    +1.00%
   bottom   wick_high    swing_low 40.0       13.0        42.5%       -11.1pp       -1.12%         -1.80%    -3.77%    +1.50%
   bottom    wick_mid    swing_mid 53.0       15.0        41.5%       -12.1pp       +0.23%         -0.85%    -1.82%    +2.28%

  >>> SWEET SPOTS (n≥15, hit_uplift ≥ +10.0pp):
    bottom / wick_mid / swing_high                           n= 63  hit=68.3% (+14.6pp)  mean=+2.30%  CI [+0.83, +3.80]%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    bottom / wick_high / swing_low                           n= 40  hit=42.5% (-11.1pp)  mean=-1.12%  CI [-3.77, +1.50]%
    bottom / wick_mid / swing_mid                            n= 53  hit=41.5% (-12.1pp)  mean=+0.23%  CI [-1.82, +2.28]%

=== Direction × wick × volume ===
direction wick_bucket vol_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
      top    wick_low    vol_mid 49.0       14.0        63.3%        +9.7pp       +1.85%         +1.68%    -0.47%    +4.05%
   bottom    wick_mid   vol_high 46.0       15.0        63.0%        +9.4pp       +1.97%         +1.77%    +0.31%    +3.60%
   bottom    wick_low   vol_high 48.0       12.0        62.5%        +8.9pp       +3.85%         +0.79%    +0.88%    +7.21%
      top    wick_low   vol_high 60.0       12.0        58.3%        +4.7pp       +0.84%         +0.91%    -1.10%    +2.76%
      top    wick_mid    vol_mid 53.0       14.0        56.6%        +3.0pp       +0.79%         +0.83%    -1.42%    +2.94%
      top   wick_high    vol_mid 54.0       14.0        55.6%        +2.0pp       +1.52%         +0.80%    -0.15%    +3.23%
   bottom    wick_low    vol_mid 54.0       15.0        55.6%        +2.0pp       +2.03%         +0.65%    +0.18%    +3.99%
   bottom   wick_high   vol_high 40.0       14.0        55.0%        +1.4pp       +1.74%         +0.46%    -0.59%    +4.52%
      top    wick_mid    vol_low 57.0       13.0        54.4%        +0.8pp       +0.11%         +1.13%    -2.22%    +2.44%
   bottom    wick_low    vol_low 63.0       15.0        54.0%        +0.4pp       +1.73%         +0.35%    -0.21%    +3.96%
   bottom    wick_mid    vol_low 62.0       14.0        51.6%        -2.0pp       +1.56%         +0.85%    +0.05%    +3.19%
      top    wick_low    vol_low 51.0       15.0        51.0%        -2.6pp       -0.05%         +0.85%    -1.80%    +1.76%
   bottom    wick_mid    vol_mid 52.0       15.0        50.0%        -3.6pp       -0.06%         +0.23%    -2.28%    +2.07%
   bottom   wick_high    vol_mid 66.0       15.0        50.0%        -3.6pp       -0.04%         +0.08%    -1.94%    +1.82%
      top   wick_high   vol_high 74.0       15.0        50.0%        -3.6pp       +0.46%         +0.07%    -1.15%    +2.10%
   bottom   wick_high    vol_low 54.0       15.0        48.1%        -5.5pp       -0.18%         -0.05%    -2.12%    +1.69%
      top   wick_high    vol_low 41.0       15.0        46.3%        -7.3pp       +0.32%         -0.42%    -3.20%    +3.92%
      top    wick_mid   vol_high 60.0       15.0        45.0%        -8.6pp       -0.31%         -0.55%    -2.00%    +1.40%
      top    wick_low         na  1.0        1.0         0.0%       -53.6pp       -2.56%         -2.56%    -2.56%    -2.56%

=== SWEET-SPOT SEARCH: direction × wick × swing × volume ===
direction wick_bucket swing_bucket vol_bucket    n  n_symbols hit_rate_pct hit_uplift_pp mean_ret_pct median_ret_pct ci_lo_pct ci_hi_pct
      top    wick_low    swing_mid   vol_high 17.0        8.0        82.4%       +28.7pp       +4.02%         +2.59%    +0.90%    +8.09%
   bottom    wick_mid   swing_high    vol_low 16.0       13.0        81.2%       +27.6pp       +4.24%         +3.29%    +0.85%    +7.92%
   bottom    wick_low    swing_mid   vol_high 12.0        8.0        75.0%       +21.4pp       +7.94%         +4.24%    +1.56%   +15.87%
      top    wick_low    swing_mid    vol_mid 15.0        9.0        73.3%       +19.7pp       +1.41%         +1.19%    -2.67%    +4.91%
      top    wick_low   swing_high    vol_low 11.0       10.0        72.7%       +19.1pp       +1.74%         +3.18%    -1.12%    +4.18%
   bottom    wick_low    swing_low    vol_mid 14.0       10.0        71.4%       +17.8pp       +1.72%         +1.52%    -1.97%    +4.71%
   bottom   wick_high    swing_mid    vol_mid 20.0       11.0        70.0%       +16.4pp       +2.52%         +1.75%    +0.17%    +5.21%
      top   wick_high   swing_high    vol_low 10.0        6.0        70.0%       +16.4pp       +7.05%         +3.36%    -0.48%   +14.99%
   bottom    wick_mid    swing_low   vol_high 13.0        6.0        69.2%       +15.6pp       +2.49%         +1.67%    +0.19%    +5.00%
   bottom   wick_high    swing_mid   vol_high  9.0        7.0        66.7%       +13.1pp       +0.86%         +0.81%    -4.07%    +4.95%
   bottom    wick_mid   swing_high    vol_mid 24.0        8.0        66.7%       +13.1pp       +1.36%         +1.50%    -0.74%    +3.34%
      top    wick_mid   swing_high    vol_low 12.0        8.0        66.7%       +13.1pp       +0.82%         +1.69%    -5.67%    +8.06%
   bottom    wick_low    swing_low   vol_high 16.0        6.0        62.5%        +8.9pp       +2.99%         +0.75%    -2.55%    +9.70%
      top    wick_low   swing_high    vol_mid 13.0       10.0        61.5%        +7.9pp       +1.14%         +2.23%    -5.17%    +6.32%
   bottom   wick_high   swing_high    vol_low 18.0        9.0        61.1%        +7.5pp       +1.71%         +1.49%    -0.56%    +4.31%
   bottom    wick_mid   swing_high   vol_high 23.0       11.0        60.9%        +7.3pp       +1.94%         +1.86%    -0.32%    +4.44%
   bottom    wick_mid    swing_mid   vol_high 10.0        9.0        60.0%        +6.4pp       +1.35%         +1.74%    -2.88%    +5.11%
      top    wick_mid    swing_mid    vol_mid 17.0       10.0        58.8%        +5.2pp       +0.47%         +2.15%    -2.48%    +3.22%
   bottom    wick_low    swing_low    vol_low 21.0       10.0        57.1%        +3.5pp       +2.88%         +0.35%    -1.87%    +8.11%
      top    wick_low    swing_low    vol_mid 21.0       10.0        57.1%        +3.5pp       +2.61%         +1.68%    -0.03%    +5.58%
      top   wick_high   swing_high   vol_high 23.0       12.0        56.5%        +2.9pp       +0.61%         +0.39%    -2.72%    +4.06%
      top   wick_high   swing_high    vol_mid 16.0        9.0        56.2%        +2.6pp       +2.39%         +1.04%    -0.70%    +5.60%
      top   wick_high    swing_low    vol_mid 18.0       11.0        55.6%        +2.0pp       +2.32%         +1.34%    -0.46%    +5.55%
      top    wick_mid    swing_low    vol_mid 18.0       10.0        55.6%        +2.0pp       -1.07%         +0.40%    -5.43%    +3.03%
      top    wick_mid   swing_high    vol_mid 18.0        9.0        55.6%        +2.0pp       +2.96%         +1.08%    -0.60%    +6.66%
   bottom    wick_low   swing_high   vol_high 20.0       10.0        55.0%        +1.4pp       +2.10%         +0.35%    -1.11%    +5.32%
      top   wick_high    swing_mid    vol_mid 20.0       10.0        55.0%        +1.4pp       +0.10%         +0.38%    -2.37%    +2.56%
      top    wick_mid    swing_low   vol_high 22.0       10.0        54.5%        +0.9pp       +1.11%         +0.71%    -1.29%    +3.49%
   bottom    wick_low    swing_mid    vol_low 24.0       12.0        54.2%        +0.6pp       +1.68%         +0.29%    -0.78%    +4.49%
   bottom    wick_low    swing_mid    vol_mid 19.0       11.0        52.6%        -1.0pp       +1.33%         +0.69%    -1.15%    +3.91%
   bottom   wick_high   swing_high   vol_high 21.0       10.0        52.4%        -1.2pp       +2.72%         +0.24%    -0.77%    +7.47%
      top    wick_mid    swing_low    vol_low 23.0       11.0        52.2%        -1.4pp       +0.22%         +1.14%    -2.34%    +2.71%
      top    wick_mid    swing_mid    vol_low 22.0       10.0        50.0%        -3.6pp       -0.39%         +0.36%    -4.48%    +3.18%
   bottom    wick_low   swing_high    vol_low 18.0       11.0        50.0%        -3.6pp       +0.47%         +0.21%    -2.35%    +3.19%
      top    wick_low   swing_high   vol_high 20.0       10.0        50.0%        -3.6pp       -0.60%         -0.06%    -4.85%    +3.23%
   bottom   wick_high    swing_low   vol_high 10.0        7.0        50.0%        -3.6pp       +0.49%         +0.17%    -2.90%    +3.94%
      top    wick_mid   swing_high   vol_high 18.0       11.0        50.0%        -3.6pp       +0.23%         +0.83%    -3.90%    +4.39%
      top   wick_high    swing_low   vol_high 35.0       13.0        48.6%        -5.0pp       +0.29%         -0.03%    -1.72%    +2.31%
      top    wick_low    swing_low   vol_high 23.0       11.0        47.8%        -5.8pp       -0.27%         -0.04%    -2.48%    +1.73%
   bottom    wick_low   swing_high    vol_mid 21.0       11.0        47.6%        -6.0pp       +2.86%         -0.53%    -0.78%    +6.88%
      top    wick_low    swing_mid    vol_low 24.0       11.0        45.8%        -7.8pp       -0.00%         -0.72%    -3.11%    +3.35%
   bottom    wick_mid    swing_low    vol_mid 11.0        8.0        45.5%        -8.1pp       -2.47%         -0.34%    -6.73%    +1.53%
   bottom   wick_high    swing_mid    vol_low 25.0       14.0        44.0%        -9.6pp       -0.67%         -0.11%    -3.96%    +2.37%
      top   wick_high    swing_mid   vol_high 16.0       11.0        43.8%        -9.9pp       +0.64%         -0.62%    -2.76%    +4.38%
      top    wick_low    swing_low    vol_low 16.0        9.0        43.8%        -9.9pp       -1.36%         -1.21%    -3.39%    +0.49%
   bottom    wick_mid    swing_mid    vol_low 26.0       11.0        42.3%       -11.3pp       +0.28%         -0.79%    -1.72%    +2.37%
   bottom   wick_high    swing_low    vol_mid 19.0       10.0        42.1%       -11.5pp       -1.37%         -1.65%    -6.15%    +3.13%
      top   wick_high    swing_low    vol_low 17.0        8.0        41.2%       -12.4pp       -3.75%         -1.96%    -8.09%    +0.32%
   bottom   wick_high   swing_high    vol_mid 27.0       12.0        40.7%       -12.9pp       -1.01%         -1.47%    -3.46%    +1.69%
   bottom    wick_mid    swing_low    vol_low 20.0       12.0        40.0%       -13.6pp       +1.08%         -0.45%    -1.06%    +3.87%
   bottom   wick_high    swing_low    vol_low 11.0        9.0        36.4%       -17.2pp       -2.16%         -5.37%    -5.84%    +2.19%
      top   wick_high    swing_mid    vol_low 14.0       11.0        35.7%       -17.9pp       +0.44%         -1.25%    -5.75%    +7.13%
      top    wick_mid    swing_mid   vol_high 20.0       12.0        30.0%       -23.6pp       -2.34%         -2.52%    -4.61%    -0.01%
   bottom    wick_mid    swing_mid    vol_mid 17.0       10.0        29.4%       -24.2pp       -0.50%         -1.89%    -5.58%    +4.59%
      top    wick_low    swing_mid         na  1.0        1.0         0.0%       -53.6pp       -2.56%         -2.56%    -2.56%    -2.56%

  >>> SWEET SPOTS (n≥15, hit_uplift ≥ +10.0pp):
    top / wick_low / swing_mid / vol_high                    n= 17  hit=82.4% (+28.7pp)  mean=+4.02%  CI [+0.90, +8.09]%
    bottom / wick_mid / swing_high / vol_low                 n= 16  hit=81.2% (+27.6pp)  mean=+4.24%  CI [+0.85, +7.92]%
    top / wick_low / swing_mid / vol_mid                     n= 15  hit=73.3% (+19.7pp)  mean=+1.41%  CI [-2.67, +4.91]%
    bottom / wick_high / swing_mid / vol_mid                 n= 20  hit=70.0% (+16.4pp)  mean=+2.52%  CI [+0.17, +5.21]%
    bottom / wick_mid / swing_high / vol_mid                 n= 24  hit=66.7% (+13.1pp)  mean=+1.36%  CI [-0.74, +3.34]%

  <<< ANTI-SPOTS / filter candidates (n≥15, hit_uplift ≤ -10.0pp):
    bottom / wick_mid / swing_mid / vol_low                  n= 26  hit=42.3% (-11.3pp)  mean=+0.28%  CI [-1.72, +2.37]%
    bottom / wick_high / swing_low / vol_mid                 n= 19  hit=42.1% (-11.5pp)  mean=-1.37%  CI [-6.15, +3.13]%
    top / wick_high / swing_low / vol_low                    n= 17  hit=41.2% (-12.4pp)  mean=-3.75%  CI [-8.09, +0.32]%
    bottom / wick_high / swing_high / vol_mid                n= 27  hit=40.7% (-12.9pp)  mean=-1.01%  CI [-3.46, +1.69]%
    bottom / wick_mid / swing_low / vol_low                  n= 20  hit=40.0% (-13.6pp)  mean=+1.08%  CI [-1.06, +3.87]%
    top / wick_mid / swing_mid / vol_high                    n= 20  hit=30.0% (-23.6pp)  mean=-2.34%  CI [-4.61, -0.01]%
    bottom / wick_mid / swing_mid / vol_mid                  n= 17  hit=29.4% (-24.2pp)  mean=-0.50%  CI [-5.58, +4.59]%
```

## OOS validation (60/40 train/test split)

### Pool US OOS
```
  OOS: dropped 5 train signals whose forward-return window crossed cutoff 2024-07-08

Per-signal pooled CSV → ../data/review/sweet_spots_pool_us_h20_oos.csv
Pool: 10 symbol(s) — ['SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'GDX', 'XLF', 'XLK', 'TLT', 'NVDA']
Instrument class: us_equity  Horizon: 20d
  SPY:   43 signals
  QQQ:   25 signals
  IWM:   25 signals
  DIA:   24 signals
  GLD:   20 signals
  GDX:   24 signals
  XLF:   30 signals
  XLK:   31 signals
  TLT:   20 signals
  NVDA:   24 signals

Total pooled signals: 266 from 10 symbols
Baseline (all pooled signals): hit_rate=63.9%  mean=+2.04%

OOS split: train=154 (2021-06-08→2024-05-22) test=107 (2024-07-08→2026-04-15)
Train baseline hit: 68.8%   Test baseline hit: 57.0%

=== OOS: Direction × wick tercile (n_train≥15 AND n_test≥15) ===
direction wick_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
   bottom   wick_high      39              69.2%              +0.4pp     27             70.4%            +13.4pp                     +1.1pp
   bottom    wick_low      37              75.7%              +6.8pp     21             66.7%             +9.7pp                     -9.0pp
   bottom    wick_mid      37              67.6%              -1.3pp     15             53.3%             -3.7pp                    -14.2pp

=== OOS: Direction × prior_swing tercile (n_train≥15 AND n_test≥15) ===
direction swing_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
   bottom    swing_low      45              62.2%              -6.6pp     38             68.4%            +11.4pp                     +6.2pp
   bottom    swing_mid      34              85.3%             +16.5pp     19             68.4%            +11.4pp                    -16.9pp
      top   swing_high      18              72.2%              +3.4pp     30             40.0%            -17.0pp                    -32.2pp

  >>> STABLE SWEET SPOTS (both train and test uplift ≥ +10.0pp):
    bottom / swing_mid                                       train n=34 85.3% (+16.5pp)  test n=19 68.4% (+11.4pp)

=== OOS: Direction × candidate_volume_ratio tercile (n_train≥15 AND n_test≥15) ===
direction vol_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
   bottom    vol_low      30              66.7%              -2.2pp     32             71.9%            +14.9pp                     +5.2pp
   bottom    vol_mid      41              68.3%              -0.5pp     15             66.7%             +9.7pp                     -1.6pp
   bottom   vol_high      42              76.2%              +7.4pp     16             50.0%             -7.0pp                    -26.2pp
      top    vol_low      21              61.9%              -6.9pp     19             36.8%            -20.2pp                    -25.1pp

=== OOS: Direction × wick × swing (n_train≥15 AND n_test≥15) ===
direction wick_bucket swing_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
   bottom   wick_high    swing_low      19              63.2%              -5.7pp     15             73.3%            +16.3pp                    +10.2pp

=== OOS: Direction × wick × volume (n_train≥15 AND n_test≥15) ===
(no cell meets both-side n threshold)

=== OOS: SWEET-SPOT SEARCH: direction × wick × swing × volume (n_train≥15 AND n_test≥15) ===
(no cell meets both-side n threshold)
```

### Pool CN index OOS
```
  OOS: dropped 2 train signals whose forward-return window crossed cutoff 2022-11-27

Per-signal pooled CSV → ../data/review/sweet_spots_pool_cn_h20_oos.csv
Pool: 4 symbol(s) — ['kq_m_cffex_if', 'kq_m_cffex_ih', 'kq_m_cffex_ic', 'kq_m_cffex_im']
Instrument class: cn_futures  Horizon: 20d
  kq_m_cffex_if:   72 signals
  kq_m_cffex_ih:   67 signals
  kq_m_cffex_ic:   77 signals
  kq_m_cffex_im:   21 signals

Total pooled signals: 237 from 4 symbols
Baseline (all pooled signals): hit_rate=60.3%  mean=+0.90%

OOS split: train=140 (2016-02-29→2022-09-14) test=95 (2022-11-27→2026-04-20)
Train baseline hit: 60.0%   Test baseline hit: 60.0%

=== OOS: Direction × wick tercile (n_train≥15 AND n_test≥15) ===
direction wick_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
   bottom   wick_high      21              57.1%              -2.9pp     15             80.0%            +20.0pp                    +22.9pp
   bottom    wick_mid      25              64.0%              +4.0pp     15             66.7%             +6.7pp                     +2.7pp
      top    wick_low      22              68.2%              +8.2pp     18             61.1%             +1.1pp                     -7.1pp
   bottom    wick_low      25              76.0%             +16.0pp     16             56.2%             -3.8pp                    -19.8pp
      top   wick_high      26              38.5%             -21.5pp     16             56.2%             -3.8pp                    +17.8pp
      top    wick_mid      21              57.1%              -2.9pp     15             40.0%            -20.0pp                    -17.1pp

  XXX COLLAPSED (train sweet, test not):
    bottom / wick_low                                        train n=25 +16.0pp  test n=16 -3.8pp  DRIFT -19.8pp

=== OOS: Direction × prior_swing tercile (n_train≥15 AND n_test≥15) ===
direction swing_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
   bottom   swing_high      21              66.7%              +6.7pp     18             66.7%             +6.7pp                     +0.0pp
      top    swing_mid      30              40.0%             -20.0pp     16             56.2%             -3.8pp                    +16.2pp

=== OOS: Direction × candidate_volume_ratio tercile (n_train≥15 AND n_test≥15) ===
direction vol_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
   bottom   vol_high      27              63.0%              +3.0pp     19             68.4%             +8.4pp                     +5.5pp
      top    vol_low      30              63.3%              +3.3pp     19             68.4%             +8.4pp                     +5.1pp
   bottom    vol_low      17              76.5%             +16.5pp     18             61.1%             +1.1pp                    -15.4pp
      top   vol_high      20              40.0%             -20.0pp     17             47.1%            -12.9pp                     +7.1pp

  XXX COLLAPSED (train sweet, test not):
    bottom / vol_low                                         train n=17 +16.5pp  test n=18 +1.1pp  DRIFT -15.4pp

=== OOS: Direction × wick × swing (n_train≥15 AND n_test≥15) ===
(no cell meets both-side n threshold)

=== OOS: Direction × wick × volume (n_train≥15 AND n_test≥15) ===
(no cell meets both-side n threshold)

=== OOS: SWEET-SPOT SEARCH: direction × wick × swing × volume (n_train≥15 AND n_test≥15) ===
(no cell meets both-side n threshold)
```

### Pool CN commodity OOS
```
  OOS: dropped 4 train signals whose forward-return window crossed cutoff 2022-08-24
Pool: 15 symbol(s) — ['kq_m_shfe_rb', 'kq_m_shfe_cu', 'kq_m_shfe_au', 'kq_m_shfe_ag', 'kq_m_dce_m', 'kq_m_dce_i', 'kq_m_dce_j', 'kq_m_dce_jm', 'kq_m_dce_p', 'kq_m_dce_y', 'kq_m_czce_ta', 'kq_m_czce_ma', 'kq_m_czce_cf', 'kq_m_czce_sr', 'kq_m_ine_sc']
Instrument class: cn_futures  Horizon: 20d
  kq_m_shfe_rb:   75 signals
  kq_m_shfe_cu:   53 signals
  kq_m_shfe_au:   54 signals
  kq_m_shfe_ag:   71 signals
  kq_m_dce_m:   76 signals
  kq_m_dce_i:   74 signals
  kq_m_dce_j:   76 signals
  kq_m_dce_jm:   68 signals
  kq_m_dce_p:   69 signals
  kq_m_dce_y:   68 signals
  kq_m_czce_ta:   61 signals
  kq_m_czce_ma:   55 signals
  kq_m_czce_cf:   56 signals
  kq_m_czce_sr:   83 signals
  kq_m_ine_sc:   46 signals

Total pooled signals: 985 from 15 symbols
Baseline (all pooled signals): hit_rate=53.6%  mean=+0.95%

OOS split: train=587 (2016-01-21→2022-06-23) test=394 (2022-08-24→2026-04-21)
Train baseline hit: 55.7%   Test baseline hit: 51.0%

=== OOS: Direction × wick tercile (n_train≥15 AND n_test≥15) ===
direction wick_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
      top    wick_mid     107              48.6%              -7.1pp     67             55.2%             +4.2pp                     +6.6pp
   bottom    wick_mid      88              54.5%              -1.2pp     77             54.5%             +3.5pp                     +0.0pp
   bottom    wick_low      94              60.6%              +4.9pp     70             52.9%             +1.8pp                     -7.8pp
      top    wick_low     102              61.8%              +6.1pp     59             49.2%             -1.9pp                    -12.6pp
      top   wick_high     101              54.5%              -1.3pp     63             47.6%             -3.4pp                     -6.8pp
   bottom   wick_high      95              54.7%              -1.0pp     58             44.8%             -6.2pp                     -9.9pp

=== OOS: Direction × prior_swing tercile (n_train≥15 AND n_test≥15) ===
direction swing_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
   bottom    swing_low      90              52.2%              -3.5pp     65             63.1%            +12.1pp                    +10.9pp
      top    swing_mid      95              50.5%              -5.2pp     38             60.5%             +9.5pp                    +10.0pp
      top   swing_high     109              59.6%              +3.9pp     30             50.0%             -1.0pp                     -9.6pp
   bottom   swing_high      87              65.5%              +9.8pp    101             48.5%             -2.5pp                    -17.0pp
      top    swing_low     106              53.8%              -1.9pp    121             47.9%             -3.1pp                     -5.8pp
   bottom    swing_mid     100              53.0%              -2.7pp     39             38.5%            -12.6pp                    -14.5pp

=== OOS: Direction × candidate_volume_ratio tercile (n_train≥15 AND n_test≥15) ===
direction vol_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
      top    vol_mid      97              54.6%              -1.1pp     70             61.4%            +10.4pp                     +6.8pp
   bottom   vol_high      67              67.2%             +11.5pp     67             56.7%             +5.7pp                    -10.4pp
   bottom    vol_low     112              50.0%              -5.7pp     61             50.8%             -0.2pp                     +0.8pp
      top    vol_low      83              55.4%              -0.3pp     53             47.2%             -3.8pp                     -8.3pp
   bottom    vol_mid      98              57.1%              +1.4pp     77             46.8%             -4.3pp                    -10.4pp
      top   vol_high     129              55.0%              -0.7pp     66             42.4%             -8.6pp                    -12.6pp

  XXX COLLAPSED (train sweet, test not):
    bottom / vol_high                                        train n=67 +11.5pp  test n=67 +5.7pp  DRIFT -10.4pp

=== OOS: Direction × wick × swing (n_train≥15 AND n_test≥15) ===
direction wick_bucket swing_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
   bottom    wick_low    swing_low      34              58.8%              +3.1pp     25             76.0%            +25.0pp                    +17.2pp
      top    wick_mid    swing_mid      36              36.1%             -19.6pp     18             66.7%            +15.7pp                    +30.6pp
   bottom    wick_mid   swing_high      30              80.0%             +24.3pp     35             57.1%             +6.1pp                    -22.9pp
   bottom    wick_mid    swing_low      24              41.7%             -14.0pp     25             56.0%             +5.0pp                    +14.3pp
   bottom   wick_high    swing_low      32              53.1%              -2.6pp     15             53.3%             +2.3pp                     +0.2pp
      top    wick_mid    swing_low      32              56.2%              +0.5pp     42             50.0%             -1.0pp                     -6.2pp
      top   wick_high    swing_low      37              45.9%              -9.8pp     41             48.8%             -2.2pp                     +2.8pp
   bottom    wick_mid    swing_mid      34              41.2%             -14.5pp     17             47.1%             -4.0pp                     +5.9pp
   bottom    wick_low   swing_high      26              57.7%              +2.0pp     33             45.5%             -5.6pp                    -12.2pp
      top    wick_low    swing_low      37              59.5%              +3.8pp     38             44.7%             -6.3pp                    -14.7pp
   bottom   wick_high   swing_high      31              58.1%              +2.4pp     33             42.4%             -8.6pp                    -15.6pp

  XXX COLLAPSED (train sweet, test not):
    bottom / wick_mid / swing_high                           train n=30 +24.3pp  test n=35 +6.1pp  DRIFT -22.9pp

=== OOS: Direction × wick × volume (n_train≥15 AND n_test≥15) ===
direction wick_bucket vol_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
      top    wick_mid    vol_mid      33              42.4%             -13.3pp     24             70.8%            +19.8pp                    +28.4pp
   bottom    wick_low   vol_high      24              66.7%             +11.0pp     23             60.9%             +9.9pp                     -5.8pp
   bottom    wick_mid   vol_high      23              73.9%             +18.2pp     27             59.3%             +8.2pp                    -14.7pp
      top   wick_high    vol_mid      33              51.5%              -4.2pp     24             58.3%             +7.3pp                     +6.8pp
   bottom   wick_high    vol_low      35              45.7%             -10.0pp     16             56.2%             +5.2pp                    +10.5pp
      top    wick_low    vol_mid      31              71.0%             +15.3pp     22             54.5%             +3.5pp                    -16.4pp
   bottom    wick_mid    vol_mid      24              45.8%              -9.9pp     30             53.3%             +2.3pp                     +7.5pp
   bottom    wick_mid    vol_low      41              48.8%              -6.9pp     20             50.0%             -1.0pp                     +1.2pp
   bottom    wick_low    vol_mid      34              61.8%              +6.1pp     22             50.0%             -1.0pp                    -11.8pp
      top    wick_mid    vol_low      32              59.4%              +3.7pp     22             50.0%             -1.0pp                     -9.4pp
   bottom    wick_low    vol_low      36              55.6%              -0.2pp     25             48.0%             -3.0pp                     -7.6pp
      top    wick_low    vol_low      27              51.9%              -3.9pp     19             47.4%             -3.6pp                     -4.5pp
   bottom   wick_high   vol_high      20              60.0%              +4.3pp     17             47.1%             -4.0pp                    -12.9pp
      top    wick_low   vol_high      43              62.8%              +7.1pp     18             44.4%             -6.6pp                    -18.3pp
      top    wick_mid   vol_high      42              45.2%             -10.5pp     21             42.9%             -8.2pp                     -2.4pp
      top   wick_high   vol_high      44              56.8%              +1.1pp     27             40.7%            -10.3pp                    -16.1pp
   bottom   wick_high    vol_mid      40              60.0%              +4.3pp     25             36.0%            -15.0pp                    -24.0pp
Per-signal pooled CSV → ../data/review/sweet_spots_pool_cn_commodity_h20_oos.csv


  XXX COLLAPSED (train sweet, test not):
    bottom / wick_low / vol_high                             train n=24 +11.0pp  test n=23 +9.9pp  DRIFT -5.8pp
    bottom / wick_mid / vol_high                             train n=23 +18.2pp  test n=27 +8.2pp  DRIFT -14.7pp
    top / wick_low / vol_mid                                 train n=31 +15.3pp  test n=22 +3.5pp  DRIFT -16.4pp

=== OOS: SWEET-SPOT SEARCH: direction × wick × swing × volume (n_train≥15 AND n_test≥15) ===
direction wick_bucket swing_bucket vol_bucket n_train hit_rate_pct_train hit_uplift_pp_train n_test hit_rate_pct_test hit_uplift_pp_test train_to_test_hit_drift_pp
      top   wick_high    swing_low   vol_high      20              50.0%              -5.7pp     17             47.1%             -4.0pp                     -2.9pp
```
