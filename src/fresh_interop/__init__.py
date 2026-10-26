"""Optional Treemün <-> WS3 interoperability and parity harness.

This package is deliberately outside the core FRESH dependency graph. It exists
to answer a narrow question: can WS3's optimization layer reproduce an
independent stand-policy MILP built from Treemün's coefficients?

Nothing here is a production runtime. See the repository README for scope.
"""

from .parity import (
    ParityResult,
    build_ws3_problem,
    carbon_coefficients,
    compare,
    economic_coefficients,
    harvest_coefficients,
    selected_policies,
    solve_treemun_reference,
)
from .run import (
    ILLUSTRATIVE_ECONOMICS,
    TreemunContractError,
    TreemunRun,
    load_treemun_run,
    sha256,
)
from .spatial import (
    adjacency_edges,
    edge_stand_ids,
    greenup_conflicts,
    pairs_to_constraint_sets,
    treemun_adjacency_to_ws3_pairs,
)

__version__ = "0.1.0a1"

__all__ = [
    "ILLUSTRATIVE_ECONOMICS",
    "ParityResult",
    "TreemunContractError",
    "TreemunRun",
    "adjacency_edges",
    "build_ws3_problem",
    "carbon_coefficients",
    "compare",
    "economic_coefficients",
    "edge_stand_ids",
    "greenup_conflicts",
    "harvest_coefficients",
    "load_treemun_run",
    "pairs_to_constraint_sets",
    "selected_policies",
    "sha256",
    "solve_treemun_reference",
    "treemun_adjacency_to_ws3_pairs",
]
