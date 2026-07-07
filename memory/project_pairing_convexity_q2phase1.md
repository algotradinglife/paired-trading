---
name: project_pairing_convexity_q2phase1
description: 配对凸性 Q2-Phase1 实测：au call-favorable/rb 不/cu 矛盾→precious-base 二分太粗，cu 负 EV 须 Phase2 期权侧解释
metadata:
  type: project
---

期权配对「条件凸性」假设的 Phase 1 实测（card t_49029cd2 承接；commit c172fa50；doc/conditional-tails-q2-phase1-2026-06-16.md；工具 `scripts/analyze_conditional_tails.py`）。

**假设**（philosopher）：call 配对只在标的条件右尾凸性兑现时赚钱；贵金属右尾肥于基本金属，解释 DD-line ag/au EV+ vs cu/rb EV−（[[project_ddline_options_findings]]）。

**方法学纠正（重要）**：MFE/MAE excursion 被波动率主导、近似对称（P[MFE≥2]≈P[MAE≥2] 全品种），度量 σ√H 而非凸性——**不能用 excursion 右尾质量测凸性**。决策相关量 = terminal 期权回报代理 `E[max(term−k,0)]`（k-ATR-OTM call 内在价值）及 **call/put 比率**。

**结果**（all-candidate 结构性总体，n≈990–1180/品种）：
- **au**：call/put@1ATR **1.64–1.65**，terminal skew +0.50（唯一正）→ call 凸性favorable ✓
- **rb**：call/put **0.93–1.04**，负漂移 → 缺 call 凸性 ✓（与 DD-line rb 负 EV 一致）
- **cu**：call/put **1.43–1.55**（标的 call-favorable）却 DD-line EV− → ✗ **标的前向分布解释不了 cu−**。

**裁决**：
1. **「贵金属 vs 基本金属」二分太粗**——真正分界是逐品种前向漂移/凸性（au/cu 同属 call-favorable，rb 另一类）。
2. **cu 是关键判例**：标的层 call-favorable 但期权 EV−，差异必在**期权侧（IV/theta 太贵 vs realized 凸性）**→ Phase 2（realized vs implied）必需，优先验 cu。
3. Q3 put：无品种结构性偏 put → de-prioritize 成立。

**Why/caveat**：spec（replica 选中）子集 n=15–42 太小且 au-spec 自相矛盾（负漂移）→ 可靠读数是 all-candidate；全为标的层，未含 IV/theta。au 是唯一贵金属代表，ag 待数据确认 precious 共性。

**How to apply**：晋升任何配对选品判据前须 Phase 2（期权 IV/skew @信号时点，ag/au/cu/rb，优先 cu）；Phase 2 数据须**另起 data 卡**（当前 t_f68f93e2 是闸门 OOS 的 al/zn/ni/ag/i 5min 标的，与此无关）。相关 [[project_spec001_ev_eval]]、[[option-pairing-edge-triage-2026-06-16]]。
