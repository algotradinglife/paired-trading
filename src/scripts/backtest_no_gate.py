"""One-off comparison: run backtest WITHOUT the direction gate, to measure lift."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import patch

from engine.divergence import detector as det_mod

# Replace gate_signals with identity for this run only
with patch.object(det_mod, "gate_signals", lambda x: x):
    from scripts.backtest_signals import main
    sys.exit(main(["--daily", "0.3"]))
