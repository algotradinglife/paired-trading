"""Level topology — adjacency and recursive relationships among timeframes.

Reference: doc/08-multitimeframe-fusion.md §1
           doc/04-feature-extraction.md §4 (time level约定)
"""

from __future__ import annotations

from dataclasses import dataclass

# Standard level ordering for assets. Smaller (faster) → larger (slower).
# Two profiles per doc/02 §1.1.

LEVELS_CRYPTO_24H = [
    "1m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "12h",
    "D", "3D", "W", "2W", "M", "Q", "6M",
]

LEVELS_US_STOCK = [
    "5m", "15m", "30m",
    "1h", "2h",
    "D", "2D", "3D",
    "W", "2W",
    "M", "2M", "Q", "6M", "Y",
]

LEVELS_A_STOCK = LEVELS_US_STOCK   # same gap pattern (skips 6h/12h)


@dataclass(frozen=True)
class LevelTopology:
    """Ordered list of supported time levels for a market profile.

    Methods provide:
      - `direct_children_of(L)`  — all levels smaller than L (集合, unordered set)
      - `nesting_chain_of(L)`    — recursive chain L → max-sub → max-sub-of-sub → ...
      - `sub_of(L)` / `super_of(L)` — adjacent levels in the ordering
    """

    levels: tuple[str, ...]

    def __post_init__(self):
        # Validate no duplicates
        if len(self.levels) != len(set(self.levels)):
            raise ValueError(f"Duplicate levels in topology: {self.levels}")

    def has(self, level: str) -> bool:
        return level in self.levels

    def index_of(self, level: str) -> int:
        try:
            return self.levels.index(level)
        except ValueError as e:
            raise ValueError(f"Level {level!r} not in topology {self.levels}") from e

    def direct_children_of(self, level: str) -> list[str]:
        """All levels strictly smaller than `level` — unordered集合 by convention.

        Used by启动判定 — "all direct children must complete底部 调整".
        """
        idx = self.index_of(level)
        return list(self.levels[:idx])

    def nesting_chain_of(self, level: str) -> list[str]:
        """Recursive chain from `level` down to the smallest, via 'max sub' each step.

        Since our level list is linearly ordered, the "max sub" at each step
        is simply the immediate predecessor. So the chain is just the prefix
        of `levels` up to `level`, reversed.

        Used by顶部判定 — "main level tops when the chain's smallest level
        finishes its rebound".
        """
        idx = self.index_of(level)
        # [level, level-1, level-2, ..., smallest]
        return list(reversed(self.levels[: idx + 1]))

    def sub_of(self, level: str) -> str | None:
        """Immediate smaller level, or None if `level` is the smallest."""
        idx = self.index_of(level)
        return self.levels[idx - 1] if idx > 0 else None

    def super_of(self, level: str) -> str | None:
        """Immediate larger level, or None if `level` is the largest."""
        idx = self.index_of(level)
        return self.levels[idx + 1] if idx + 1 < len(self.levels) else None

    def restrict_to(self, available: list[str]) -> LevelTopology:
        """Return a new topology containing only the levels in `available`,
        preserving the original ordering.

        Useful when the data source only provides a subset of levels and you
        want sub/super to refer to the next *available* level in that subset.
        """
        kept = tuple(L for L in self.levels if L in available)
        return LevelTopology(levels=kept)


# Convenience factories
def topology_for_crypto() -> LevelTopology:
    return LevelTopology(levels=tuple(LEVELS_CRYPTO_24H))


def topology_for_us_stock() -> LevelTopology:
    return LevelTopology(levels=tuple(LEVELS_US_STOCK))


def topology_for_a_stock() -> LevelTopology:
    return LevelTopology(levels=tuple(LEVELS_A_STOCK))
