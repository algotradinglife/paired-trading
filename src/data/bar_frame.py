"""BarFrame + ProvenanceManifest — the unified OHLCV container with
strict period_end timestamp semantics and lineage metadata
(architecture v0.3 §6.2, §6.3, §14.1 / §14.2).

Why a wrapper around pd.DataFrame:
  1. Three multi-TF look-ahead leaks in 48h had a common root: each
     script independently decided how to interpret bar timestamps.
     BarFrame centralizes that decision (period_end always) so the
     leak class can't recur per-caller.
  2. Provenance has to be carried alongside the data — caching, audit,
     and replay all depend on knowing the exact input version that
     produced an artifact. With a bare DataFrame this info is lost the
     moment someone calls `.copy()`.
  3. The frozen dataclass + validator pattern matches the project
     convention (DivergenceSignal, PolicyDecision, ExhaustionEvent).

Stability promise: BarFrame and ProvenanceManifest are the contract
between data layer (Step 0/3) and derivations layer (Step 4). Adding
fields is non-breaking; changing existing field semantics requires a
version bump on the manifest schema.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Iterable

import pandas as pd

# Used by UTC-strict offset comparison.
_ZERO_OFFSET = timedelta(0)

# Manifest schema version. Bump on breaking changes; additive fields
# don't require a bump (consumers tolerate unknown keys).
MANIFEST_SCHEMA_VERSION = "1.0"


REQUIRED_COLUMNS: tuple[str, ...] = ("timestamp", "open", "high", "low", "close")
OPTIONAL_COLUMNS: tuple[str, ...] = ("volume", "open_interest")


@dataclass(frozen=True)
class ProvenanceManifest:
    """JSON-serializable lineage record (architecture v0.3 §6.3).

    One manifest is attached to every cached artifact, INCLUDING raw
    bars (codex M1 fix in v0.2: lineage tree must not start at an
    unversioned root).

    Stored alongside the payload file: a parquet at
    `data/cache/bars/spy-D-...parquet` has a sibling
    `data/cache/bars/spy-D-...manifest.json`.
    """

    artifact_id: str               # globally unique; matches payload filename stem
    artifact_type: str             # "bars" / "derivations.macd" / "detector.exhaustion" / ...
    created_at: datetime
    # Payload (file we describe). For BarFrame this is the parquet of df.
    payload_path: str              # path relative to repo root
    payload_hash: str              # sha256 of the parquet file
    row_range_start: datetime
    row_range_end: datetime
    row_count: int
    # Lineage. For raw bars `inputs=[]` — they are roots.
    inputs: tuple["ManifestInput", ...] = ()
    # Params used to produce the artifact (provider query params,
    # derivation hyperparams, etc).
    params: dict[str, Any] = field(default_factory=dict)
    # Code provenance — protects against accidental dirty-worktree
    # outputs leaking into "validated" runs.
    git_sha: str = ""
    dirty_worktree: bool = False
    package_versions: dict[str, str] = field(default_factory=dict)
    # Data-source metadata (mainly for raw-bar manifests, but anything
    # downstream is welcome to carry these too).
    provider: str = ""
    symbol: str = ""
    level: str = ""
    exchange: str = ""
    calendar_version: str = ""
    stamp_convention: str = "period_end"
    adjustment_mode: str = ""
    session_policy: str = ""
    source_query: str = ""
    as_of: datetime | None = None
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "created_at": self.created_at.isoformat(),
            "payload": {
                "path": self.payload_path,
                "hash": self.payload_hash,
                "row_range": {
                    "start": self.row_range_start.isoformat(),
                    "end": self.row_range_end.isoformat(),
                },
                "row_count": self.row_count,
            },
            "inputs": [i.to_dict() for i in self.inputs],
            "params": dict(self.params),
            "code": {
                "git_sha": self.git_sha,
                "dirty_worktree": self.dirty_worktree,
                "package_versions": dict(self.package_versions),
            },
            "data_metadata": {
                "provider": self.provider,
                "symbol": self.symbol,
                "level": self.level,
                "exchange": self.exchange,
                "calendar_version": self.calendar_version,
                "stamp_convention": self.stamp_convention,
                "adjustment_mode": self.adjustment_mode,
                "session_policy": self.session_policy,
                "source_query": self.source_query,
                "as_of": self.as_of.isoformat() if self.as_of else None,
            },
            "schema_version": self.schema_version,
        }
        return d

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass(frozen=True)
class ManifestInput:
    """A pointer to a parent artifact in the lineage chain."""

    artifact_id: str
    hash: str  # the parent artifact's payload_hash

    def to_dict(self) -> dict[str, str]:
        return {"artifact_id": self.artifact_id, "hash": self.hash}


@dataclass(frozen=True)
class BarFrame:
    """Causal OHLCV container with period_end timestamps and provenance.

    See module docstring for design rationale. Field reference matches
    architecture v0.3 §6.2.

    Mutability contract: BarFrame is conceptually immutable. Construction
    takes a defensive copy AND freezes the underlying numpy arrays where
    possible. Callers MUST treat `bf.df` as read-only — any mutation
    bypasses validation and renders payload_hash / manifest stale.
    Mutating bf.df is undefined behavior, and a Step 2 lint rule will
    flag in-tree mutations of BarFrame.df.
    """

    df: pd.DataFrame
    provider: str          # "polygon" / "qveris" / "tqsdk"
    symbol: str            # uppercase ticker for equities; underlying code for futures
    level: str             # "D" / "1h" / "15m" / "5m" / "W"
    exchange: str          # "XNYS" / "XSHG" / ...
    calendar_version: str  # full str like "exchange_calendars==4.13.2+XNYS"
    adjustment_mode: str   # "split_only" / "total" / "none"
    session_policy: str    # "regular" / "regular+extended" / "regular+night"
    source_query: str      # provider-specific query / file path for replay
    as_of: datetime        # when this snapshot was pulled
    last_completed_ts: datetime  # period_end of last fully-closed bar
    payload_hash: str      # sha256 of canonical bytes representation

    # All BarFrames stamp this way — kept as field for explicitness so
    # serialized manifest is self-describing and so a future migration
    # period (where we want to accept "period_start" inputs) can flip
    # it intentionally rather than by accident.
    stamp_convention: str = "period_end"

    def __post_init__(self) -> None:
        self._validate_df()
        self._validate_metadata()
        # Codex P2 (2026-05-28 round 4): defensive copy so the BarFrame's
        # internal data is decoupled from the caller's original frame.
        # object.__setattr__ is the standard escape hatch for frozen
        # dataclass init.
        df_copy = self.df.copy()
        # Codex P2 (round 5): also freeze the underlying numpy arrays
        # so casual mutations like `bf.df.values[0, 0] = 999` raise
        # ValueError at write time. This is best-effort — `bf.df.loc[..., ...]`
        # may still trigger a copy-on-write under pandas 3.x's CoW
        # default and silently bypass freeze. The contract is documented
        # explicitly in the class docstring; a Step 2 lint rule will
        # flag in-tree mutation patterns.
        for col in df_copy.columns:
            try:
                df_copy[col].values.setflags(write=False)
            except (AttributeError, ValueError):
                pass  # extension dtypes (e.g. datetime64 tz) ignore freeze
        object.__setattr__(self, "df", df_copy)

    # ---- validators ----

    def _validate_df(self) -> None:
        df = self.df
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"df must be a pandas DataFrame, got {type(df).__name__}")

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"BarFrame missing required columns: {missing}")

        # timestamp must be tz-aware UTC datetime64
        ts = df["timestamp"]
        if not pd.api.types.is_datetime64_any_dtype(ts):
            raise TypeError("BarFrame.df.timestamp must be datetime64; got "
                            f"{ts.dtype}")
        tz = getattr(ts.dt, "tz", None)
        if tz is None:
            raise ValueError("BarFrame.df.timestamp must be tz-aware (UTC)")
        # Codex P3 (2026-05-28 round 6): accept any tz object whose
        # actual offset is zero, instead of a fragile string allowlist.
        # exchange_calendars / pandas / dateutil all may return
        # different repr for "UTC" depending on path.
        try:
            offset = tz.utcoffset(None)  # type: ignore[union-attr]
        except (TypeError, ValueError):
            # Some tz implementations need a concrete datetime.
            offset = ts.iloc[0].utcoffset() if len(ts) else None
        if offset != _ZERO_OFFSET:
            raise ValueError(
                f"BarFrame.df.timestamp must be UTC (zero offset); got "
                f"tz={tz!r} with offset={offset}. Loaders are responsible "
                f"for normalization."
            )

        # Monotone non-decreasing.
        if not ts.is_monotonic_increasing:
            raise ValueError(
                "BarFrame.df.timestamp must be monotonically increasing "
                "(loader must sort)."
            )

        # No duplicate timestamps.
        if ts.duplicated().any():
            n_dupe = int(ts.duplicated().sum())
            raise ValueError(f"BarFrame.df has {n_dupe} duplicate timestamps")

        # Codex P2 (2026-05-28 round 2): JSON/CSV inputs sometimes
        # pass price fields as object/string dtype; the inequality
        # checks below would then do lexicographic comparison and
        # corrupt MACD downstream. Require numeric dtypes for required
        # price columns.
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise TypeError(
                    f"BarFrame.df.{col} must be numeric dtype; got "
                    f"{df[col].dtype}. Loader must coerce before "
                    f"construction."
                )

        # Codex P2 (2026-05-28): NaN in OHLC bypasses the inequality
        # checks below (NaN < x is False), so we must reject any null
        # value in required price columns BEFORE the OHLC sanity check.
        # Otherwise downstream MACD / label code reads NaN as if it
        # were valid price data.
        null_counts = {c: int(df[c].isna().sum()) for c in price_cols
                       if df[c].isna().any()}
        if null_counts:
            raise ValueError(
                f"BarFrame has null values in required price columns: "
                f"{null_counts}"
            )

        # OHLC sanity: high >= max(open, close), low <= min(open, close).
        bad_high = (df["high"] < df[["open", "close"]].max(axis=1)).sum()
        bad_low = (df["low"] > df[["open", "close"]].min(axis=1)).sum()
        if bad_high or bad_low:
            raise ValueError(
                f"OHLC inconsistency: {int(bad_high)} bars with high < "
                f"max(open, close); {int(bad_low)} bars with low > "
                f"min(open, close)"
            )

        # Volume non-negative if present.
        if "volume" in df.columns:
            if (df["volume"].fillna(0) < 0).any():
                raise ValueError("BarFrame has negative volume rows")

        # Strict column allowlist — flag unexpected columns so we don't
        # silently carry leaky fields like a "raw_period_start" extra.
        unexpected = [c for c in df.columns
                      if c not in REQUIRED_COLUMNS and c not in OPTIONAL_COLUMNS]
        if unexpected:
            raise ValueError(
                f"BarFrame.df has unexpected columns: {unexpected}. "
                f"Allowed: {REQUIRED_COLUMNS + OPTIONAL_COLUMNS}."
            )

    def _validate_metadata(self) -> None:
        if self.stamp_convention != "period_end":
            raise ValueError(
                f"stamp_convention must be 'period_end'; got "
                f"{self.stamp_convention!r}. Loaders are responsible for "
                f"normalizing any period_start input."
            )
        if not self.provider:
            raise ValueError("BarFrame.provider is required")
        if not self.symbol:
            raise ValueError("BarFrame.symbol is required")
        if not self.level:
            raise ValueError("BarFrame.level is required")
        if not self.exchange:
            raise ValueError("BarFrame.exchange is required")
        if not self.calendar_version:
            raise ValueError("BarFrame.calendar_version is required")
        # Codex P3 (2026-05-28 round 5): UTC explicitly. Offset-aware
        # but non-UTC values would round-trip differently in manifests
        # and break cache keys / consumer comparisons.
        if self.as_of.tzinfo is None:
            raise ValueError("BarFrame.as_of must be tz-aware (UTC)")
        if self.as_of.utcoffset() != _ZERO_OFFSET:
            raise ValueError(
                f"BarFrame.as_of must be UTC; got offset "
                f"{self.as_of.utcoffset()}"
            )
        if self.last_completed_ts.tzinfo is None:
            raise ValueError("BarFrame.last_completed_ts must be tz-aware (UTC)")
        if self.last_completed_ts.utcoffset() != _ZERO_OFFSET:
            raise ValueError(
                f"BarFrame.last_completed_ts must be UTC; got offset "
                f"{self.last_completed_ts.utcoffset()}"
            )
        # Codex P3 (2026-05-28): not just prefix — require full 64-hex
        # body so a malformed value like 'sha256:x' can't enter the
        # provenance chain as a trusted lineage hash.
        if not self.payload_hash.startswith("sha256:"):
            raise ValueError(
                f"BarFrame.payload_hash must be a sha256: prefixed digest; "
                f"got {self.payload_hash!r}"
            )
        hex_body = self.payload_hash[len("sha256:"):]
        if len(hex_body) != 64 or not all(c in "0123456789abcdef" for c in hex_body):
            raise ValueError(
                f"BarFrame.payload_hash digest body must be 64 lowercase "
                f"hex characters; got body={hex_body!r}"
            )

        # Consistency: last_completed_ts must match df's last timestamp.
        if len(self.df) > 0:
            last_df = self.df["timestamp"].iloc[-1]
            # tz-aware comparison; coerce both to UTC pd.Timestamp.
            last_df_ts = pd.Timestamp(last_df).tz_convert("UTC").to_pydatetime()
            last_field = pd.Timestamp(self.last_completed_ts).tz_convert(
                "UTC").to_pydatetime()
            if last_df_ts != last_field:
                raise ValueError(
                    f"last_completed_ts {last_field!r} does not match df's "
                    f"last bar timestamp {last_df_ts!r}"
                )
            # Codex P2 (2026-05-28): central look-ahead guardrail. The
            # polygon loader filters mid-session bars out, but any future
            # loader (qveris/tqsdk) could fail to. Reject at the contract
            # level so the leak class is impossible to reintroduce by a
            # well-formed caller.
            as_of_utc = pd.Timestamp(self.as_of).tz_convert("UTC").to_pydatetime()
            if last_df_ts > as_of_utc:
                raise ValueError(
                    f"BarFrame would expose an unclosed bar: last bar's "
                    f"period_end {last_df_ts!r} is after as_of {as_of_utc!r}. "
                    f"Loader must filter mid-session bars before construction."
                )

    # ---- convenience ----

    def __len__(self) -> int:
        return len(self.df)

    def manifest(
        self,
        *,
        artifact_id: str,
        payload_path: str,
        created_at: datetime,
        git_sha: str = "",
        dirty_worktree: bool = False,
        package_versions: dict[str, str] | None = None,
        inputs: Iterable[ManifestInput] = (),
        params: dict[str, Any] | None = None,
    ) -> ProvenanceManifest:
        """Return a ProvenanceManifest describing this BarFrame.

        BarFrame doesn't decide where to persist itself (that's the
        cache layer's job in Step 4). It only knows the inputs to the
        manifest. Caller supplies artifact_id + payload_path after
        deciding where the parquet lives.
        """
        if len(self.df) == 0:
            raise ValueError("Cannot build a manifest from an empty BarFrame")

        return ProvenanceManifest(
            artifact_id=artifact_id,
            artifact_type="bars",
            created_at=created_at,
            payload_path=payload_path,
            payload_hash=self.payload_hash,
            row_range_start=pd.Timestamp(self.df["timestamp"].iloc[0])
                .tz_convert("UTC").to_pydatetime(),
            row_range_end=pd.Timestamp(self.df["timestamp"].iloc[-1])
                .tz_convert("UTC").to_pydatetime(),
            row_count=len(self.df),
            inputs=tuple(inputs),
            params=params or {},
            git_sha=git_sha,
            dirty_worktree=dirty_worktree,
            package_versions=package_versions or {},
            provider=self.provider,
            symbol=self.symbol,
            level=self.level,
            exchange=self.exchange,
            calendar_version=self.calendar_version,
            stamp_convention=self.stamp_convention,
            adjustment_mode=self.adjustment_mode,
            session_policy=self.session_policy,
            source_query=self.source_query,
            as_of=self.as_of,
        )

    def with_df(self, new_df: pd.DataFrame, *, new_payload_hash: str) -> "BarFrame":
        """Return a copy with a different df — used by derivations that
        produce slices (e.g. a ForeignTFView.last_n() helper). Must
        provide an updated payload_hash so the new BarFrame's lineage
        is distinct from its parent."""
        new_last = pd.Timestamp(new_df["timestamp"].iloc[-1]).tz_convert(
            "UTC").to_pydatetime() if len(new_df) else self.last_completed_ts
        return replace(self, df=new_df, payload_hash=new_payload_hash,
                       last_completed_ts=new_last)


# ---------------------------------------------------------------------------
# Helpers exported for loaders.
# ---------------------------------------------------------------------------

def canonical_payload_hash(df: pd.DataFrame) -> str:
    """sha256 of a canonical byte representation of the DataFrame.

    Used for BarFrame.payload_hash before the bytes are written to
    parquet. Canonical = sorted columns + UTF-8 + microsecond timestamps.
    """
    cols = sorted(df.columns)
    canonical = df[cols].copy()
    # Convert datetimes to ISO strings for stable hashing.
    if "timestamp" in canonical.columns:
        canonical["timestamp"] = canonical["timestamp"].dt.tz_convert(
            "UTC").astype("string")
    blob = canonical.to_csv(index=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()
