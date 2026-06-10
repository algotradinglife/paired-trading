# Standing up `paired-trading` on a new machine (Windows WSL)

**Goal:** a fresh agent/person pulls the code from GitHub, connects it to the
data prepared on the new server, and runs. Data itself is prepared separately on
the target machine — this guide covers **code, environment, the data-access
contract, secrets, and the knowledge artifacts** (which are the priority).

> Target is **Windows WSL** (a Linux userland). All commands below are bash. The
> old macOS-keychain credential helper does **not** work here — see §4.

---

## 0. Two things that do NOT arrive via `git clone paired-trading`

These are the easy-to-miss blockers. Handle them first.

1. **`quant-data` — required dependency; the WSL box has its own (redesigned
   format).** `src/pyproject.toml` wires it as an editable source:
   `[tool.uv.sources] quant-data = { path = "../../quant-data", editable = true }`.
   On WSL, **repoint that source at the machine's existing `quant-data`** (adjust
   the relative/abs path, or `pip/uv add` it if it's installable) — do not copy
   the Mac one. The real work here is **API compatibility**, not fetching: see
   "Data-access contract" below. `uv sync` fails until this source resolves.

2. **The auto-memory / lessons store — out of repo, machine-path-keyed.**
   Lives at `~/.claude/projects/-Users-huhan-code-trading-paired-trading/memory/`
   (38 files: `MEMORY.md` index + 37 entries of decisions, feedback, validated
   findings). It is keyed to the *machine path*, so it will not appear on the new
   box. **➜ Copy it** to the new machine under the new path slug, e.g.
   `~/.claude/projects/-home-<user>-code-trading-paired-trading/memory/`.
   A version-controlled digest that DOES travel with the repo is **`doc/LESSONS.md`**.

---

## 1. Pull the code (both repos, same parent directory)

```bash
mkdir -p ~/code/trading && cd ~/code/trading
git clone git@github.com:algotradinglife/paired-trading.git
```
`quant-data` is already on this machine (§0.1) — edit
`src/pyproject.toml`'s `[tool.uv.sources] quant-data = { path = ... }` to point at
it (relative or absolute), instead of the macOS `../../quant-data` sibling.

### The data-access contract (what the redesigned `quant-data` must satisfy)

`paired-trading` reaches `quant-data` through one runtime chokepoint plus a set of
tooling imports. If the redesigned format keeps this **Python API**, the code runs
unchanged; if not, adapt the chokepoint first, then tooling as needed.

- **Runtime read chokepoint:** `src/data/store.py::BarStore` (wrapped by
  `data/bar_loader.py`, used by `score_today` + all backtests). It calls
  `quant_data.storage.parquet.ParquetStorage` and `quant_data.models.{Exchange,
  Interval}`, and `BarStore.load_barframe(symbol, exchange_mic, level)` must return
  a `BarFrame` whose `.df` has a tz-aware UTC `timestamp` column + OHLCV. **Adapt
  `data/store.py` here if the redesigned API differs** — it's the single seam for
  the read path.
- **Tooling imports (fetch / migrate / options):** ~24 scripts import
  `quant_data.{models (BarData/ContractData/Product/OptionType), storage(.parquet)
  .ParquetStorage, datafeed (Polygon/Minishare/YFinance/Akshare), options_manager
  .OptionsManager, DataManager}`. These only matter for the scripts you actually
  run (most strategy/backtest runs need only the chokepoint above).
- **Verify the wiring:** `uv run pytest -q -k "quant or parquet or options"`
  exercises this surface; then a `score_today` / backtest smoke (§5).

## 2. Python environment (3.13+, `uv`, pinned lockfile)

```bash
# install uv (https://docs.astral.sh/uv/) and Python 3.13 on WSL, then:
cd ~/code/trading/paired-trading/src
uv sync            # uses the committed uv.lock → reproducible install
```
Requires Python ≥ 3.13. Key deps (pinned in `uv.lock`): pandas ≥3, numpy ≥2.4,
scipy, tqsdk, akshare, yfinance, exchange-calendars, pydantic, plus the local
`quant-data`. Dev: pytest, ruff.

