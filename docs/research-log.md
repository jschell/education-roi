# Milestone 0 Research Log

## 2026-09-19

### Paper

Target: Zhang, Liu & Hu (2024), “Degrees of Return: Estimating Internal Rates of Return for College Majors Using Quantile Regression.”

Checked:

- Sage/AERA indexed publisher metadata;
- AERA article metadata;
- Rutgers institutional research metadata;
- ResearchGate record supplied by the user.

Verified from accessible metadata:

- journal/volume/pages/year;
- ACS 2009–2021;
- ten broad majors;
- high-school-graduate comparison;
- age-earnings/IRR focus;
- quantile-regression analysis;
- selection adjustment exists.

Blocked:

- ResearchGate served an automated-access restriction to the cloud browser;
- indexed publisher pages did not expose full equations, sample construction, or supplements;
- no accessible replication package was identified in this pass.

Decision:

- Plan 01 remains active/blocked.
- Do not implement a paper-labeled reproduction from abstract-level evidence.
- Request/use a lawful accessible PDF or user-provided copy in the next pass.

### Official sources verified

- Census ACS PUMS overview/download/documentation entry points.
- College Scorecard bulk files, API documentation, data documentation, and change log.
- BLS OEWS annual tables.
- BLS CPI data entry point.
- BLS Employment Projections occupational data, methods, tables, and crosswalks.
- BLS 2018 SOC manuals/definitions/crosswalk entry point.
- Federal Student Aid borrower and partner-announcement entry points.
- Apprenticeship.gov data/statistics entry point.
- NCES IPEDS/CIP canonical entry points; some NCES pages timed out in the research environment and require direct implementation-time download verification.

### Plan decisions

- Plan 02 may be marked complete as an architecture/source-inventory deliverable.
- Every endpoint must still be revalidated when its adapter is implemented.
- Plan 01 cannot pass its hard gate until article-level method verification is complete.


## 2026-09-19 — User supplied article PDF

The attached 33-page article was extracted and reviewed. It resolved:

- DOI and publication metadata;
- Equations 1–6;
- ACS 2009–2021 sample construction;
- primary/robustness earnings outcomes;
- 2021-dollar conversion;
- covariates;
- first-major handling;
- separate age-profile method;
- decile quantile regression and rank invariance;
- 0/25/50% selection sensitivity and preferred 25%;
- 15% opportunity-cost earnings uplift;
- NPSAS:18-AC direct cost construction;
- 0/50/100% nontuition attribution;
- $1,000 books/supplies;
- NPSAS:12 student earnings of $3,268 in 2021 dollars;
- four-year ages 18–21 attendance assumption.

The publisher confirms a 337.25 KB supplemental PDF named `sj-pdf-1-aer-10.3102_00028312241231512.pdf`. Its endpoint presented a browser challenge. Table A1’s exact 173-field crosswalk and any additional estimation details remain blocked. Plan 01 therefore stays active; the full-text blocker is narrowed to the supplement.
