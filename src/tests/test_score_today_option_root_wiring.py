"""score_today ag/au option data roots are forwarded into selector/enrichment."""
from __future__ import annotations

from argparse import Namespace
from datetime import date

import scripts.score_today as score_today


def test_ag_option_helper_forwards_quant_root_and_legacy_json_dir(monkeypatch, tmp_path):
    quant_root = tmp_path / "quant"
    json_dir = tmp_path / "options" / "ag"
    args = Namespace(quant_data_root=quant_root, ag_options_data_dir=json_dir)
    seen: dict[str, tuple] = {}

    def fake_select(
        underlying_price,
        signal_date,
        n_strikes=3,
        mm_target_pct=None,
        *,
        quant_root=None,
    ):
        seen["select"] = (
            underlying_price,
            signal_date,
            n_strikes,
            mm_target_pct,
            quant_root,
        )
        return [{"contract_sym": "ag2608c10000", "strike": 10000, "days_to_expiry": 30}]

    def fake_enrich(calls, signal_date, underlying_price, data_dir, *, quant_root=None):
        seen["enrich"] = (calls, signal_date, underlying_price, data_dir, quant_root)
        calls[0]["price_source"] = "store"
        return calls

    monkeypatch.setattr(score_today, "select_otm_calls", fake_select)
    monkeypatch.setattr(score_today, "enrich_with_iv", fake_enrich)

    calls = score_today._select_enriched_ag_calls(
        9000.0,
        date(2026, 7, 10),
        args,
        mm_target_pct=2.5,
    )

    assert calls[0]["price_source"] == "store"
    assert seen["select"] == (9000.0, date(2026, 7, 10), 3, 2.5, quant_root)
    assert seen["enrich"] == (calls, date(2026, 7, 10), 9000.0, json_dir, quant_root)


def test_au_option_helper_forwards_quant_root_and_legacy_json_dir(monkeypatch, tmp_path):
    quant_root = tmp_path / "quant"
    json_dir = tmp_path / "options" / "au"
    args = Namespace(quant_data_root=quant_root, au_options_data_dir=json_dir)
    seen: dict[str, tuple] = {}

    def fake_select(
        underlying_price,
        signal_date,
        n_strikes=3,
        mm_target_pct=None,
        *,
        quant_root=None,
    ):
        seen["select"] = (
            underlying_price,
            signal_date,
            n_strikes,
            mm_target_pct,
            quant_root,
        )
        return [{"contract_sym": "au2608c800", "strike": 800, "days_to_expiry": 30}]

    def fake_enrich(calls, signal_date, underlying_price, data_dir, *, quant_root=None):
        seen["enrich"] = (calls, signal_date, underlying_price, data_dir, quant_root)
        calls[0]["price_source"] = "store"
        return calls

    monkeypatch.setattr(score_today, "select_otm_calls_au", fake_select)
    monkeypatch.setattr(score_today, "enrich_with_iv_au", fake_enrich)

    calls = score_today._select_enriched_au_calls(
        700.0,
        date(2026, 7, 10),
        args,
        mm_target_pct=1.8,
    )

    assert calls[0]["price_source"] == "store"
    assert seen["select"] == (700.0, date(2026, 7, 10), 3, 1.8, quant_root)
    assert seen["enrich"] == (calls, date(2026, 7, 10), 700.0, json_dir, quant_root)
