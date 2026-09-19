# Financial Engine

## Timing and money basis

Cash flows are annual and indexed by age. The first age in a series is discounting period zero;
subsequent ages are end-of-period annual flows. Calculations retain full precision and defer rounding
to presentation.

Every series declares either a constant-dollar (`real`) basis and dollar year or a `nominal` basis.
Scenario comparison rejects mismatched bases rather than converting implicitly. CPI conversion will
be a separate, provenance-bearing transformation in the next Plan 06 slice.

## Annual components and counterfactuals

Each scenario year requires explicit earnings, direct education cost, incremental living cost, grant
aid, and financing cost. Net cash flow is earnings plus grant aid minus the three cost categories.
Costs and financing remain separate components. Missing values are invalid; the engine does not infer
zero from absent data.

Opportunity cost is produced by subtracting the complete counterfactual scenario net flow from the
option net flow at each matching age. Scenarios must cover identical, consecutive ages. This supports
education versus workforce and option-versus-option comparisons with the same calculation.

## Initial metrics

- NPV accepts an explicit rate greater than -100% and discounts from period zero.
- Lifetime net value is the undiscounted sum of net cash flows; lifetime earnings remains a separate
  scenario component total.
- Break-even age is the first age whose cumulative incremental value is nonnegative; otherwise the
  result is explicitly `NEVER`.
- IRR searches a configurable bounded interval on a logarithmic grid and refines sign-changing roots
  by bisection. Results are `UNIQUE`, `MULTIPLE`, `NO_ROOT`, or `INDETERMINATE` for an all-zero series.
  The result preserves the search bounds. Even-multiplicity roots are not claimed unless a grid point
  is itself within tolerance, so the method does not imply an exhaustive unbounded polynomial proof.
