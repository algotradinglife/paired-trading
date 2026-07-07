"""PA / Feitian shared contracts."""

from .contract import (
    PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
    SIGNAL_STATUSES,
    PaFeitianSnapshot,
    PaFeitianSignal,
    load_snapshot,
    snapshot_to_jsonable,
    validate_snapshot,
    write_snapshot,
)
from .scorecard_producer import (
    example_snapshot,
    snapshot_from_scorecard,
    snapshot_from_scorecard_file,
)

__all__ = [
    "PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION",
    "SIGNAL_STATUSES",
    "PaFeitianSnapshot",
    "PaFeitianSignal",
    "example_snapshot",
    "load_snapshot",
    "snapshot_from_scorecard",
    "snapshot_from_scorecard_file",
    "snapshot_to_jsonable",
    "validate_snapshot",
    "write_snapshot",
]
