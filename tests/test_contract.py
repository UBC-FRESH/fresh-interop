from __future__ import annotations

import pandas as pd
import pytest

from fresh_interop import TreemunRun, load_treemun_run


def test_run_contract(run: TreemunRun) -> None:
    assert len(run.stands) == 105
    assert len(run.alternatives) == 780
    assert len(run.forests) == 780

    required_alternative_columns = {
        "stand_id",
        "policy",
        "species",
        "area_ha",
        "initial_age",
        "ending_age",
        "thinning_age",
        "final_harvest_age",
    }
    assert required_alternative_columns <= set(run.alternatives.columns)

    assert set(run.harvest.columns) == {
        "period",
        "species",
        "policy",
        "stand_id",
        "dry_wood_t",
    }
    assert run.carbon is not None
    assert set(run.carbon.columns) == {
        "period",
        "species",
        "policy",
        "stand_id",
        "carbon_tC_year",
    }

    assert run.metadata["units"]["dry_wood"] == "Mg dry aboveground biomass"
    assert run.metadata["units"]["carbon"] == "Mg C"
    assert run.metadata["units"]["carbon_stock_time"] == "Mg C year"
    assert run.metadata["economic_parameters_source"] == "illustrative_readme"
    assert len(run.metadata["stands_sha256"]) == 64
    assert run.metadata["horizon"] == 30


def test_without_carbon_returns_four_tuple(stands_file) -> None:
    run = load_treemun_run(stands_file, horizon=30, include_carbon=False)
    assert run.carbon is None
    assert len(run.forests) == 780
    assert set(run.harvest.columns) == {
        "period",
        "species",
        "policy",
        "stand_id",
        "dry_wood_t",
    }


def test_economics_join_is_complete(run: TreemunRun) -> None:
    keys = set(
        zip(
            run.alternatives["stand_id"].astype(str),
            run.alternatives["policy"].astype(str),
            strict=False,
        )
    )
    economic_keys = set(
        zip(
            run.economics["stand_id"].astype(str),
            run.economics["policy"].astype(str),
            strict=False,
        )
    )
    assert keys == economic_keys
    assert len(run.ending_dry_wood) == len(keys)


def test_contract_error_on_bad_frame() -> None:
    from fresh_interop.run import TreemunContractError, _require_columns

    with pytest.raises(TreemunContractError):
        _require_columns(pd.DataFrame({"a": [1]}), {"a", "b"}, "test")
