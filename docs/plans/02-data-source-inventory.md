# Plan 02 — Authoritative Data Source Inventory

## Objective

Verify the current authoritative documentation, releases, formats, classifications, access methods, and update behavior for every planned source.

## Scope

- ACS PUMS
- IPEDS
- College Scorecard
- BLS CPI
- BLS OEWS
- BLS Employment Projections
- NCES CIP
- SOC and crosswalks
- Federal Student Aid
- Department of Labor apprenticeship data for later use

## Work packages

### 1. Source register

For every dataset, record:

- publisher and authoritative landing page;
- documentation and data dictionary URLs;
- direct download or API mechanism;
- release cadence and lag;
- available history;
- file formats and compression;
- expected artifact size;
- version identifier;
- preliminary/provisional/final status;
- suppression rules;
- licensing and usage restrictions;
- change notices;
- update discovery strategy.

### 2. Versioning investigation

Determine how each publisher represents release dates, revisions, replacements, and corrected files. Define a stable internal version key.

### 3. Download feasibility

Perform small, non-production download tests. Record redirects, authentication/API keys, rate limits, archive structure, filenames, and checksums supplied by the publisher.

### 4. Schema and classification inventory

Record candidate fields, data types, code lists, classification vintages, and official crosswalk availability.

### 5. Freshness policy

Define newest-appropriate-final selection and the behavior of `--latest`. Specify warning requirements for provisional data.

### 6. Update detection

Specify whether discovery uses a release page, machine-readable catalog, API metadata, headers, or checksum comparison. Avoid brittle page scraping when official metadata exists.

## Deliverables

- `docs/datasets.md`
- source inventory table
- source-specific update strategy
- classification/crosswalk inventory
- licensing and restriction notes
- initial artifact-size/storage estimate
- unresolved source risks

## Validation requirements

- URLs must resolve to official publishers.
- Download claims must be tested.
- Dataset and documentation versions must match.
- No commercial mirror may be the canonical source when an original is available.
- APIs must not be assumed stable without current documentation.

## Acceptance criteria

- All MVP sources have verified acquisition paths.
- Version and publication status can be determined programmatically or with a documented manual step.
- Required variables appear available or are flagged as gaps.
- Expected storage and processing constraints are understood.
- Update checks can avoid silently replacing prior vintages.
