"""Resolve scenario cost requests from validated immutable IPEDS artifacts."""

from collections.abc import Mapping
from pathlib import Path

from education_roi.ipeds.archive import parse_nonnegative_cost, read_charge_rows
from education_roi.ipeds.source import (
    BOOKS_COLUMN,
    BOOKS_STATUS_COLUMN,
    COST_COLUMNS,
    IPEDS_CHARGES_DATASET,
    TUITION_COLUMNS,
    TUITION_STATUS_COLUMNS,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ApprovalState, ArtifactManifest
from education_roi.provenance.store import Registry
from education_roi.scenarios.models import ScenarioDefinition
from education_roi.scenarios.resolution import (
    ProviderValue,
    ResolutionRequest,
    ScenarioResolutionError,
)


class IPEDSValueProvider:
    """Use one exact validated release; never fall back across years or institutions."""

    _usable_states = frozenset({ApprovalState.VALIDATED, ApprovalState.APPROVED})

    def __init__(
        self,
        registry: Registry,
        raw_root: Path,
        scenarios: Mapping[str, ScenarioDefinition],
    ) -> None:
        self._registry = registry
        self._raw_root = raw_root
        self._scenarios = dict(scenarios)
        self._cache: dict[str, dict[int, dict[str, str]]] = {}

    def _manifest(self, release: str) -> ArtifactManifest:
        artifacts = tuple(
            artifact
            for artifact in self._registry.list_artifacts(
                dataset_id=IPEDS_CHARGES_DATASET.dataset_id, release=release
            )
            if artifact.state in self._usable_states
        )
        if not artifacts:
            message = f"no validated IPEDS artifact for exact release {release}"
            raise ScenarioResolutionError(message)
        if len(artifacts) != 1:
            message = f"ambiguous validated IPEDS artifacts for release {release}"
            raise ScenarioResolutionError(message)
        return artifacts[0]

    def _rows(self, manifest: ArtifactManifest) -> dict[int, dict[str, str]]:
        cached = self._cache.get(manifest.artifact_id)
        if cached is not None:
            return cached
        path = self._raw_root / manifest.storage_path
        digest, size = sha256_file(path)
        if digest != manifest.sha256 or size != manifest.file_size:
            message = f"immutable IPEDS artifact failed integrity check: {manifest.artifact_id}"
            raise ScenarioResolutionError(message)
        rows = read_charge_rows(path)
        self._cache[manifest.artifact_id] = rows
        return rows

    def resolve(self, request: ResolutionRequest) -> ProviderValue | None:
        if request.source != "ipeds" or request.path not in COST_COLUMNS:
            return None
        scenario = self._scenarios.get(request.scenario_id)
        if scenario is None or scenario.education is None or scenario.education.institution is None:
            return None
        institution = scenario.education.institution
        manifest = self._manifest(request.vintage)
        row = self._rows(manifest).get(institution.unitid)
        if row is None:
            return None
        if request.path == "costs.tuition_and_fees":
            residency = institution.tuition_residency.value
            column = TUITION_COLUMNS[residency]
            status_column = TUITION_STATUS_COLUMNS[residency]
        else:
            column = BOOKS_COLUMN
            status_column = BOOKS_STATUS_COLUMN
        if column not in row:
            return None
        value = parse_nonnegative_cost(row[column])
        if value is None:
            return None
        return ProviderValue(
            value=value,
            source="ipeds",
            vintage=request.vintage,
            artifact_id=manifest.artifact_id,
            transformation_ids=(f"ipeds:{request.vintage}:unitid:{institution.unitid}:{column}",),
            source_metadata=(f"{status_column}={row.get(status_column, '<absent>')}",),
        )
