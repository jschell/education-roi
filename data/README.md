# Data workspace

This directory contains only structure and documentation in Git. Downloaded source data must not be committed.

- `raw/`: immutable source artifacts, organized by publisher and release.
- `processed/`: reproducible derivatives of raw artifacts.
- `crosswalks/`: versioned classification mappings whose licenses permit inclusion.
- `manifests/`: small source and transformation manifests suitable for review.

Later plans will create these directories as needed. A raw artifact must never be overwritten by a newer release.

