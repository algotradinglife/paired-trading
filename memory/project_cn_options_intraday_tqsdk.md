---
name: project_cn_options_intraday_tqsdk
description: "TqSdk free tier CN options intraday coverage — symbol formats, confirmed working exchanges, fetch script"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

TqSdk free tier (wss://free-api.shinnytech.com) DOES serve full historical intraday (15min/60min) for CN commodity options, including expired contracts.

**Symbol formats by exchange:**
- SHFE (au/cu/rb/ag): `SHFE.{instr}{yymm}{C/P}{strike}` — NO hyphens, UPPERCASE C/P
  - Example: `SHFE.au2112C380`, `SHFE.cu2404C62000`
- DCE (m/i/pg/c): `DCE.{instr}{yymm}-{C/P}-{strike}` — WITH hyphens, uppercase C/P
  - Example: `DCE.m2209-C-3000`
- CZCE (sr/ma/ta/cf): `CZCE.{INSTR_UPPER}{yyy}{C/P}{strike}` — NO hyphens, 3-digit month
  - `yyy` = last digit of year + 2-digit month: `sr2511` → `511`
  - Example: `CZCE.SR201C5900` (sr2201 = Jan 2022)

**Coverage confirmed:**
- SHFE AU (gold): ✓ full history (tested au2112C380 = Dec 2021, works)
- DCE M (soybean meal): ✓ 4821 bars back to 2021-09-16 (tested m2209-C-3000)
- CZCE SR (sugar): ✓ full history back to 2021-02-03 (tested sr2201c5900)
- SHFE CU (copper): expected to work, same format as AU
- SHFE RB (rebar): expected to work
- DCE I (iron ore): some symbols timeout — may be illiquid strikes

**Data depth:** Full contract lifetime from listing to expiry. Not time-limited.
Retired contracts disappear only after being delisted from TqSdk's catalog.

**Fetch script:** `scripts/fetch_options_intraday_cn.py`
- Usage: `scripts/_with_creds.sh tqsdk uv run python scripts/fetch_options_intraday_cn.py --underlying au cu --tfs 15min 60min`
- Outputs to `data/options/cn/{underlying}/{ticker}_{tf}.json`
- Batch size 20 per TqSdk session
- Skip-complete logic based on MIN_BARS=5

**Why:** cn commodity option intraday needed for 4-tick stop loss analysis (Xiao framework).
