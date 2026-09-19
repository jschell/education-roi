# Data provenance and immutable storage

## Artifact identity

Raw artifacts use a content-addressed identity:

```text
{dataset_id}:{publisher_release}:{sha256}
```

Bytes are stored under:

```text
data/raw/{dataset_id}/{release}/{sha256}/{source_filename}
```

The SHA-256 directory prevents a publisher from silently replacing bytes under the same filename or release. Re-registering identical bytes is idempotent. Different bytes under an existing dataset release are retained separately and enter `REVIEW_REQUIRED`.

## Manifest contract

Each artifact records its dataset and publisher, release and vintage, retrieval time, requested and final URLs, SHA-256, size, publication status, schema version, software version, immutable storage path, and lifecycle state. Retrieval timestamps must be timezone-aware. Storage paths must be relative and cannot contain parent traversal.

Processed-artifact manifests record their own output hash and every input artifact identifier. A transformation without raw lineage is invalid.

## Source policy

Each dataset definition has a stable identifier and explicit allowed domains. Both the requested URL and final redirect target must use HTTPS and match an allowed domain or its subdomain. Lookalike suffixes are rejected.

## Lifecycle

The supported states are:

```text
DISCOVERED → DOWNLOADED → VALIDATED → APPROVED
                    ↘ REVIEW_REQUIRED ↗
```

Artifacts may be rejected from reviewable states. An approved artifact can be returned to review or rejected, but cannot silently move backward. Transitions are recorded with UTC time and an optional reason.

## Storage safety

- Hashing streams bytes rather than loading datasets into memory.
- Expected publisher checksums are verified before registration.
- ZIP and tar archives receive integrity checks.
- Artifact creation uses a temporary sibling and atomic replacement.
- Registered raw bytes and manifests are made read-only.
- SQLite uniqueness constraints and transactions make identical concurrent registration idempotent.
- Partial or failed registrations do not become approved artifacts.

## Adapter boundary

Release discovery and downloading are protocols. ACS, IPEDS, Scorecard, and BLS adapters will implement them separately so publisher-specific HTML, APIs, filenames, and release rules do not leak into the provenance core.

