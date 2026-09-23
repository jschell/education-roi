from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from education_roi.ipeds import (
    GR2023_DATASET_ID,
    GR2023_DICTIONARY_DATASET_ID,
    IPEDSComponent,
    IPEDSGraduationError,
    IPEDSGraduationStatus,
    IPEDSRelease,
    IPEDSReleaseCatalog,
    resolve_gr2023_bachelors,
    select_release,
)
from education_roi.provenance.models import ApprovalState, ArtifactManifest, DatasetDefinition
from education_roi.provenance.store import ArtifactStore, Registry

ROOT = Path(__file__).parents[2]
HEADER = "UNITID,GRTYPE,CHRTSTAT,SECTION,COHORT,LINE,XGRTOTLT,GRTOTLT\n"


def fixture(
    tmp_path: Path, rows: str
) -> tuple[Path, Path, IPEDSRelease, ArtifactManifest, ArtifactManifest]:
    release = select_release(
        IPEDSReleaseCatalog.from_file(ROOT / "data/manifests/ipeds-release-catalog.json"),
        IPEDSComponent.GRADUATION_RATES,
    )
    archive = tmp_path / "GR2023.zip"
    dictionary = tmp_path / "GR2023_Dict.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2023.csv", HEADER + rows)
        output.writestr("gr2023_RV.csv", HEADER + rows)
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2023.xlsx", b"synthetic dictionary placeholder")
    registry = Registry(tmp_path / "registry.sqlite")
    store = ArtifactStore(tmp_path / "raw", registry)
    manifests = []
    for path, dataset_id, url in (
        (archive, GR2023_DATASET_ID, str(release.data_url)),
        (dictionary, GR2023_DICTIONARY_DATASET_ID, str(release.dictionary_url)),
    ):
        definition = DatasetDefinition(
            dataset_id=dataset_id,
            publisher="National Center for Education Statistics",
            name="GR2023 fixture",
            allowed_domains=("nces.ed.gov",),
        )
        registry.add_dataset(definition)
        manifest = store.register(
            path,
            definition,
            release=release.release_id,
            source_url=url,
            final_url=url,
            publication_status="final",
            schema_version="ipeds-gr2023-v1",
        )
        manifests.append(registry.transition(manifest.artifact_id, ApprovalState.VALIDATED))
    return archive, dictionary, release, manifests[0], manifests[1]


def test_final_bachelors_rate_uses_matching_award_and_cohort_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("education_roi.ipeds.graduation._verify_dictionary", lambda path: None)
    args = fixture(
        tmp_path,
        "236948,8,12,2,2,50,R,6713\n236948,9,13,2,2,29A,R,5700\n236948,12,16,2,2,18A,Z,5619\n",
    )
    result = resolve_gr2023_bachelors(*args, 236948)
    assert result.status is IPEDSGraduationStatus.AVAILABLE
    assert result.observation is not None
    assert result.observation.adjusted_cohort == 6713
    assert result.observation.completers == 5619
    assert result.observation.observed_rate == pytest.approx(5619 / 6713)
    assert result.observation.award_outcome.value == "bachelors_degree"
    assert result.observation.source_statuses == ("R", "Z")
    assert result.observation.dictionary_artifact_id == args[4].artifact_id


@pytest.mark.parametrize(
    ("rows", "status", "reason"),
    [
        ("236948,8,12,2,2,50,R,12\n", IPEDSGraduationStatus.INSUFFICIENT_DATA, "missing"),
        (
            "236948,8,12,2,2,50,R,-1\n236948,12,16,2,2,18A,R,0\n",
            IPEDSGraduationStatus.INSUFFICIENT_DATA,
            "negative sentinel",
        ),
        (
            "236948,8,12,2,2,50,R,12\n236948,12,16,2,2,18A,R,\n",
            IPEDSGraduationStatus.INSUFFICIENT_DATA,
            "blank",
        ),
        (
            "236948,8,12,2,2,50,R,0\n236948,12,16,2,2,18A,R,0\n",
            IPEDSGraduationStatus.AVAILABLE,
            "",
        ),
    ],
)
def test_missing_or_zero_denominator_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rows: str,
    status: IPEDSGraduationStatus,
    reason: str,
) -> None:
    monkeypatch.setattr("education_roi.ipeds.graduation._verify_dictionary", lambda path: None)
    result = resolve_gr2023_bachelors(*fixture(tmp_path, rows), 236948)
    assert result.status is status
    if reason:
        assert reason in (result.reason or "")
    else:
        assert result.observation is not None and result.observation.observed_rate is None


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        (
            "236948,8,12,2,2,50,R,10\n236948,8,12,2,2,50,R,10\n",
            "duplicate GR2023 row",
        ),
        ("236948,8,12,3,2,50,R,10\n", "incompatible cohort keys"),
        (
            "236948,8,12,2,2,50,R,5\n236948,12,16,2,2,18A,R,6\n",
            "exceed adjusted cohort",
        ),
    ],
)
def test_invalid_rows_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: str, reason: str
) -> None:
    monkeypatch.setattr("education_roi.ipeds.graduation._verify_dictionary", lambda path: None)
    with pytest.raises(IPEDSGraduationError, match=reason):
        resolve_gr2023_bachelors(*fixture(tmp_path, rows), 236948)


def test_tampered_archive_fails_manifest_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("education_roi.ipeds.graduation._verify_dictionary", lambda path: None)
    archive, dictionary, release, data_manifest, dict_manifest = fixture(
        tmp_path, "236948,8,12,2,2,50,R,10\n236948,12,16,2,2,18A,R,5\n"
    )
    with archive.open("ab") as output:
        output.write(b"tampered")
    with pytest.raises(IPEDSGraduationError, match="do not match"):
        resolve_gr2023_bachelors(archive, dictionary, release, data_manifest, dict_manifest, 236948)


def test_dictionary_must_document_final_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from education_roi.ipeds.graduation import _verify_dictionary

    dictionary = tmp_path / "GR2023_Dict.zip"
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2023.xlsx", b"synthetic placeholder")
    rows = [
        ["(Final/revised release)"],
        *[
            [
                "1",
                variable,
                "N",
                "2",
                "Disc",
                "XGRTOTLT" if variable == "GRTOTLT" else "",
                variable,
            ]
            for variable in sorted(
                {"UNITID", "GRTYPE", "CHRTSTAT", "SECTION", "COHORT", "LINE", "GRTOTLT"}
            )
        ],
        ["GRTYPE", "80176", "8", "gr2023_RV", "2", "GRTYPE", "8", "Adjusted cohort"],
        [
            "GRTYPE",
            "80176",
            "12",
            "gr2023_RV",
            "2",
            "GRTYPE",
            "12",
            "Completers of bachelor's or equivalent degrees total",
        ],
    ]
    monkeypatch.setattr("education_roi.ipeds.graduation._xlsx_rows", lambda data: rows)
    _verify_dictionary(dictionary)
    rows[-1][7] = "Any degree or certificate"
    with pytest.raises(IPEDSGraduationError, match="does not support"):
        _verify_dictionary(dictionary)
