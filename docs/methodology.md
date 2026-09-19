# Methodology Specification

**Status:** PROVISIONAL — Plan 01 remains active  
**Last reviewed:** 2026-09-19

## Research target

The initial reproduction target is Zhang, Liu, and Hu (2024), “Degrees of Return: Estimating Internal Rates of Return for College Majors Using Quantile Regression,” *American Educational Research Journal* 61(3), 577–609.

Public publisher/author metadata verifies that the study:

- uses American Community Survey data from 2009–2021;
- estimates IRRs for college graduates in ten broad majors relative to high-school graduates;
- finds materially different age-earnings trajectories and returns across majors;
- applies quantile regression to examine different positions in the earnings distribution;
- uses a selection adjustment;
- reports generally higher IRRs toward the high end of the earnings distribution.

These facts are verified from the publisher/AERA metadata and institutional research metadata. The full article equations, complete sample restrictions, appendices, and supplements were **not accessible during this research pass**. ResearchGate returned an automated-access restriction, and indexed publisher pages exposed only metadata/abstract material.

Accordingly, this document distinguishes:

- **VERIFIED:** supported directly by accessible primary metadata or government documentation;
- **PROVISIONAL:** standard implementation proposal awaiting article verification;
- **PROJECT EXTENSION:** capability required by this project but not attributed to the paper.

## Hard-gate rule

No paper-specific implementation may be labeled a Zhang reproduction until the full article and any supplements have been reviewed and the provisional fields below are replaced with verified specifications.

## Analytical unit

**VERIFIED:** ten broad bachelor’s-major groups are compared with high-school graduates.

**PROJECT EXTENSION:** the system’s primary unit is a scenario. A scenario can describe an institution/program, transfer pathway, apprenticeship, workforce path, or staged pathway. Any scenario may be another scenario’s counterfactual.

## Canonical cash-flow framework

The following equations are the project’s provisional mathematical contract. They are standard financial definitions and are **not yet asserted to be verbatim paper equations**.

For scenario (s), age/year (t):

[
CF_{s,t}=E_{s,t}-C_{s,t}-L_{s,t}-F_{s,t}
]

where:

- (E): real earnings;
- (C): direct education costs net of grants/scholarships;
- (L): incremental living costs relative to the counterfactual;
- (F): financing costs kept separate from education resource cost.

Incremental cash flow relative to counterfactual (c):

[
Delta CF_t=CF_{s,t}-CF_{c,t}
]

Net present value at real discount rate (d):

[
NPV(d)=sum_{t=0}^{T}rac{Delta CF_t}{(1+d)^t}
]

IRR is a real rate (r) satisfying:

[
0=sum_{t=0}^{T}rac{Delta CF_t}{(1+r)^t}
]

The engine must return structured undefined states when no real root exists or multiple economically relevant roots occur.

Break-even age is the first age (a) for which cumulative incremental value is nonnegative and remains disclosed with the chosen discounting convention:

[
a^*=minleft{a:sum_{t=0}^{a}rac{Delta CF_t}{(1+d)^t}ge 0ight}
]

## Real-dollar conversion

For a monetary value (V_y) measured in year (y), converted to target year (b):

[
V_b=V_yrac{CPI_b}{CPI_y}
]

Every conversion must retain CPI series ID, source period, target period, source value, target value, and factor. Annual-average CPI-U is the proposed default for annual cash flows; this remains a project choice unless the paper specifies another series/convention.

## Earnings model

**VERIFIED:** the study analyzes age-earnings trajectories and quantile variation.

**PROVISIONAL implementation:**

- model approximately ages 18–65;
- use P10, P25, P50, P75, and P90;
- treat percentiles as distribution positions, not individual probabilities;
- estimate separate trajectories by education/major and other verified covariates;
- use survey person weights;
- preserve unweighted N, weighted N, uncertainty, ACS product, vintage, geography, and fallback level;
- avoid extrapolation outside observed support unless explicitly labeled.

The exact paper quantile-regression equation, polynomial/spline age form, covariates, pooling, weighting behavior, and standard-error procedure remain unresolved pending full-text review.

## ACS candidate variables