## 3. Connect the code to data access (the directory contract)

The code reads from `src/data/...` by default; several roots are env-overridable.
Point these at wherever the new server's prepared data lives. **`baselines/` is in
git** and travels with the clone — do not regenerate it.

| What | Default path | Env override | Notes |
|---|---|---|---|
| Quant Parquet store | `src/data/quant/{SHFE,DCE,CZCE,CFFEX,INE,NYSE}` | `QUANT_ROOT` | primary bar source; `bar_loader.DEFAULT_QUANT_ROOT` |
| JSON bar fallback | `src/data/raw/` | — | `{symbol}_daily.json` / `_60` / `_15` |
| CN options | `src/data/options/cn/{ag,au,...}` | — | option daily+intraday json |
| Derived / review outputs | `src/data/review/`, repo `data/review/` | `DERIVED_ROOT` | backtest CSVs, payoffs |
| Market-data root | — | `MARKET_DATA` | used by `drift_gate.sh` + some fetch scripts |
| Baselines (**in git**) | `baselines/*.json` | — | validated lane artifacts — single source of truth |

Create `.env` from `.env.example`, set the WSL paths, and `source .env` before
running. (On WSL, a Windows drive shows up as e.g. `/mnt/d/...`; a native WSL
path like `~/data/...` is faster.)

## 4. Secrets / credentials (WSL: env vars, not the macOS keychain)

`src/scripts/_with_creds.sh` loads secrets from the **macOS keychain**
(`security find-generic-password`) — it will not run on WSL. Instead export the
vars (put them in `.env` or `~/.bashrc`). These are needed **only by the
data-fetch/prep scripts**, not to run backtests on already-prepared data:

| Service | Vars |
|---|---|
| TqSdk (CN futures + options intraday) | `TQ_USERNAME`, `TQ_PASSWORD` |
| Polygon (US options) | `POLYGON_PROXY_URL`, `POLYGON_PROXY_KEY` |
| Qveris / FMP (data sources) | `QVERIS_API_KEY`, `FMP_API_KEY` |

On WSL, call fetch scripts directly (drop the `_with_creds.sh` prefix):
`uv run python scripts/fetch_tqsdk.py ...` with the env set.

## 5. Run + verify

```bash
cd ~/code/trading/paired-trading/src
uv run pytest -q     # ~504 passed. NOTE: some tests load data/raw + data/options,
                     # so run AFTER data prep; pure-logic tests pass without data.
# smoke a backtest:
uv run python scripts/backtest_full_stack.py --pool CN_BOND
uv run python scripts/backtest_options_attribution.py --underlying ag
```

## 6. Optional: weekly drift-gate cron

`src/scripts/drift_gate.sh` discovers the repo path relative to itself (portable)
but defaults `DERIVED_ROOT`/`MARKET_DATA` to macOS paths — override via env. Add
to WSL cron only if you want the weekly `validate_baselines.py --full` drift check.

## 7. VCS note

Both repos are colocated **jj + git**. `git clone` is sufficient; `jj` is
optional (`jj git init --colocate` inside the clone if you want it). Day-to-day
this project commits with `jj` (`jj describe -m ... && jj new`), not `git`.

---

## Knowledge map — what to read on arrival (priority order)

1. `doc/repro/NEXT_SESSION.md` — the handoff; read this first.
2. `STATUS.md` — current system state (lanes, baselines, infra).
3. `doc/LESSONS.md` — distilled, version-controlled lessons (digest of the
   out-of-repo auto-memory; see §0.2).
4. `doc/repro/*.md` (32 docs) — validated findings, REJECT decisions, repro recipes.
5. `docs/superpowers/specs|plans/*` (8 docs) — designs (baseline-validation,
   PA-TOP, options-attribution).
6. `baselines/*.json` — validated lane artifacts (auditable single source of truth).
7. `CLAUDE.md` — project instructions and conventions.

*(This guide supersedes the prior 2026-06-07 macOS→macOS move record.)*
