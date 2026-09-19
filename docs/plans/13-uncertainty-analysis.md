# Plan 13 — Sensitivity and Uncertainty Analysis

## Objective

Quantify how conclusions change under alternative assumptions, first deterministically and then through empirically justified Monte Carlo simulation.

## Hard-gate rule

Do not implement probabilistic simulation until deterministic calculations, scenario resolution, and one-at-a-time/multivariate sensitivity tests are validated.

## Sensitivity scope

At minimum vary:

- net price;
- completion probability;
- time-to-degree;
- selection adjustment;
- earnings quantile;
- discount rate;
- aid;
- debt;
- graduate-school probability;
- real wage growth.

## Implementation tasks

### Deterministic sensitivity

1. Define parameter ranges with provenance.
2. Support one-at-a-time sensitivity.
3. Support structured scenario grids.
4. Rank drivers by effect on selected metrics.
5. Identify conclusion reversals.
6. Produce compact machine-readable results.

### Monte Carlo

1. Define stochastic variables only where evidence supports distributions.
2. Store distribution family, parameters, correlation assumptions, and source.
3. Use deterministic seeds and record generator/version.
4. Support completion and staged-pathway events.
5. Model earnings/employment uncertainty without treating observed quantiles as individual probabilities.
6. Add convergence and stability diagnostics.
7. Default to 10,000 simulations but allow configuration.
8. Report median/P10/P90 NPV and IRR, break-even distributions, and threshold probabilities.
9. Refuse simulation when required distributions lack justification.

## Statistical cautions

- Preserve dependencies between variables where evidence supports them.
- Avoid double-counting uncertainty already represented in an input.
- Do not imply causal or personalized probability claims.
- Separate parameter uncertainty from outcome heterogeneity where possible.

## Tests

- deterministic grid counts;
- seed reproducibility;
- known synthetic distributions;
- convergence diagnostics;
- correlated inputs;
- completion branching;
- undefined IRR handling;
- insufficient distribution evidence;
- serial/parallel equivalence within numerical tolerance.

## Acceptance criteria

- Base results always include deterministic sensitivity.
- Reported ranges trace to explicit assumptions.
- Simulation inputs have documented empirical or expert justification.
- Repeated seeded runs reproduce.
- The report identifies the assumptions most capable of changing the decision.
