"""Coefficient-level parity between a Treemün run and ``ws3.opt.Problem``.

This is the core oracle. It does not re-simulate growth in WS3; it takes
Treemün's own per-alternative coefficients and rebuilds the same binary
stand-policy selection problem with the WS3 solver stack.
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass
from typing import Any

from .run import TreemunRun


@dataclass(frozen=True)
class ParityResult:
    """Result of one objective-level comparison."""

    objective: str
    treemun_value: float
    ws3_value: float
    relative_delta: float | None
    stands: int
    policy_agreement: int
    policy_agreement_fraction: float | None
    treemun_status: str | None
    ws3_status: str | None
    treemun_build_solve_seconds: float
    ws3_build_solve_seconds: float
    treemun_raw: dict[str, float | None]


def economic_coefficients(run: TreemunRun) -> dict[tuple[str, str], float]:
    """Return one economic value per stand-policy alternative."""
    return {
        (str(row.stand_id), str(row.policy)): float(row.economic_value)
        for row in run.economics.itertuples(index=False)
    }


def carbon_coefficients(run: TreemunRun) -> dict[tuple[str, str], float]:
    """Return total standing-carbon stock-time per stand-policy alternative."""
    if run.carbon is None:
        return {}
    totals: dict[tuple[str, str], float] = collections.defaultdict(float)
    for row in run.carbon.itertuples(index=False):
        totals[(str(row.stand_id), str(row.policy))] += float(row.carbon_tC_year)
    return dict(totals)


def harvest_coefficients(
    run: TreemunRun,
) -> dict[tuple[int, str, str], float]:
    """Return harvested dry wood per period, stand, and policy."""
    totals: dict[tuple[int, str, str], float] = collections.defaultdict(float)
    for row in run.harvest.itertuples(index=False):
        totals[(int(row.period), str(row.stand_id), str(row.policy))] += float(
            row.dry_wood_t
        )
    return dict(totals)


def build_ws3_problem(
    coefficients: dict[tuple[str, str], float],
    *,
    name: str,
    harvest: dict[tuple[int, str, str], float] | None = None,
    horizon: int | None = None,
    even_flow_mode: str = "none",
    even_flow_tolerance: float = 0.10,
    minimum_ending_dry_wood_t: float | None = None,
    ending_dry_wood: dict[tuple[str, str], float] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Build the binary stand-policy selection MILP with ``ws3.opt.Problem``.

    Args:
        coefficients: Objective coefficient per ``(stand_id, policy)``.
        name: Problem name.
        harvest: Optional harvested dry wood per ``(period, stand_id, policy)``.
            Required when ``even_flow_mode`` is not ``"none"``.
        horizon: Number of annual periods. Required with even-flow.
        even_flow_mode: ``"none"``, ``"two_sided_average"``,
            ``"two_sided_consecutive"``, or ``"nondecreasing"``.
        even_flow_tolerance: Fractional tolerance for the flow constraints.
        minimum_ending_dry_wood_t: Optional lower bound on ending stock.
        ending_dry_wood: Ending stock per ``(stand_id, policy)``. Required when
            ``minimum_ending_dry_wood_t`` is set.

    Returns:
        The ``ws3.opt.Problem`` and a mapping with variable names, the
        stand-to-variables index, and the constraint provenance.
    """
    from ws3 import opt

    if not coefficients:
        raise ValueError("coefficients must not be empty")
    if even_flow_mode not in {
        "none",
        "two_sided_average",
        "two_sided_consecutive",
        "nondecreasing",
    }:
        raise ValueError(f"unsupported even_flow_mode: {even_flow_mode}")
    if even_flow_mode != "none" and (harvest is None or horizon is None):
        raise ValueError("harvest and horizon are required for even-flow")

    problem = opt.Problem(name, sense=opt.SENSE_MAXIMIZE, solver=opt.SOLVER_HIGHS)
    by_stand: dict[str, list[str]] = collections.defaultdict(list)
    for stand, policy in coefficients:
        variable = f"x_{stand}_{policy}"
        problem.add_var(variable, opt.VTYPE_BINARY)
        by_stand[stand].append(variable)

    for stand, variables in by_stand.items():
        problem.add_constraint(
            f"assign_{stand}",
            dict.fromkeys(variables, 1.0),
            "=",
            1.0,
        )

    if minimum_ending_dry_wood_t is not None:
        if ending_dry_wood is None:
            raise ValueError(
                "ending_dry_wood is required when minimum_ending_dry_wood_t is set"
            )
        coeffs = {
            f"x_{stand}_{policy}": float(value)
            for (stand, policy), value in ending_dry_wood.items()
        }
        problem.add_constraint(
            "minimum_ending_dry_wood",
            coeffs,
            ">",
            float(minimum_ending_dry_wood_t),
        )

    provenance: dict[str, Any] = {
        "coefficients": "provided",
        "even_flow_mode": even_flow_mode,
        "even_flow_tolerance": float(even_flow_tolerance),
        "constraints": [],
    }

    if even_flow_mode != "none":
        assert harvest is not None and horizon is not None
        period_coeffs: dict[int, dict[str, float]] = {
            period: {} for period in range(1, int(horizon) + 1)
        }
        for (period, stand, policy), value in harvest.items():
            if period not in period_coeffs:
                continue
            variable = f"x_{stand}_{policy}"
            period_coeffs[period][variable] = (
                period_coeffs[period].get(variable, 0.0) + float(value)
            )

        for period in period_coeffs:
            problem.add_var(f"h_{period}", opt.VTYPE_CONTINUOUS, lb=0.0)
            tracking = {f"h_{period}": 1.0}
            for variable, value in period_coeffs[period].items():
                tracking[variable] = -value
            problem.add_constraint(
                f"harvest_track_{period}", tracking, "=", 0.0
            )
            provenance["constraints"].append(f"harvest_track_{period}")

        tolerance = float(even_flow_tolerance)
        if even_flow_mode == "two_sided_average":
            for period in period_coeffs:
                lower: dict[str, float] = {f"h_{period}": 1.0}
                upper: dict[str, float] = {f"h_{period}": 1.0}
                for other in period_coeffs:
                    lower[f"h_{other}"] = lower.get(f"h_{other}", 0.0) - (
                        (1.0 - tolerance) / int(horizon)
                    )
                    upper[f"h_{other}"] = upper.get(f"h_{other}", 0.0) - (
                        (1.0 + tolerance) / int(horizon)
                    )
                problem.add_constraint(
                    f"even_flow_lower_{period}", lower, ">", 0.0
                )
                problem.add_constraint(
                    f"even_flow_upper_{period}", upper, "<", 0.0
                )
                provenance["constraints"].extend(
                    [f"even_flow_lower_{period}", f"even_flow_upper_{period}"]
                )
        elif even_flow_mode == "nondecreasing":
            for period in range(1, int(horizon)):
                coeffs = {
                    f"h_{period + 1}": 1.0,
                    f"h_{period}": -(1.0 - tolerance),
                }
                problem.add_constraint(
                    f"nondecreasing_{period}", coeffs, ">", 0.0
                )
                provenance["constraints"].append(f"nondecreasing_{period}")
        else:  # two_sided_consecutive
            for period in range(1, int(horizon)):
                lower = {
                    f"h_{period + 1}": 1.0,
                    f"h_{period}": -(1.0 - tolerance),
                }
                upper = {
                    f"h_{period + 1}": 1.0,
                    f"h_{period}": -(1.0 + tolerance),
                }
                problem.add_constraint(
                    f"consecutive_lower_{period}", lower, ">", 0.0
                )
                problem.add_constraint(
                    f"consecutive_upper_{period}", upper, "<", 0.0
                )
                provenance["constraints"].extend(
                    [
                        f"consecutive_lower_{period}",
                        f"consecutive_upper_{period}",
                    ]
                )

    problem.z(
        {
            f"x_{stand}_{policy}": float(value)
            for (stand, policy), value in coefficients.items()
        }
    )
    provenance["variables"] = {
        "stand_policy": len(coefficients),
        "harvest_periods": 0 if even_flow_mode == "none" else int(horizon or 0),
    }
    return problem, {"by_stand": by_stand, "provenance": provenance}


