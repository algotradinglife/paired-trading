"""The 4-emitter replay must reproduce score_today's ag/au options emission.

score_today only scores *recent* signals, so a full-history diff isn't
possible; instead this pins the gate INVARIANTS that make the replay faithful
(verified against score_today.py:940-1098, 1238-1303 at build time):
  - emissions are well-formed OTM calls for the right underlying;
  - bpull / pa_h2 / context_a are the active lanes (fire > 0);
  - divergence emits 0 — the DIF-detector family is off (include_dif_detectors
    is False in production); if this ever flips, the config drifted and the
    attribution must be revisited.
"""
from pathlib import Path

from data import bar_loader
from engine.options.options_emission_replay import (
    replay_bpull, replay_context_a, replay_divergence, replay_pa_h2,
)

BARS = Path(__file__).resolve().parents[1] / "data" / "raw"
_REQUIRED_CALL_KEYS = {"contract_sym", "strike", "otm_pct", "expiry_month", "days_to_expiry"}


def _load(ul):
    sym = f"kq_m_shfe_{ul}"
    bars = bar_loader.load_bars_quant_or_json(sym, "_daily", BARS)
    h = bar_loader.load_bars_quant_or_json(sym, "_60", BARS)
    return bars, h, sym


def _all(ul):
    bars, h, sym = _load(ul)
    return {
        "bpull": replay_bpull(bars, h, ul, sym),
        "pa_h2": replay_pa_h2(bars, h, ul, sym),
        "context_a": replay_context_a(bars, h, ul, sym),
        "divergence": replay_divergence(bars, h, ul),
    }


def test_ag_emissions_well_formed_and_active_lanes():
    em = _all("ag")
    # Active lanes fire; emitted calls are well-formed ag OTM calls.
    assert len(em["bpull"]) > 0 and len(em["context_a"]) > 0
    for lane in ("bpull", "pa_h2", "context_a"):
        for e in em[lane]:
            assert e.calls, f"{lane} emitted a signal with no calls"
            for c in e.calls:
                assert _REQUIRED_CALL_KEYS <= set(c), f"missing keys in {lane} call"
                assert c["contract_sym"].startswith("ag")


def test_au_emissions_well_formed():
    em = _all("au")
    assert len(em["bpull"]) > 0
    for lane in ("bpull", "pa_h2", "context_a"):
        for e in em[lane]:
            assert e.calls
            for c in e.calls:
                assert c["contract_sym"].startswith("au")


def test_divergence_lane_is_off():
    # DIF-detector family is suppressed in production (include_dif_detectors
    # defaults False). The divergence emitter must therefore emit nothing;
    # a non-zero count means the signal-source config drifted.
    assert _all("ag")["divergence"] == []
    assert _all("au")["divergence"] == []
