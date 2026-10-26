"""Load and normalize a Treemün run into a frozen contract.

The purpose of this module is to isolate the optional upstream dependency. No
other module in :mod:`fresh_interop` imports ``treemun_sim`` at import time.
"""

from __future__ import annotations

import hashlib
import platform
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Illustrative 2025 USD values from the Treemün README / paper Table B.3.
# They are scenario inputs, not recommendations. Any real comparison should
# pass its own ``economic_parameters``.
ILLUSTRATIVE_ECONOMICS: dict[str, Any] = {
    "revenue_per_dry_t": {"Pinus radiata": 44.07, "Eucalyptus globulus": 43.66},
    "transport_cost_per_dry_t": {"Pinus radiata": 15.76, "Eucalyptus globulus": 10.59},
    "thinning_cost_per_dry_t": {"Pinus radiata": 11.03, "Eucalyptus globulus": 0.0},
    "final_harvest_cost_per_dry_t": {"Pinus radiata": 12.61, "Eucalyptus globulus": 8.47},
    "replanting_cost_per_ha": {"Pinus radiata": 684.0, "Eucalyptus globulus": 716.0},
    "annual_management_cost_per_ha": 15.0,
    "terminal_value_per_dry_t": {"Pinus radiata": 7.85, "Eucalyptus globulus": 12.30},
}

PACKAGE_NAME = "treemun-sim"


@dataclass(frozen=True)
class TreemunRun:
    """Normalized Treemün outputs.

    Attributes:
        stands: Original stand table, one row per stand.
        alternatives: One row per feasible stand-policy alternative.
        harvest: Long table with ``period``, ``stand_id``, ``policy``,
            ``species``, and ``dry_wood_t``.
        carbon: Long table with the same keys plus ``carbon_tC_year``, or
            ``None`` when carbon accounting was not requested.
        economics: One row per stand-policy from
            ``EconomicEvaluation.summary_by_policy``.
        ending_dry_wood: Ending dry wood per ``(stand_id, policy)``.
        forests: The raw trajectory tables returned by Treemün.
        metadata: Provenance, units, versions, and hashes.
    """

    stands: pd.DataFrame
    alternatives: pd.DataFrame
    harvest: pd.DataFrame
    carbon: pd.DataFrame | None
    economics: pd.DataFrame
    ending_dry_wood: dict[tuple[str, str], float]
    forests: tuple[pd.DataFrame, ...]
    metadata: dict[str, Any]


