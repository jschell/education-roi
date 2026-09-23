"""Exact paired GR registration from small stand-in archives."""

import json
from pathlib import Path
from shutil import copyfile
from zipfile import ZIP_DEFLATED, ZipFile

import polars as pl
import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.config.paths import ProjectPaths
from education_roi.ipeds import (
    GR2023_DATASET_ID,
    GR2023_DICTIONARY_DATASET_ID,
    IPEDSComponent,
    IPEDSReleaseCatalog,
    register_gr2023_release,
)
from education_roi.provenance.downloader import DownloadResult
from education_roi.provenance.models import ApprovalState, DatasetDefinition
from education_roi.provenance.store import ArtifactStore, Registry

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = "UNITID,GRTYPE,CHRTSTAT,SECTION,COHORT,LINE,XGRTOTLT,GRTOTLT\n"
ROWS = "236948,8,12,2,2,50,R,6713\n236948,12,16,2,2,18A,R,5619\n"


def test_register_pair_and_reject_invalid_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("education_roi.ipeds.registration._verify_dictionary", lambda path: None)
    release = next(
        item
        for item in IPEDSReleaseCatalog.from_file(CATALOG).releases
        if item.component is IPEDSComponent.GRADUATION_RATES
    )
    source = tmp_path / "source"
    source.mkdir()
    archive = source / "GR2023.zip"
    dictionary = source / "GR2023_Dict.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2023.csv", HEADER + "236948,8,12,2,2,50,R,1\n")
        output.writestr("gr2023_RV.csv", HEADER + ROWS)
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2023.xlsx", b"synthetic dictionary")

    class FakeDownloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            destination_directory.mkdir(parents=True, exist_ok=True)
            original = (archive, dictionary)[self.index % 2]
            self.index += 1
            target = destination_directory / f"download-{self.index}.zip"
            copyfile(original, target)
            return DownloadResult(target, url, url, target.stat().st_size)

    downloader = FakeDownloader()
    paths = ProjectPaths(tmp_path / "project")
    registered = register_gr2023_release(release, paths, downloader=downloader)  # type: ignore[arg-type]
    assert registered.data.state is ApprovalState.VALIDATED
    assert registered.dictionary.state is ApprovalState.VALIDATED
    assert registered.data.release == registered.dictionary.release == "2023-24-final"
    assert registered.data.dataset_id != registered.dictionary.dataset_id
    again = register_gr2023_release(release, paths, downloader=downloader)  # type: ignore[arg-type]
    assert again.data.artifact_id == registered.data.artifact_id
    assert again.dictionary.artifact_id == registered.dictionary.artifact_id
    assert not list((paths.data / ".downloads").glob("*.zip"))

    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2023.csv", HEADER + ROWS)
    with pytest.raises(ValueError, match="missing gr2023_RV.csv"):
        register_gr2023_release(release, paths, downloader=downloader)  # type: ignore[arg-type]
    assert not list((paths.data / ".downloads").glob("*.zip"))


def test_gr2023_cli_rejects_unreviewed_catalog(tmp_path: Path) -> None:
    catalog = tmp_path / "empty-gr.json"
    payload = IPEDSReleaseCatalog.from_file(CATALOG).model_dump(mode="json")
    payload["releases"] = payload["releases"][:1]
    catalog.write_text(json.dumps(payload), encoding="utf-8")
    result = CliRunner().invoke(app, ["ipeds", "register-gr2023", "--catalog", str(catalog)])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["status"] == "INVALID"


def test_resolve_gr2023_cli_uses_only_validated_paired_registry_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("education_roi.ipeds.graduation._verify_dictionary", lambda path: None)
    monkeypatch.setattr(
        "education_roi.ipeds.graduation_pipeline._verify_dictionary", lambda path: None
    )
    archive = tmp_path / "GR2023.zip"
    dictionary = tmp_path / "GR2023_Dict.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2023_RV.csv", HEADER + ROWS)
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2023.xlsx", b"synthetic dictionary")
    cli = CliRunner()
    command = [
        "ipeds",
        "resolve-gr2023",
        "236948",
        "--catalog",
        str(CATALOG),
        "--root",
        str(tmp_path),
    ]
    no_registry = cli.invoke(app, command)
    assert no_registry.exit_code == 2
    assert json.loads(no_registry.stdout)["status"] == "INVALID"

    release = next(
        item
        for item in IPEDSReleaseCatalog.from_file(CATALOG).releases
        if item.component is IPEDSComponent.GRADUATION_RATES
    )
    registry = Registry(tmp_path / "data/manifests/registry.sqlite")
    store = ArtifactStore(tmp_path / "data/raw", registry)
    for path, dataset_id, url in (
        (archive, GR2023_DATASET_ID, str(release.data_url)),
        (dictionary, GR2023_DICTIONARY_DATASET_ID, str(release.dictionary_url)),
    ):
        definition = DatasetDefinition(
            dataset_id=dataset_id,
            publisher="NCES",
            name="Fixture",
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
        registry.transition(manifest.artifact_id, ApprovalState.VALIDATED)
    available = cli.invoke(app, command)
    assert available.exit_code == 0, available.stdout
    payload = json.loads(available.stdout)
    assert payload["status"] == "AVAILABLE"
    assert payload["observed_rate"] == pytest.approx(5619 / 6713)
    assert payload["observation"]["dictionary_artifact_id"]
    assert "not individual completion probability" in payload["interpretation"]

    absent = cli.invoke(app, [*command[:2], "123456", *command[3:]])
    assert absent.exit_code == 0
    assert json.loads(absent.stdout)["status"] == "INSUFFICIENT_DATA"

    built = cli.invoke(
        app, ["ipeds", "build-gr2023", "--catalog", str(CATALOG), "--root", str(tmp_path)]
    )
    assert built.exit_code == 0, built.stdout
    report = json.loads(built.stdout)
    assert report["status"] == "WRITTEN"
    assert report["manifest"]["transformation"]["input_artifact_ids"]
    table = pl.read_parquet(report["parquet_path"])
    assert table.height == 1
    assert table["observed_rate"][0] == pytest.approx(5619 / 6713)
    again = cli.invoke(
        app, ["ipeds", "build-gr2023", "--catalog", str(CATALOG), "--root", str(tmp_path)]
    )
    assert again.exit_code == 0, again.stdout
    assert json.loads(again.stdout)["manifest"] == report["manifest"]

    stored = tmp_path / "data/raw" / registry.list_artifacts(GR2023_DATASET_ID)[0].storage_path
    stored.chmod(0o600)
    with stored.open("ab") as output:
        output.write(b"tampered")
    invalid = cli.invoke(app, command)
    assert invalid.exit_code == 2
    assert json.loads(invalid.stdout)["status"] == "INVALID"
    invalid_build = cli.invoke(
        app, ["ipeds", "build-gr2023", "--catalog", str(CATALOG), "--root", str(tmp_path)]
    )
    assert invalid_build.exit_code == 2
