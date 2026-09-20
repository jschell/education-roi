from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from education_roi.ipeds import IPEDS_CHARGES_DATASET, IPEDSArchiveError, IPEDSValueProvider
from education_roi.provenance.models import ApprovalState
from education_roi.provenance.store import ArtifactStore, Registry
from education_roi.scenarios import (
    ResolutionRequest,
    ScenarioResolutionError,
    load_scenario_file,
)

EXAMPLES = Path(__file__).parents[2] / "scenarios" / "examples"


def make_zip(path: Path, body: str) -> Path:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("IC2023_AY.csv", body)
    return path


def provider(tmp_path: Path, body: str, *, validate: bool = True) -> tuple[IPEDSValueProvider, str]:
    source = make_zip(tmp_path / "charges.zip", body)
    registry = Registry(tmp_path / "data/manifests/registry.sqlite")
    registry.add_dataset(IPEDS_CHARGES_DATASET)
    manifest = ArtifactStore(tmp_path / "data/raw", registry).register(
        source,
        IPEDS_CHARGES_DATASET,
        release="2023-24-final",
        source_url="https://nces.ed.gov/ipeds/datacenter/data/IC2023_AY.zip",
        final_url="https://nces.ed.gov/ipeds/datacenter/data/IC2023_AY.zip",
        publication_status="final",
        schema_version="ipeds-ic-ay-v1",
    )
    if validate:
        registry.transition(manifest.artifact_id, ApprovalState.VALIDATED, "test validation")
    scenario = load_scenario_file(EXAMPLES / "example-bachelors.yaml").scenario
    resolver = IPEDSValueProvider(registry, tmp_path / "data/raw", {scenario.id: scenario})
    return resolver, manifest.artifact_id


def request(path: str = "costs.tuition_and_fees") -> ResolutionRequest:
    return ResolutionRequest(
        scenario_id="example-bachelors", path=path, source="ipeds", vintage="2023-24-final"
    )


def test_provider_resolves_exact_unitid_release_and_column_with_provenance(tmp_path: Path) -> None:
    resolver, artifact_id = provider(
        tmp_path, "UNITID,CHG2AY3,CHG4AY3\n236948,12000,900\n999999,1,2\n"
    )
    tuition = resolver.resolve(request())
    books = resolver.resolve(request("costs.books_and_supplies"))
    assert tuition is not None and tuition.value == 12000
    assert books is not None and books.value == 900
    assert tuition.artifact_id == artifact_id
    assert tuition.transformation_ids == ("ipeds:2023-24-final:unitid:236948:CHG2AY3",)


@pytest.mark.parametrize("cell", ["", "-1"])
def test_missing_or_negative_sentinel_is_insufficient_not_zero(tmp_path: Path, cell: str) -> None:
    resolver, _ = provider(tmp_path, f"UNITID,CHG2AY3,CHG4AY3\n236948,{cell},900\n")
    assert resolver.resolve(request()) is None


def test_unvalidated_artifact_is_not_eligible(tmp_path: Path) -> None:
    resolver, _ = provider(
        tmp_path, "UNITID,CHG2AY3,CHG4AY3\n236948,12000,900\n", validate=False
    )
    with pytest.raises(ScenarioResolutionError, match="no validated IPEDS artifact"):
        resolver.resolve(request())


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("UNITID,CHG2AY3\n236948,1\n", "missing columns"),
        ("UNITID,CHG2AY3,CHG4AY3\n236948,1,2\n236948,3,4\n", "duplicate UNITID"),
        ("UNITID,CHG2AY3,CHG4AY3\n236948,nope,2\n", "invalid IPEDS cost"),
    ],
)
def test_schema_and_value_failures_are_explicit(tmp_path: Path, body: str, message: str) -> None:
    resolver, _ = provider(tmp_path, body)
    with pytest.raises(IPEDSArchiveError, match=message):
        resolver.resolve(request())


def test_provider_does_not_claim_other_sources_or_paths(tmp_path: Path) -> None:
    resolver, _ = provider(tmp_path, "UNITID,CHG2AY3,CHG4AY3\n236948,12000,900\n")
    assert resolver.resolve(request("costs.incremental_living_cost")) is None
    other = request().model_copy(update={"source": "college-scorecard"})
    assert resolver.resolve(other) is None