These are candidates to confirm against the paper and the selected ACS vintage’s data dictionary:

| Concept | Candidate ACS PUMS fields | Status |
|---|---|---|
| Age | `AGEP` | Highly likely; paper-specific rule unverified |
| Attainment | `SCHL` | Highly likely |
| First/second bachelor’s field | `FOD1P`, `FOD2P` | Highly likely |
| Wage/salary earnings | `WAGP` | Candidate target |
| Total personal income | `PINCP` | Candidate; do not substitute for earnings silently |
| Employment status | `ESR` | Candidate restriction/covariate |
| Weeks worked | `WKWN` or vintage-specific equivalent | Candidate |
| Usual hours | `WKHP` | Candidate |
| Person weight | `PWGTP` | Required for weighted estimates |
| Replicate weights | `PWGTP1–PWGTP80` | Candidate for variance estimation |
| Inflation adjustment | `ADJINC` | Required when pooling income years as defined by Census |
| Sex | `SEX` | Candidate stratifier/control |
| Race/ethnicity | `RAC1P`, `HISP` | Candidate control/descriptive fields |
| State/PUMA | `ST`, `PUMA` | Project extension |
| Occupation/industry | `OCCP`, `INDP` | Validation/context only |

Field availability and coding must be checked per vintage. No transformation should proceed solely from this table.

## Counterfactual and foregone earnings

**VERIFIED:** the research compares college-major returns with high-school graduates.

**PROVISIONAL:** foregone earnings during enrollment equal the counterfactual earnings path minus any scenario earnings during study. They are not zero.

**PROJECT EXTENSION:** a counterfactual may be another education scenario. Incremental comparison must use aligned annual cash flows rather than subtracting summary IRRs.

## Direct and living costs

Paper-specific cost datasets, tuition assumptions, duration, and living-cost treatment are unresolved.

Project rules:

- distinguish sticker price, net price, and incremental living cost;
- do not count all food/housing as education cost automatically;
- keep grants/scholarships, family contribution, and borrowing distinct;
- keep economic resource cost separate from financing cost;
- retain nominal year and conversion provenance.

## Selection adjustment

**VERIFIED:** the study applies a selection adjustment.

The exact formula and placement in the earnings/cash-flow calculation remain unverified. The project must not assume that “25% adjustment” necessarily means multiplying all graduate earnings, the earnings premium, or IRR by 0.75 until the article confirms it.

Provisional sensitivity values remain 0%, 10%, 25%, 40%, and 50%, but are project scenarios—not a claim about the paper’s exact operation.

## Completion and graduate education

These are project extensions. Compute separately:

- conditional-graduate return;
- expected enrollment return incorporating noncompletion/late completion;
- optional and mandatory graduate-school branches.

Do not use graduate-only outcomes as enrollment outcomes.

## Known ambiguities

| ID | Question | Impact | Resolution required |
|---|---|---|---|
| M-01 | Exact paper equations | Critical | Review full article |
| M-02 | Exact ACS sample restrictions | Critical | Review methods/appendix |
| M-03 | Earnings definition and zero earners | Critical | Verify target and exclusions |
| M-04 | Quantile-regression specification | Critical | Verify form, covariates, weights |
| M-05 | Cost source and construction | Critical | Verify datasets/dollar basis |
| M-06 | Selection-adjustment formula | Critical | Verify equation and preferred value |
| M-07 | Tuition duration/timing | High | Verify annual timing |
| M-08 | Second-major handling | Medium | Verify major assignment |
| M-09 | Graduate-degree handling | High | Verify sample |
| M-10 | Variance/uncertainty method | High | Verify replicate weights/SE approach |

## Primary references

- Publisher/AERA article landing: https://journals.sagepub.com/
- AERA article metadata: https://www.aera.net/
- User-provided ResearchGate record: https://www.researchgate.net/publication/378878341_Degrees_of_Return_Estimating_Internal_Rates_of_Return_for_College_Majors_Using_Quantile_Regression
- Rutgers research metadata: https://www.researchwithrutgers.com/
- Census ACS PUMS: https://www.census.gov/programs-surveys/acs/microdata.html
