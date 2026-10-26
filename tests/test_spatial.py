from __future__ import annotations

from fresh_interop import (
    TreemunRun,
    adjacency_edges,
    edge_stand_ids,
    greenup_conflicts,
    pairs_to_constraint_sets,
    solve_treemun_reference,
    treemun_adjacency_to_ws3_pairs,
)


def test_adjacency_edge_contract(run: TreemunRun, geometry_file) -> None:
    edges = adjacency_edges(geometry_file)
    assert list(edges.columns) == [
        "stand_id_a",
        "stand_id_b",
        "shared_boundary_length",
    ]
    assert len(edges) == 215
    assert edges["shared_boundary_length"].gt(0).all()
    assert edge_stand_ids(edges) <= set(run.stands["stand_id"].astype(str))


def test_pair_conversion_is_unique(run: TreemunRun, geometry_file) -> None:
    edges = adjacency_edges(geometry_file)
    pairs = treemun_adjacency_to_ws3_pairs(edges)
    weighted = treemun_adjacency_to_ws3_pairs(edges, keep_weights=True)

    assert len(pairs) == 215
    assert len(weighted) == 215
    assert len({frozenset(pair) for pair in pairs}) == 215
    assert all(len(item) == 2 for item in pairs)
    assert all(len(item) == 3 for item in weighted)

    neighbours = pairs_to_constraint_sets(pairs)
    assert len(neighbours) == 105
    assert sum(len(values) for values in neighbours.values()) == 2 * 215


def test_greenup_conflict_count(run: TreemunRun, geometry_file) -> None:
    edges = adjacency_edges(geometry_file)
    solution = solve_treemun_reference(run, objective="economic")
    conflicts = greenup_conflicts(
        run,
        solution["selected_policies"],
        edges,
        greenup_window=2,
    )
    assert len(conflicts) == 200
    assert {
        "stand_id_a",
        "stand_id_b",
        "period_a",
        "period_b",
        "period_distance",
        "shared_boundary_length",
    } <= set(conflicts.columns)
