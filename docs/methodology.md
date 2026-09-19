# Methodology Specification

**Status:** VERIFIED AGAINST MAIN ARTICLE; supplemental Table A1 still required  
**Last reviewed:** 2026-09-19  
**Article:** Zhang, Liu, and Hu (2024), DOI: https://doi.org/10.3102/00028312241231512

## Scope and evidence boundary

This specification was checked against the supplied 33-page article PDF. Equations 1–6, the ACS sample, covariates, cost construction, opportunity-cost assumptions, quantile method, and selection adjustment are verified from the main article.

The publisher lists a separate supplemental PDF. It contains at least Table A1, which maps 173 detailed ACS undergraduate fields into the paper’s ten major groups. The publisher’s supplement endpoint returned an access challenge in this environment. Until that file is obtained, the exact field crosswalk is unresolved and the reproduction hard gate remains open.

## Data and sample

The paper pools 13 annual ACS 1-year PUMS files, 2009–2021.

Inclusion criteria:

1. Born in the United States.
2. Age 18–65.
3. Highest attainment is either high-school diploma or bachelor’s degree.
4. Bachelor’s graduates report undergraduate major.
5. Not currently enrolled in school.
6. Positive annual earnings.

Explicit exclusions:

- less than high school;
- some college;
- associate degree;
- advanced degrees, including master’s, first-professional, and doctorate;
- nonpositive earnings;
- currently enrolled people;
- foreign-born people.

Final reported sample: 5,835,917, approximately 2.9 million high-school graduates and 2.9 million bachelor’s graduates.

The paper uses only the first reported undergraduate major. About 11% of bachelor’s graduates report a second major; a robustness analysis excluding dual majors was similar but is not published in the article.

## Outcomes and dollar normalization

Primary dependent variable: annual wage and salary income.

Robustness analysis: total earnings, including income such as self-employment.

For pooled ACS income:

1. Apply the ACS income adjustment factor for the annual file.
2. Convert to constant 2021 dollars using BLS CPI.

The resulting IRRs are real rates. The paper states nominal IRRs before inflation adjustment are typically 2–3 percentage points higher.

## Major taxonomy

The paper builds on Carnevale, Strohl, and Melton (2013) and a Census crosswalk to aggregate 173 detailed ACS fields into:

1. Biological and life sciences
2. Business
3. Computer science
4. Education
5. Engineering
6. Health
7. Humanities and liberal arts
8. Math and sciences
9. Social sciences
10. Other majors

Exact detailed-code membership is in supplemental Table A1 and must be imported verbatim once obtained. Do not independently invent or approximate that mapping in a paper-labeled reproduction.

## Covariates

The earnings equations include:

- age and age squared;
- sex;
- race/ethnicity: White reference, Asian, Black, Hispanic, other;
- marital status: single/never married reference, married, divorced/widowed/separated;
- Census region: Northeast, Midwest, South, West.

The authors intentionally omit industry and class of worker because those outcomes depend partly on college major.

## Mean earnings equations

The paper begins with a pooled log-linear equation:

[
ln(Y_i)=alpha_0+eta_1 age_i+eta_2 age_i^2+
sum_{j=1}^{10}gamma_j M_j+Z_i'\lambda+mu_i
	ag{1}
]

where (Y_i) is annual wage/salary earnings, (M_j) is major (j), high school is the reference, and (Z_i) contains covariates.

Because Equation 1 forces parallel age profiles, the preferred specification estimates separate equations:

[
ln(Y_{im})=alpha_{0m}+eta_{1m}age_i+eta_{2m}age_i^2+
Z_i'\lambda+mu_{im},quad m=0,ldots,10
	ag{2}
]

where (m=0) is high school and (m=1,ldots,10) are major groups.

To standardize observed composition, insert the pooled mean values of all bachelor’s-graduate covariates except age and age squared into every group equation:

[
ln(E_m)=hat{\alpha}_{0m}+ar{Z}'hat{\lambda}
	ag{3}
]

Then the age profile is:

[
ln(Y_{im})=ln(E_m)+hat{\beta}_{1m}age_i+
hat{\beta}_{2m}age_i^2
	ag{4}
]

Predictions are generated for every age 18–65.

### Implementation ambiguity to test

The printed Equation 2 displays an un-subscripted (\lambda), even though the text says a separate earnings equation is estimated for every group. Implementation must determine whether all coefficients, including covariates, are estimated separately by group—as separate regressions imply—or whether covariate slopes are constrained. This must be resolved from supplement/code/author clarification or bounded through both implementations.

## IRR equation

The paper’s printed equation is:

[
sum_{t=18}^{65}\frac{Y_{ct}-Y_{ht}}{(1+r)^{t-18}}
-
sum_{t=18}^{21}\frac{C_{ct}}{(1+r)^{t-18}}=0
	ag{5}
]

where:

- (Y_{ct}): predicted bachelor’s/major earnings at age (t);
- (Y_{ht}): predicted high-school earnings at age (t);
- (C_{ct}): college cost at age (t);
- (r): IRR.

