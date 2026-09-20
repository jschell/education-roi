# Decision 0001 — Proceed Without Restricted NPSAS Microdata

**Status:** Accepted  
**Date:** 2026-09-20

## Decision

The project will continue without obtaining or using restricted-use NPSAS microdata. Restricted
NPSAS access is not a prerequisite for the MVP, the financial engine, scenario comparisons, or
institution-level analysis.

Public, authoritative sources will be used for education costs in this order when available:

1. scenario-specific documented costs;
2. institution/program published costs;
3. institution-level net price from IPEDS or College Scorecard;
4. public sector and income-band estimates;
5. broader sector or credential averages;
6. an explicit `INSUFFICIENT_DATA` result.

Every fallback must record the requested level, the level actually used, the source and vintage,
and the reason for the fallback. Broader averages must not be labeled as student-, demographic-, or
major-specific estimates. Cost uncertainty will be evaluated with documented low/base/high cases
or sensitivity ranges rather than hidden point assumptions.

## Effect on the Zhang reproduction

The project may complete a **methodologically aligned reproduction** using public or published cost
inputs. It must not claim an exact-input replication of Zhang, Liu & Hu (2024) when the paper's
restricted NPSAS-derived cost cells are unavailable.

The reproduction report must distinguish:

- calculations validated independently of NPSAS, including ACS sample processing, earnings
  profiles, quantile infrastructure, opportunity costs, selection adjustment, cash flows, and IRR;
- cost inputs replaced with public or published aggregates;
- discrepancies that cannot be resolved without the original restricted cost cells or author code.

Unavailable NPSAS inputs must not be estimated by tuning costs to match the paper's reported IRRs.
Table A1 verification, authoritative ACS inputs, exact coefficients, and CPI inputs remain separate
evidence requirements.

## Open-source and security consequence

No restricted NPSAS microdata will enter the repository, development environment, test fixtures,
Docker images, CI artifacts, or published result bundles. Synthetic fixtures and public aggregate
data remain the only permitted NPSAS-like inputs unless this decision is formally superseded.

## Revisit conditions

Reconsider this decision only if at least one of the following occurs:

- the authors provide reproducible aggregate cost cells or code that can be used lawfully;
- NCES publishes the required cells through a public product;
- exact-input replication becomes a funded or externally mandated deliverable; or
- an eligible institution agrees to sponsor restricted access and the expected research benefit
  justifies its legal, security, and disclosure-review burden.

Any reconsideration must preserve the public-data execution path and create a new decision record;
it must not silently alter this policy.
