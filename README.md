# fresh-interop

An **optional** interoperability and parity harness for the
[UBC-FRESH](https://github.com/UBC-FRESH) modelling ecosystem.

> Status: `0.1.0a1` alpha. Benchmark-only. This package is **not** a runtime
> dependency of `ws3`, `femic`, `fhops`, or `ws4`.

## Why this exists

[Treemün](https://github.com/fulloaf/treemun) is an open-source Python
framework for spatial growth-and-yield simulation and harvest-scheduling
optimization in Chilean plantation forests (Ulloa-Fierro et al., 2026,
*Ecological Informatics* 99, 104044; MIT). It occupies the same layer as the
WS3/WS4 estate model, so adopting it as a core dependency would create two
competing modelling cores.

This package takes the useful, low-risk part instead: it rebuilds Treemün's
binary stand–policy MILP with `ws3.opt.Problem` and compares the two solves.
That gives WS3 an independent oracle for matrix generation, objective
accounting, and solver integration without making Treemün part of the runtime.

## What it does

- Loads a Treemün run and normalizes the four- or five-object return into a
  frozen `TreemunRun` contract (stands, alternatives, harvest, carbon,
  economics, provenance).
- Builds the same stand–policy selection problem with `ws3.opt.Problem`.
- Compares objective value, selected policies, and runtime for economic and
  carbon objectives.
- Converts Treemün adjacency edges to unique unordered stand pairs and exposes
  green-up conflict counts for a selected plan.

It does **not**:

- validate Treemün's growth equations for British Columbia or any other region;
- replace `libcbm`/CBM carbon accounting (Treemün's carbon is a standing
  stock-time proxy);
- map Treemün policies onto WS3 `Action`/`DevelopmentType` semantics (that
  mapping is lossy and deliberately out of scope for v0.1).

## Reproduced result

On the bundled 105-stand / 834 ha Chilean fixture (30 *P. radiata*, 75
*E. globulus*, 780 alternatives, 30-year horizon):

| Objective | Treemün | `ws3.opt.Problem` | Relative delta | Policy agreement |
|---|---|---|---|---|
| Economic (NPV) | 2,596,065.355151 | 2,596,065.355151 | 0.0 | 105/105 |
| Carbon stock-time | 1,179,846.898470 | 1,179,846.898470 | 0.0 | 105/105 |

Spatial snapshot: 215 adjacency edges, 1,689 final-harvest indicator entries,
200 green-up conflicts for the economic plan at a 2-period window.

Environment: Python 3.12.3, `treemun-sim` 2.0.0.post1, `ws3` 1.1.0a5,
NumPy 2.5.4, pandas 3.1.0, Pyomo 6.10.1, HiGHS 1.15.1.

## Install (development)

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[complete,dev]"
pytest
```

The `complete` extra pins `treemun-sim==2.0.0.post1` and adds GeoPandas for the
spatial fixture. If the pin is unavailable, install the `v2.0.0` wheel from the
GitHub release and record its SHA256.

## Run the parity check

```bash
fresh-interop parity \
  --stands tests/data/forest_stands.csv \
  --geometry tests/data/treemun_landscape.gpkg \
  --out results.json
```

Expected output:

```text
economic: treemun=2596065.355151 ws3=2596065.355151 delta=0.0 policies=105/105
carbon: treemun=1179846.898470 ws3=1179846.898470 delta=0.0 policies=105/105
wrote results.json
```

## Python API

```python
from fresh_interop import load_treemun_run, compare

run = load_treemun_run(
    "tests/data/forest_stands.csv",
    horizon=30,
    include_carbon=True,
)
result = compare(run, objective="economic")
print(result.relative_delta, result.policy_agreement_fraction)
```

Build the WS3 side directly:

```python
from fresh_interop import build_ws3_problem, economic_coefficients

problem, mapping = build_ws3_problem(
    economic_coefficients(run),
    name="economic_parity",
)
problem.solve(threads=8)
print(problem.z(), problem.status())
```

## Scope and caveats

- **Units:** Treemün is Mg dry aboveground biomass. Do not silently convert to
  WS3 m³. The harness stays in biomass units end to end.
- **Arity:** `simulate_forest` returns four objects by default and five when
  `return_carbon_for_optimization=True` (which requires `include_carbon=True`).
  The loader normalizes this.
- **Even-flow:** the default two-sided-average formulation is infeasible on the
  bundled annual fixture because it contains zero-harvest periods. The code can
  build the constraints; the fixture cannot satisfy them. This is a fixture
  property, not a parity result.
- **Upstream maturity:** one maintainer, no CI workflows, and a v1 → v2
  breaking change (m³ → Mg, API renamed to English). Pin the exact version.
- **Licensing:** Treemün code is MIT. The article and its figures are
  CC BY-NC-ND; do not copy them into MIT-licensed documentation.

## Citation

If you use this harness, cite the upstream framework:

> Ulloa-Fierro, F., Álvarez-Miranda, E., Garcia-Gonzalo, J.,
> González-Olabarria, J. R., Mola-Yudego, B., Miranda, A., Carrasco-Barra, J., &
> Weintraub, A. (2026). Treemün: A Python framework for spatial growth-and-yield
> simulation and harvest scheduling optimization in plantation forests.
> *Ecological Informatics* 99, 104044.
> https://doi.org/10.1016/j.ecoinf.2026.104044

## License

MIT. See `LICENSE`.
