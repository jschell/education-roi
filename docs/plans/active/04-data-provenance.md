# Plan 04 — Data Provenance and Immutable Storage

**Status:** ACTIVE

## Objective

Implement the source-artifact lifecycle so every downstream result can be traced to immutable bytes and source metadata.

## Completed in the initial increment

- [x] Pydantic dataset, artifact, and transformation manifest schemas.
- [x] Stable dataset identifiers and allowed-domain policy.
- [x] Streaming SHA-256 and byte counting.
- [x] ZIP and tar integrity checks.
- [x] Content-addressed immutable raw paths.
- [x] Idempotent registration of identical bytes.
- [x] Review-required handling for changed bytes under a reused release.
- [x] SQLite datasets, artifacts, and transition history.
- [x] Explicit lifecycle state machine.
- [x] Source-independent discovery and downloader protocols.
- [x] `data check`, `data update`, and `data validate` CLI contracts.
- [x] Software version and timezone-aware retrieval time.
- [x] Processed-data lineage contract referencing raw artifact identifiers.
- [x] Provenance documentation.

## Remaining work

- [ ] Implement the production streaming HTTPS downloader using temporary files.
- [ ] Add interruption and redirect integration tests around the downloader.
- [ ] Add a multiprocess concurrency test for same-artifact registration.
- [ ] Add registry lookup/listing methods used by `data validate`.
- [ ] Make CLI commands operate on configured source adapters rather than placeholder responses.
- [ ] Confirm CI and Docker checks.

## Safety behavior

- Partial downloads never appear as approved artifacts.
- A repeated identical hash is idempotent.
- Changed bytes under the same publisher release remain separate and require review.
- Failed validation cannot become the default release.
- Raw artifacts and their manifests are read-only after registration.

## Verification

The initial increment has 16 unit tests covering CLI contracts, source-domain validation, hash and size calculation, corrupt archives, idempotence, changed releases, checksum mismatch, lifecycle transitions, safe paths, and transformation lineage.

## Acceptance criteria

- A raw artifact can be downloaded, hashed, registered, validated, and retrieved by immutable identifier.
- A processed artifact identifies every raw dependency.
- No release silently replaces another.
- Invalid or suspicious releases cannot become default without approval.