def selected_policies(problem: Any, by_stand: dict[str, list[str]]) -> dict[str, str]:
    """Return the selected policy per stand from a solved problem."""
    solution = problem.solution() or {}
    selected: dict[str, str] = {}
    for stand, variables in by_stand.items():
        variable, value = max(
            ((variable, solution.get(variable, 0.0)) for variable in variables),
            key=lambda item: item[1],
        )
        if float(value) > 0.5:
            selected[stand] = variable[len(f"x_{stand}_") :]
    return selected


def solve_treemun_reference(
    run: TreemunRun,
    *,
    objective: str,
    even_flow_mode: str = "none",
    even_flow_tolerance: float = 0.10,
    solver_name: str = "appsi_highs",
    threads: int = 8,
    relative_gap: float = 0.0,
) -> dict[str, Any]:
    """Solve Treemün's own model for the reference value."""
    import treemun_sim as tm

    options = {
        "policy_summary": run.alternatives.to_dict("records"),
        "ending_dry_wood_by_policy": _ending_map(run),
        "harvested_dry_wood_by_period": {
            (int(period), str(species), str(policy), str(stand)): float(value)
            for (period, species, policy, stand), value in _harvest_map(run).items()
        },
        "carbon_stock_time_by_period": _carbon_map(run),
        "forest": list(run.forests),
        "horizon": int(run.metadata["horizon"]),
        "economic_mode": str(run.metadata["economic_mode"]),
        "economic_parameters": run.metadata["economic_parameters"],
        "discount_rate": float(run.metadata["discount_rate"]),
        "even_flow_mode": even_flow_mode,
        "even_flow_tolerance": float(even_flow_tolerance),
    }
    model = tm.build_forest_management_model(**options, objective=objective)
    results = tm.solve_model(
        model,
        solver_name,
        relative_gap=relative_gap,
        threads=threads,
    )
    return tm.extract_solution(model, results)


