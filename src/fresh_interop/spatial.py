"""Spatial helpers used by the parity harness.

The heavy polygons stay in Treemün/GeoPandas; this module only converts the
resulting edge table into the stand-pair vocabulary that WS3 constraints use.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from .run import TreemunRun

EDGE_COLUMNS = ("stand_id_a", "stand_id_b", "shared_boundary_length")


def adjacency_edges(
    geometry_file: str | Path,
    *,
    stand_id_column: str = "stand_id",
    minimum_shared_boundary: float = 0.0,
) -> pd.DataFrame:
    """Build adjacency edges from a projected GeoPackage or Shapefile.

    This is a thin wrapper around Treemün so the optional dependency stays in
    one place.
    """
    import treemun_sim as tm

    return tm.build_adjacency_edges(
        str(geometry_file),
        stand_id_column=stand_id_column,
        minimum_shared_boundary=minimum_shared_boundary,
    )


def treemun_adjacency_to_ws3_pairs(
    edges: pd.DataFrame,
    *,
    keep_weights: bool = False,
) -> list[tuple[str, str]] | list[tuple[str, str, float]]:
    """Convert an edge table to unique unordered stand pairs.

    Args:
        edges: DataFrame with ``stand_id_a``, ``stand_id_b``, and
            ``shared_boundary_length``.
        keep_weights: Include the shared-boundary length as a third element.

    Returns:
        A list of ``(stand_a, stand_b)`` tuples, or
        ``(stand_a, stand_b, weight)`` when ``keep_weights`` is true.
    """
    missing = set(EDGE_COLUMNS) - set(edges.columns)
    if missing:
        raise ValueError(f"edges is missing columns: {sorted(missing)}")

    seen: set[frozenset[str]] = set()
    pairs: list[tuple[str, str]] | list[tuple[str, str, float]] = []
    for row in edges.itertuples(index=False):
        left = str(row.stand_id_a)
        right = str(row.stand_id_b)
        if left == right:
            continue
        key = frozenset((left, right))
        if key in seen:
            continue
        seen.add(key)
        if keep_weights:
            pairs.append((left, right, float(row.shared_boundary_length)))
        else:
            pairs.append((left, right))
    return pairs


def greenup_conflicts(
    run: TreemunRun,
    selected_policies: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    greenup_window: int = 2,
) -> pd.DataFrame:
    """List realized green-up conflicts for a selected plan.

    Args:
        run: Normalized Treemün run (supplies the trajectories).
        selected_policies: One row per stand with ``stand_id`` and ``policy``.
        edges: Adjacency edge table.
        greenup_window: Maximum allowed period distance between adjacent final
            harvests before the pair counts as a conflict.
    """
    import treemun_sim as tm

    return tm.count_greenup_event_conflicts(
        selected_policies=selected_policies,
        forest=list(run.forests),
        adjacency_edges=edges,
        greenup_window=int(greenup_window),
    )


def edge_stand_ids(edges: pd.DataFrame) -> set[str]:
    """Return the set of stand ids referenced by an edge table."""
    missing = set(EDGE_COLUMNS) - set(edges.columns)
    if missing:
        raise ValueError(f"edges is missing columns: {sorted(missing)}")
    ids: set[str] = set()
    for left, right in edges[["stand_id_a", "stand_id_b"]].itertuples(index=False):
        ids.add(str(left))
        ids.add(str(right))
    return ids


def pairs_to_constraint_sets(
    pairs: Iterable[tuple[str, str]],
) -> dict[str, set[str]]:
    """Group adjacency pairs by stand for a WS3 pairwise constraint loop."""
    neighbours: dict[str, set[str]] = {}
    for left, right in pairs:
        neighbours.setdefault(left, set()).add(right)
        neighbours.setdefault(right, set()).add(left)
    return neighbours
