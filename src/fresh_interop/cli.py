"""Command-line entry point for the Treemün parity harness."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .parity import compare, solve_treemun_reference
from .run import load_treemun_run, sha256
from .spatial import adjacency_edges, greenup_conflicts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fresh-interop",
        description=(
            "Optional Treemün <-> WS3 interoperability and parity harness. "
            "Not a production dependency of any FRESH package."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    parity = subparsers.add_parser(
        "parity",
        help="Run economic and carbon coefficient-level parity checks.",
    )
    parity.add_argument("--stands", type=Path, required=True)
    parity.add_argument("--geometry", type=Path)
    parity.add_argument("--out", type=Path, default=Path("fresh-interop-results.json"))
    parity.add_argument("--horizon", type=int, default=30)
    parity.add_argument("--no-carbon", action="store_true")
    parity.add_argument(
        "--even-flow",
        default="none",
        choices=[
            "none",
            "two_sided_average",
            "two_sided_consecutive",
            "nondecreasing",
        ],
    )
    parity.add_argument("--even-flow-tolerance", type=float, default=0.10)
    parity.add_argument("--greenup-window", type=int, default=2)
    return parser


def run_parity(args: argparse.Namespace) -> dict:
    geometry_frame = (
        adjacency_edges(args.geometry) if args.geometry is not None else None
    )

    run = load_treemun_run(
        args.stands,
        horizon=args.horizon,
        include_carbon=not args.no_carbon,
    )
    objectives = ["economic"] if args.no_carbon else ["economic", "carbon"]
    parity = [
        asdict(
            compare(
                run,
                objective=objective,
                even_flow_mode=args.even_flow,
                even_flow_tolerance=args.even_flow_tolerance,
            )
        )
        for objective in objectives
    ]

    spatial: dict[str, object] = {}
    if geometry_frame is not None:
        spatial = {
            "adjacency_edges": len(geometry_frame),
            "adjacency_columns": list(geometry_frame.columns),
            "greenup_window": int(args.greenup_window),
        }
        solution = solve_treemun_reference(run, objective="economic")
        conflicts = greenup_conflicts(
            run,
            solution["selected_policies"],
            geometry_frame,
            greenup_window=args.greenup_window,
        )
        spatial["greenup_conflicts_economic_plan"] = len(conflicts)

    report = {
        "environment": {
            "treemun_sim": run.metadata["treemun_sim_version"],
            "treemun_module_version": run.metadata["treemun_module_version"],
            "python": run.metadata["python_version"],
            "pandas": run.metadata["pandas_version"],
            "numpy": run.metadata["numpy_version"],
        },
        "fixture": {
            "stands_file": str(args.stands),
            "stands_sha256": sha256(args.stands),
            "geometry_file": str(args.geometry) if args.geometry else None,
            "geometry_sha256": sha256(args.geometry) if args.geometry else None,
            "horizon": int(args.horizon),
        },
        "alternatives": len(run.alternatives),
        "stands": len(run.stands),
        "parity": parity,
        "spatial": spatial,
        "units": run.metadata["units"],
        "note": (
            "Coefficient-level parity only. Treemün supplies the growth "
            "trajectories; this run does not validate them for other regions."
        ),
    }
    args.out.write_text(json.dumps(report, indent=2))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "parity":
        report = run_parity(args)
        for result in report["parity"]:
            print(
                f"{result['objective']}: "
                f"treemun={result['treemun_value']:.6f} "
                f"ws3={result['ws3_value']:.6f} "
                f"delta={result['relative_delta']} "
                f"policies={result['policy_agreement']}/{result['stands']}"
            )
        print(f"wrote {args.out}")
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