def compare(
    run: TreemunRun,
    *,
    objective: str,
    even_flow_mode: str = "none",
    even_flow_tolerance: float = 0.10,
    solver_name: str = "appsi_highs",
    threads: int = 8,
    relative_gap: float = 0.0,
) -> ParityResult:
    """Solve both formulations and compare objective, policies, and timing."""
    if objective == "economic":
        coefficients = economic_coefficients(run)
    elif objective == "carbon":
        coefficients = carbon_coefficients(run)
    else:
        raise ValueError("objective must be 'economic' or 'carbon'")

    started = time.perf_counter()
    reference = solve_treemun_reference(
        run,
        objective=objective,
        even_flow_mode=even_flow_mode,
        even_flow_tolerance=even_flow_tolerance,
        solver_name=solver_name,
        threads=threads,
        relative_gap=relative_gap,
    )
    treemun_seconds = time.perf_counter() - started

    started = time.perf_counter()
    problem, mapping = build_ws3_problem(
        coefficients,
        name=f"treemun_{objective}_parity",
        harvest=harvest_coefficients(run),
        horizon=int(run.metadata["horizon"]),
        even_flow_mode=even_flow_mode,
        even_flow_tolerance=even_flow_tolerance,
    )
    problem.solve(threads=threads)
    ws3_seconds = time.perf_counter() - started

    treemun_value = (
        float(reference["economic_value"])
        if objective == "economic"
        else float(reference["carbon_stock_time_tC_year"])
    )
    ws3_value = float(problem.z() or 0.0)
    treemun_selected = {
        str(row["stand_id"]): str(row["policy"])
        for row in reference["selected_policies"].to_dict("records")
    }
    ws3_selected = selected_policies(problem, mapping["by_stand"])
    agreement = sum(
        1
        for stand in ws3_selected
        if ws3_selected[stand] == treemun_selected.get(stand)
    )

    return ParityResult(
        objective=objective,
        treemun_value=treemun_value,
        ws3_value=ws3_value,
        relative_delta=abs(ws3_value - treemun_value) / abs(treemun_value)
        if treemun_value
        else None,
        stands=len(ws3_selected),
        policy_agreement=agreement,
        policy_agreement_fraction=agreement / len(ws3_selected)
        if ws3_selected
        else None,
        treemun_status=str(reference.get("solver_name")),
        ws3_status=problem.status(),
        treemun_build_solve_seconds=treemun_seconds,
        ws3_build_solve_seconds=ws3_seconds,
        treemun_raw={
            "economic_value": float(reference["economic_value"]),
            "carbon_stock_time_tC_year": float(
                reference["carbon_stock_time_tC_year"]
            ),
            "ending_dry_wood_t": float(reference["ending_dry_wood_t"]),
        },
    )


def _ending_map(run: TreemunRun) -> dict[tuple[str, str], float]:
    return dict(run.ending_dry_wood)


def _harvest_map(
    run: TreemunRun,
) -> dict[tuple[int, str, str, str], float]:
    return {
        (
            int(row.period),
            str(row.species),
            str(row.policy),
            str(row.stand_id),
        ): float(row.dry_wood_t)
        for row in run.harvest.itertuples(index=False)
    }


def _carbon_map(
    run: TreemunRun,
) -> dict[tuple[int, str, str, str], float] | None:
    if run.carbon is None:
        return None
    return {
        (
            int(row.period),
            str(row.species),
            str(row.policy),
            str(row.stand_id),
        ): float(row.carbon_tC_year)
        for row in run.carbon.itertuples(index=False)
    }
