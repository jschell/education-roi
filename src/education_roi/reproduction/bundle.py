"""Immutable, deterministic artifact bundles for Zhang reproduction runs."""

from dataclasses import dataclass
from hashlib import sha256
from json import JSONDecodeError, dumps, loads
from os import rename
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from education_roi.reproduction.reporting import ReproductionReport

BUNDLE_SCHEMA_VERSION = "reproduction-bundle-v1"
ARTIFACT_NAMES = (
    "cash-flows.json",
    "comparisons.json",
    "profile-validations.json",
    "profiles.json",
    "report.json",
    "report.md",
    "sample-flow.json",
)


class BundleIntegrityError(ValueError):
    """The bundle is incomplete, noncanonical, or fails an integrity check."""


@dataclass(frozen=True)
class BundleArtifact:
    path: str
    sha256: str
    file_size: int

    def as_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "file_size": self.file_size}


@dataclass(frozen=True)
class ReproductionBundle:
    run_id: str
    path: Path
    certification_status: str
    artifacts: tuple[BundleArtifact, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "path": str(self.path),
            "certification_status": self.certification_status,
            "artifacts": [item.as_dict() for item in self.artifacts],
        }


def _canonical_json(value: object) -> bytes:
    return dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _validate_run_id(run_id: str) -> None:
    if (
        not run_id.strip()
        or run_id != run_id.strip()
        or run_id in {".", ".."}
        or "/" in run_id
        or "\\" in run_id
    ):
        raise ValueError("run_id must be one nonempty path-safe segment")


def _artifact(path: Path) -> BundleArtifact:
    content = path.read_bytes()
    return BundleArtifact(path.name, sha256(content).hexdigest(), len(content))


def write_reproduction_bundle(
    report: ReproductionReport, *, results_root: Path, run_id: str
) -> ReproductionBundle:
    """Atomically write a new run bundle without replacing an existing run."""
    _validate_run_id(run_id)
    results_root.mkdir(parents=True, exist_ok=True)
    target = results_root / run_id
    if target.exists():
        raise FileExistsError(f"reproduction run already exists: {target}")

    payload = report.as_dict()
    sections: dict[str, object] = {
        "sample-flow.json": payload["sample_flow"],
        "profiles.json": payload["profiles"],
        "profile-validations.json": payload["profile_validations"],
        "cash-flows.json": payload["cash_flows"],
        "comparisons.json": payload["comparisons"],
    }
    temporary = Path(mkdtemp(prefix=f".{run_id}.", dir=results_root))
    try:
        (temporary / "report.json").write_bytes(_canonical_json(payload))
        (temporary / "report.md").write_text(report.to_markdown(), encoding="utf-8")
        for name, value in sections.items():
            (temporary / name).write_bytes(_canonical_json(value))
        artifacts = tuple(_artifact(temporary / name) for name in ARTIFACT_NAMES)
        manifest = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "run_id": run_id,
            "report_schema_version": report.schema_version,
            "certification_status": report.certification_status.value,
            "configuration_hash": report.configuration_hash,
            "dataset_hashes": list(report.dataset_hashes),
            "artifacts": [item.as_dict() for item in artifacts],
        }
        (temporary / "manifest.json").write_bytes(_canonical_json(manifest))
        rename(temporary, target)
    except Exception:
        if temporary.exists():
            rmtree(temporary)
        raise
    return ReproductionBundle(run_id, target, report.certification_status.value, artifacts)


def _read_json(path: Path) -> object:
    try:
        raw = path.read_bytes()
        value = loads(raw)
    except (OSError, UnicodeDecodeError, JSONDecodeError) as error:
        raise BundleIntegrityError(f"cannot read canonical JSON artifact: {path.name}") from error
    if raw != _canonical_json(value):
        raise BundleIntegrityError(f"JSON artifact is not canonical: {path.name}")
    return value


def verify_reproduction_bundle(path: Path) -> ReproductionBundle:
    """Verify the manifest, canonical encoding, section identity, and every artifact hash."""
    if not path.is_dir() or path.is_symlink():
        raise BundleIntegrityError("bundle path must be a real directory")
    expected_names = {*ARTIFACT_NAMES, "manifest.json"}
    actual_names = {item.name for item in path.iterdir()}
    if actual_names != expected_names:
        raise BundleIntegrityError("bundle has missing or unexpected artifacts")
    if any(not item.is_file() or item.is_symlink() for item in path.iterdir()):
        raise BundleIntegrityError("bundle artifacts must be regular files")

    manifest = _read_json(path / "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise BundleIntegrityError("bundle manifest schema is unsupported")
    run_id = manifest.get("run_id")
    certification_status = manifest.get("certification_status")
    artifact_values = manifest.get("artifacts")
    if not isinstance(run_id, str) or not isinstance(certification_status, str):
        raise BundleIntegrityError("bundle manifest identity is invalid")
    try:
        _validate_run_id(run_id)
    except ValueError as error:
        raise BundleIntegrityError("bundle manifest run_id is invalid") from error
    if not isinstance(artifact_values, list):
        raise BundleIntegrityError("bundle manifest artifacts are invalid")

    parsed_artifacts: list[BundleArtifact] = []
    for value in artifact_values:
        if not isinstance(value, dict):
            raise BundleIntegrityError("bundle manifest artifact entry is invalid")
        try:
            artifact = BundleArtifact(
                path=str(value["path"]),
                sha256=str(value["sha256"]),
                file_size=int(value["file_size"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BundleIntegrityError("bundle manifest artifact entry is invalid") from error
        if artifact.path not in ARTIFACT_NAMES:
            raise BundleIntegrityError("bundle manifest names an unexpected artifact")
        actual = _artifact(path / artifact.path)
        if actual != artifact:
            raise BundleIntegrityError(f"artifact integrity mismatch: {artifact.path}")
        parsed_artifacts.append(artifact)
    artifacts = tuple(parsed_artifacts)
    if tuple(item.path for item in artifacts) != ARTIFACT_NAMES:
        raise BundleIntegrityError("bundle manifest artifacts are incomplete or out of order")

    report = _read_json(path / "report.json")
    if not isinstance(report, dict):
        raise BundleIntegrityError("report.json must contain an object")
    metadata_pairs = (
        ("report_schema_version", "schema_version"),
        ("certification_status", "certification_status"),
        ("configuration_hash", "configuration_hash"),
        ("dataset_hashes", "dataset_hashes"),
    )
    if any(manifest.get(left) != report.get(right) for left, right in metadata_pairs):
        raise BundleIntegrityError("report metadata does not match the bundle manifest")
    section_pairs = (
        ("sample-flow.json", "sample_flow"),
        ("profiles.json", "profiles"),
        ("profile-validations.json", "profile_validations"),
        ("cash-flows.json", "cash_flows"),
        ("comparisons.json", "comparisons"),
    )
    if any(_read_json(path / name) != report.get(key) for name, key in section_pairs):
        raise BundleIntegrityError("split artifact does not match report.json")
    return ReproductionBundle(run_id, path, certification_status, artifacts)
