"""Exact release housing-basis expense evidence, never incremental living cost."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.ipeds import (
    IPEDS_CHARGES_DATASET,
    IPEDS_DICTIONARY_DATASET,
    IPEDSComponent,
    IPEDSExpenseError,
    IPEDSRelease,
    IPEDSReleaseCatalog,
    resolve_ic2023_expenses,
    select_release,
)
from education_roi.ipeds.expenses import EXPENSE_LABELS, _verify_dictionary
from education_roi.provenance.models import ApprovalState, ArtifactManifest
from education_roi.provenance.store import ArtifactStore, Registry

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = (
    "UNITID,CHG2AY3,CHG4AY3,CHG5AY3,XCHG5AY3,CHG6AY3,XCHG6AY3,"
    "CHG7AY3,XCHG7AY3,CHG8AY3,XCHG8AY3,CHG9AY3,XCHG9AY3\n"
)


def fixture(
    tmp_path: Path, row: str
) -> tuple[Path, Path, IPEDSRelease, ArtifactManifest, ArtifactManifest]:
    release = select_release(
        IPEDSReleaseCatalog.from_file(CATALOG),
        IPEDSComponent.ACADEMIC_YEAR_CHARGES,
        release_id="2023-24-provisional",
        allow_nonfinal=True,
    )
    archive = tmp_path / "IC2023_AY.zip"
    dictionary = tmp_path / "IC2023_AY_Dict.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("ic2023_ay.csv", HEADER + row)
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("ic2023_ay.xlsx", b"fixture placeholder")
    registry = Registry(tmp_path / "data/manifests/registry.sqlite")
    store = ArtifactStore(tmp_path / "data/raw", registry)
    manifests = []
    for path, dataset, url in (
        (archive, IPEDS_CHARGES_DATASET, str(release.data_url)),
        (dictionary, IPEDS_DICTIONARY_DATASET, str(release.dictionary_url)),
    ):
        registry.add_dataset(dataset)
        item = store.register(
            path,
            dataset,
            release=release.release_id,
            source_url=url,
            final_url=url,
            publication_status="provisional",
            schema_version="ipeds-ic-ay-v1",
        )
        manifests.append(registry.transition(item.artifact_id, ApprovalState.VALIDATED))
    return archive, dictionary, release, manifests[0], manifests[1]


def test_living_bases_and_missing_cells_stay_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("education_roi.ipeds.expenses._verify_dictionary", lambda path: None)
    args = fixture(tmp_path, "236948,12643,900,17982,R,3027,R,16000,R,3500,Z,-1,N\n")
    result = resolve_ic2023_expenses(*args, 236948)
    assert result.status == "OBSERVED"
    assert result.on_campus_food_housing == 17982
    assert result.off_campus_food_housing == 16000
    assert result.with_family_other is None
    assert result.source_statuses["CHG9AY3"] == "N"
    assert result.source_columns["off_campus_other"] == "CHG8AY3"
    assert "not net price or incremental living cost" in result.interpretation
    absent = resolve_ic2023_expenses(*args, 999999)
    assert absent.status == "INSUFFICIENT_DATA"
    assert absent.on_campus_other is None
    args[0].write_bytes(b"tampered")
    with pytest.raises(IPEDSExpenseError, match="do not match"):
        resolve_ic2023_expenses(*args, 236948)


def test_dictionary_rejects_swapped_housing_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fixture(tmp_path, "236948,12643,900,1,R,2,R,3,R,4,R,5,R\n")[1]
    rows = [
        ["12011", code.lower(), "N", "5", "Cont", "X" + code.lower(), label]
        for code, label in EXPENSE_LABELS.items()
    ]
    monkeypatch.setattr("education_roi.ipeds.expenses._xlsx_rows", lambda *a, **kw: rows)
    _verify_dictionary(path)
    rows[0][6], rows[2][6] = rows[2][6], rows[0][6]
    with pytest.raises(IPEDSExpenseError, match="exact 2023-24"):
        _verify_dictionary(path)


def test_cli_requires_provisional_opt_in_and_validated_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("education_roi.ipeds.expenses._verify_dictionary", lambda path: None)
    fixture(tmp_path, "236948,12643,900,17982,R,3027,R,16000,R,3500,R,3297,R\n")
    args = [
        "ipeds",
        "resolve-expenses",
        "236948",
        "--catalog",
        str(CATALOG),
        "--root",
        str(tmp_path),
    ]
    blocked = CliRunner().invoke(app, args)
    assert blocked.exit_code == 2
    result = CliRunner().invoke(app, [*args, "--allow-nonfinal"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["publication_status"] == "provisional"
    assert payload["on_campus_food_housing"] == 17982
