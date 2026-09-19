# Plan 04 — Data Provenance and Immutable Storage

**Status:** QUEUED

## Objective

Implement the source-artifact lifecycle so every downstream result can be traced to immutable bytes and source metadata.

## Prerequisites

- Plan 02 source inventory
- Plan 03 project foundation

## Domain objects

- dataset definition;
- release/vintage;
- source artifact;
- retrieval event;
- manifest;
- validation result;
- transformation;
- approval state.

## Implementation tasks

1. Define Pydantic manifest schemas.
2. Implement a dataset registry with stable internal identifiers.
3. Implement streaming HTTPS downloads to temporary files.
4. Validate allowed authoritative domains and final redirect targets.
5. Calculate SHA-256 and byte size.
6. Check archive integrity.
7. Move validated bytes into versioned immutable paths.
8. Refuse in-place replacement of an existing artifact.
9. Persist metadata and state transitions in SQLite.
10. Implement release discovery interfaces independent of source-specific adapters.
11. Add `data check`, `data update`, and `data validate` CLI contracts.
12. Record software version and retrieval time.
13. Define transformed-dataset manifests that reference exact raw artifact hashes.
14. Implement explicit approval/rejection/review-required states.

## Safety behavior

- Partial downloads never appear as approved artifacts.
- A repeated identical hash is idempotent.
- A changed file under the same publisher version is retained as a separate retrieval and flagged.
- Failed schema/statistical validation cannot become the default release.
- Raw artifacts are read-only after registration.

## Deliverables

- manifest and registry schemas;
- storage layout;
- downloader abstraction;
- checksum and archive validation;
- SQLite metadata store;
- lifecycle state machine;
- CLI contracts;
- provenance documentation.

## Tests

- interrupted download;
- checksum mismatch;
- corrupt archive;
- redirect to unexpected domain;
- identical repeated download;
- changed bytes under reused filename/version;
- concurrent attempt to register the same artifact;
- transformation lineage;
- state-transition validation.

## Acceptance criteria

- A raw artifact can be downloaded, hashed, registered, validated, and retrieved by immutable identifier.
- A processed artifact can identify every raw dependency.
- No release silently replaces another.
- Invalid or suspicious releases cannot become default without approval.