def sha256(path: str | Path) -> str:
    """Return the SHA256 of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _upstream_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "unknown"


def load_treemun_run(
    stands_file: str | Path,
    *,
    horizon: int = 30,
    economic_mode: str = "detailed_cash_flow",
    economic_parameters: Mapping[str, object] | None = None,
    discount_rate: float = 0.08,
    include_carbon: bool = True,
    pinus_policies: Sequence[tuple[int, int]] | None = None,
    eucalyptus_policies: Sequence[tuple[int]] | None = None,
    lookup_table_file: str | Path | None = None,
    carbon_parameters: Mapping[str, object] | None = None,
) -> TreemunRun:
    """Run Treemün and normalize the four- or five-object return.

    Args:
        stands_file: CSV with one row per stand.
        horizon: Planning horizon in years (annual periods).
        economic_mode: Treemün economic mode.
        economic_parameters: Price and cost inputs. Defaults to
            :data:`ILLUSTRATIVE_ECONOMICS`, and the metadata records that.
        discount_rate: Discount rate for the detailed cash-flow mode.
        include_carbon: Compute carbon trajectories and stock-time.
        pinus_policies: Optional override for pine policies.
        eucalyptus_policies: Optional override for eucalyptus policies.
        lookup_table_file: Optional custom growth lookup table.
        carbon_parameters: Optional species carbon-fraction overrides.

    Raises:
        TreemunContractError: If the upstream return shape or columns do not
            match the pinned contract.
    """
    import treemun_sim as tm

    parameters = (
        dict(economic_parameters)
        if economic_parameters is not None
        else dict(ILLUSTRATIVE_ECONOMICS)
    )
    parameters_source = (
        "caller" if economic_parameters is not None else "illustrative_readme"
    )

    kwargs: dict[str, Any] = {
        "stands_file": str(stands_file),
        "horizon": int(horizon),
        "include_carbon": bool(include_carbon),
        "return_carbon_for_optimization": bool(include_carbon),
    }
    if pinus_policies is not None:
        kwargs["pinus_policies"] = pinus_policies
    if eucalyptus_policies is not None:
        kwargs["eucalyptus_policies"] = eucalyptus_policies
    if lookup_table_file is not None:
        kwargs["lookup_table_file"] = str(lookup_table_file)
    if carbon_parameters is not None:
        kwargs["carbon_parameters"] = carbon_parameters

    output = tm.simulate_forest(**kwargs)
    if len(output) == 5:
        forests, summary, ending, harvest, carbon = output
    elif len(output) == 4:
        forests, summary, ending, harvest = output
        carbon = None
    else:
        raise TreemunContractError(
            f"simulate_forest returned {len(output)} objects; expected 4 or 5"
        )

    alternatives = pd.DataFrame(list(summary))
    _require_columns(
        alternatives,
        {
            "stand_id",
            "policy",
            "species",
            "area_ha",
            "initial_age",
            "ending_age",
            "thinning_age",
            "final_harvest_age",
        },
        "policy_summary",
    )

    harvest_rows = [
        {
            "period": int(period),
            "species": str(species),
            "policy": str(policy),
            "stand_id": str(stand_id),
            "dry_wood_t": float(value),
        }
        for (period, species, policy, stand_id), value in harvest.items()
    ]
    harvest_frame = pd.DataFrame.from_records(
        harvest_rows,
        columns=["period", "species", "policy", "stand_id", "dry_wood_t"],
    )

    carbon_frame: pd.DataFrame | None = None
    if carbon is not None:
        carbon_rows = [
            {
                "period": int(period),
                "species": str(species),
                "policy": str(policy),
                "stand_id": str(stand_id),
                "carbon_tC_year": float(value),
            }
            for (period, species, policy, stand_id), value in carbon.items()
        ]
        carbon_frame = pd.DataFrame.from_records(
            carbon_rows,
            columns=["period", "species", "policy", "stand_id", "carbon_tC_year"],
        )

    evaluation = tm.evaluate_forest_economics(
        forests,
        economic_mode=economic_mode,
        discount_rate=float(discount_rate),
        economic_parameters=parameters,
    )
    economics = evaluation.summary_by_policy.copy()
    _require_columns(
        economics,
        {"stand_id", "policy", "economic_value"},
        "summary_by_policy",
    )

    stands = alternatives.drop_duplicates("stand_id")[
        ["stand_id", "species", "area_ha", "initial_age"]
    ].reset_index(drop=True)

    metadata: dict[str, Any] = {
        "treemun_sim_version": _upstream_version(),
        "treemun_module_version": getattr(tm, "__version__", "unknown"),
        "python_version": platform.python_version(),
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "horizon": int(horizon),
        "period_years": 1.0,
        "economic_mode": economic_mode,
        "discount_rate": float(discount_rate),
        "include_carbon": bool(include_carbon),
        "economic_parameters": parameters,
        "economic_parameters_source": parameters_source,
        "stands_file": str(stands_file),
        "stands_sha256": sha256(stands_file),
        "lookup_table_file": str(lookup_table_file) if lookup_table_file else None,
        "units": {
            "dry_wood": "Mg dry aboveground biomass",
            "carbon": "Mg C",
            "carbon_stock_time": "Mg C year",
            "area": "ha",
        },
    }

    return TreemunRun(
        stands=stands,
        alternatives=alternatives,
        harvest=harvest_frame,
        carbon=carbon_frame,
        economics=economics,
        ending_dry_wood={
            (str(stand_id), str(policy)): float(value)
            for (stand_id, policy), value in ending.items()
        },
        forests=tuple(forests),
        metadata=metadata,
    )


class TreemunContractError(RuntimeError):
    """Raised when Treemün's output does not match the pinned contract."""


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise TreemunContractError(
            f"{label} is missing required columns: {sorted(missing)}"
        )