College is modeled as four years of full-time attendance from ages 18–21. College students may earn income during those years; the cost construction must include both direct and opportunity costs as described below.

## Quantile regression

Equation 2 is re-estimated at earnings deciles using the Koenker–Bassett check-loss objective:

[
min_{bin R^K}
left[
sum_{y_i>x_i b}u|y_i-x_i b|
+
sum_{y_i<x_i b}(1-u)|y_i-x_i b|
ight]
	ag{6}
]

The paper estimates deciles and computes an IRR at each decile by comparing bachelor’s/major earnings with high-school earnings at the equivalent distributional position.

Identifying assumption: rank invariance. A person’s earnings rank is assumed unchanged between observed and counterfactual education states. Quantiles must not be presented as personalized probabilities.

The article presents selected quantiles; it says detailed other-decile results are in the supplement or available upon request.

## Selection adjustment

The paper cites Ashworth et al. (2021), which attributes about 37% of the raw college/high-school gap to individual heterogeneity. The paper’s observed controls explain about 11%, leaving approximately 25% as the preferred remaining adjustment.

Sensitivity specifications:

- 0%
- 25% preferred
- 50%

The adjustment applies consistently to:

1. the college/high-school earnings differential; and
2. opportunity cost while enrolled.

### Opportunity-cost adjustment

Using log-earnings equations for workers aged 22–25, the authors estimate a high-school/bachelor’s earnings difference of 0.472 log points, described as 60%. They attribute 25% of this gap to selection, giving a 15% counterfactual advantage for college-bound students. Thus college students’ foregone earnings are modeled as 15% higher than observed same-age high-school earnings in the preferred specification.

Implementation must encode the adjustment at the earnings/counterfactual level, never by multiplying the final IRR by 0.75.

## Direct-cost construction

Source: NPSAS:18-AC restricted-use undergraduate data.

Population:

- full-time students;
- four-year institutions;
- approximately 1,870 institutions and about 250,000 undergraduates in the NPSAS file.

Cost elements:

- tuition and fees;
- books and supplies;
- room and board;
- transportation;
- other education-related personal expenses.

All costs are converted to 2021 dollars.

Net cost equals enrollment-adjusted budget minus all grant aid. Loans are not deducted because they finance cost rather than reduce it.

Reported average grants are just over $10,000, composed approximately of:

- $2,250 federal;
- $1,580 state;
- $6,780 institutional;
- $340 private.

## Nontuition scenarios

The authors fix books and supplies at $1,000 in 2021 dollars, informed by approximately $281 course-material spending plus roughly $700 technology spending.

Other nontuition costs receive three attribution scenarios:

- 0%
- 50% preferred
- 100%

Preferred main specification:

- tuition and fees;
- $1,000 books/supplies;
- 50% of other nontuition costs;
- 25% selection adjustment.

Costs vary by race/ethnicity and major using NPSAS. The article does not use sex-specific costs due to small cells in some majors and broadly similar costs where both sexes are represented.

## Student earnings during college

Source: NPSAS:12.

Population: full-time students ages 18–21 attending four-year colleges.

Reported annual student earnings:

- $2,740 nominal in source-period terms;
- $3,268 in 2021 dollars.

This income offsets college-period cost/foregone earnings in reproduction.

## Reported validation targets from the main article

Preferred specification results include:

- overall IRR: 9.88% women;
- overall IRR: 9.06% men;
- computer science and engineering: above 13%;
- preferred assumptions: 50% other nontuition cost and 25% selection adjustment.

Table 3 contains combinations of cost attribution and selection adjustment. Table 4 contains major/demographic results. Exact target rows must be transcribed before tests are implemented.

## Project extensions kept separate

The following are not part of the paper’s core reproduction and must use separate configurations:

- institution-specific costs;
- enrollment/noncompletion risk;
- transfer pathways;
- debt financing;
- graduate education;
- regional earnings;
- scenario-vs-scenario counterfactuals;
- uncertainty propagation and Monte Carlo.

## Remaining open items

| ID | Item | Status |
|---|---|---|
| M-01 | Main equations 1–6 | Resolved |
| M-02 | ACS sample restrictions | Resolved |
| M-03 | Earnings definition/positive earnings | Resolved |
| M-04 | Quantile objective/deciles/rank invariance | Resolved |
| M-05 | Cost source and construction | Resolved |
| M-06 | Selection adjustment | Resolved |
| M-07 | Four-year timing, ages 18–21 | Resolved |
| M-08 | First-major handling | Resolved |
| M-09 | Advanced-degree exclusion | Resolved |
| M-10 | Exact 173-field crosswalk | **Blocked on supplemental Table A1** |
| M-11 | Survey weighting/variance details | Not explicitly stated in main methods; verify supplement/code |
| M-12 | Whether all Equation 2 covariate slopes vary by group | Clarification required |

## Sources

- Main article DOI: https://doi.org/10.3102/00028312241231512
- Supplemental listing: https://journals.sagepub.com/doi/abs/10.3102/00028312241231512
- ACS PUMS: https://www.census.gov/programs-surveys/acs/microdata.html
