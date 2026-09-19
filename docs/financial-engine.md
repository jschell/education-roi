# Financial Engine

## Timing and money basis

Cash flows are annual and indexed by age. The first age in a series is discounting period zero;
subsequent ages are end-of-period annual flows. Calculations retain full precision and defer rounding
to presentation.

Every series declares either a constant-dollar (`real`) basis and dollar year or a `nominal` basis.
Scenario comparison rejects mismatched bases rather than converting implicitly. CPI conversion is a
separate transformation that records the series, source and target years, index observations, and
factor. It accepts only an exact real-dollar source basis; nominal or wrong-year inputs are rejected.

## Annual components and counterfactuals

Each scenario year requires explicit earnings, direct education cost, incremental living cost, grant
aid, and financing cost. Net cash flow is earnings plus grant aid minus the three cost categories.
Costs and financing remain separate components. Missing values are invalid; the engine does not infer
zero from absent data.

Education schedules retain tuition, fees, books, other nontuition expenses, total and counterfactual
living costs, grants, student earnings, and loan proceeds as distinct inputs. The selected nontuition
share is included in direct cost; only incremental living cost is included. Grants offset cost, while
loans do not. Four-, five-, six-, and custom-year schedules determine when graduate earnings begin.

Selection is applied before comparison at the earnings level. During enrollment, the selected share
of an estimated earnings premium raises foregone earnings. Outside enrollment, it moves the
counterfactual toward option earnings by the selected share of their gap. It is never applied to a
calculated IRR. Schedule results carry JSON-compatible enrollment, nontuition, selection, and loan
treatment assumptions.

## Debt and financing

Fixed-rate loan schedules declare the amount borrowed, interest rate, repayment term, origination
fee, enrollment period, grace period, subsidy treatment, and payment frequency. Unsubsidized balances
accrue and capitalize interest through enrollment and grace; subsidized balances enter repayment at
their original principal. Repayment is amortized at full internal precision and aggregated into
annual payment, principal, interest, and ending-balance records.

The complete payment schedule is available for liquidity reporting. Economic cash flows treat the
original education expense as the principal cost, so financing cost includes only interest and
origination fees and does not count principal repayment a second time. A zero-debt schedule is valid
and produces zero payments and financing costs.

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
