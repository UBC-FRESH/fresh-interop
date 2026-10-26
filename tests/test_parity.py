from __future__ import annotations

import pytest

from fresh_interop import (
    TreemunRun,
    build_ws3_problem,
    carbon_coefficients,
    compare,
    economic_coefficients,
    harvest_coefficients,
    selected_policies,
)


def test_economic_parity(run: TreemunRun) -> None:
    result = compare(run, objective="economic")
    assert result.stands == 105
    assert result.relative_delta is not None
    assert result.relative_delta <= 1e-9
    assert result.policy_agreement_fraction is not None
    assert result.policy_agreement_fraction >= 0.95
    assert result.ws3_status == "optimal"


def test_carbon_parity(run: TreemunRun) -> None:
    result = compare(run, objective="carbon")
    assert result.stands == 105
    assert result.relative_delta is not None
    assert result.relative_delta <= 1e-9
    assert result.policy_agreement_fraction is not None
    assert result.policy_agreement_fraction >= 0.95
    assert result.ws3_status == "optimal"


def test_problem_shape_and_assignment(run: TreemunRun) -> None:
    coefficients = economic_coefficients(run)
    problem, mapping = build_ws3_problem(coefficients, name="economic_shape")
    assert len(problem.var_names()) == 780
    assert len(problem.constraint_names()) == 105
    problem.solve(threads=8)
    chosen = selected_policies(problem, mapping["by_stand"])
    assert len(chosen) == 105
    assert set(chosen) == set(run.stands["stand_id"].astype(str))
    assert mapping["provenance"]["even_flow_mode"] == "none"


def test_even_flow_formulation_builds(run: TreemunRun) -> None:
    problem, _mapping = build_ws3_problem(
        economic_coefficients(run),
        name="economic_even_flow",
        harvest=harvest_coefficients(run),
        horizon=30,
        even_flow_mode="two_sided_average",
        even_flow_tolerance=0.10,
    )
    # 105 assignment + 30 harvest tracking + 60 two-sided flow constraints.
    assert len(problem.constraint_names()) == 195
    assert "even_flow_lower_1" in problem.constraint_names()
    assert "even_flow_upper_30" in problem.constraint_names()


def test_carbon_coefficients_match_alternatives(run: TreemunRun) -> None:
    coefficients = carbon_coefficients(run)
    assert len(coefficients) == len(run.alternatives)
    assert all(value >= 0 for value in coefficients.values())


def test_unknown_objective_rejected(run: TreemunRun) -> None:
    with pytest.raises(ValueError):
        compare(run, objective="volume")
