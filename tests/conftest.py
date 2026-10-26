from __future__ import annotations

from pathlib import Path

import pytest

from fresh_interop import TreemunRun, load_treemun_run

DATA = Path(__file__).parent / "data"
STANDS = DATA / "forest_stands.csv"
GEOMETRY = DATA / "treemun_landscape.gpkg"


@pytest.fixture(scope="session")
def stands_file() -> Path:
    return STANDS


@pytest.fixture(scope="session")
def geometry_file() -> Path:
    return GEOMETRY


@pytest.fixture(scope="session")
def run(stands_file: Path) -> TreemunRun:
    pytest.importorskip("treemun_sim")
    return load_treemun_run(stands_file, horizon=30, include_carbon=True)
