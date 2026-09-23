"""Legacy final GR2022 path is exact and does not silently reuse GR2023 code rules."""

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
    IPEDSComponent,
    IPEDSReleaseCatalog,
    register_gr2022_release,
    transform_gr2023_archive,
)
from education_roi.ipeds.graduation import IPEDSGraduationError
from education_roi.provenance.downloader import DownloadResult

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = "UNITID,GRTYPE,CHRTSTAT,SECTION,COHORT,LINE,XGRTOTLT,GRTOTLT\n"


def test_legacy_registration_and_build_preserve_observed_cohort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("education_roi.ipeds.registration.verify_gr2022_dictionary", lambda p: None)
    monkeypatch.setattr(
        "education_roi.ipeds.graduation_pipeline.verify_gr2022_dictionary", lambda p: None
    )
    sources = tmp_path / "sources"
    sources.mkdir()
    archive, dictionary = sources / "GR2022.zip", sources / "GR2022_Dict.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2022.csv", HEADER + "236948,8,12,2,2,50,R,1\n")
        output.writestr(
            "gr2022_rv.csv",
            HEADER + "236948, 8, 12, 2, 2, 50,R,6411\n236948,12,16, 2, 2,18A,R,5409\n",
        )
    with ZipFile(dictionary, "w", ZIP_DEFLATED) as output:
        output.writestr("gr2022.xlsx", b"synthetic dictionary")

    class LocalDownloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            destination_directory.mkdir(parents=True, exist_ok=True)
            original = (archive, dictionary)[self.index]
            self.index += 1
            target = destination_directory / f"download-{self.index}.zip"
            copyfile(original, target)
            return DownloadResult(target, url, url, target.stat().st_size)

    release = next(
        r
        for r in IPEDSReleaseCatalog.from_file(CATALOG).releases
        if r.component is IPEDSComponent.GRADUATION_RATES and r.release_id == "2022-23-final"
    )
    paths = ProjectPaths(tmp_path / "project")
    pair = register_gr2022_release(release, paths, downloader=LocalDownloader())  # type: ignore[arg-type]
    with pytest.raises(IPEDSGraduationError, match="GR2023"):
        transform_gr2023_archive(
            paths.data / "raw" / pair.data.storage_path,
            paths.data / "raw" / pair.dictionary.storage_path,
            paths.data / "processed",
            pair.data,
            pair.dictionary,
            release,
        )
    cli = CliRunner()
    args = ["ipeds", "build-gr2022", "--catalog", str(CATALOG), "--root", str(paths.root)]
    result = cli.invoke(app, args)
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["manifest"]["cohort_year"] == 2016
    assert len(payload["manifest"]["transformation"]["input_artifact_ids"]) == 2
    rows = pl.read_parquet(payload["parquet_path"]).to_dicts()
    assert len(rows) == 1
    assert rows[0]["adjusted_cohort"] == 6411
    assert rows[0]["bachelors_awards"] == 5409
    assert rows[0]["raw_adjusted_cohort"] == "6411"
    assert rows[0]["observed_rate"] == pytest.approx(5409 / 6411)
    rerun = cli.invoke(app, args)
    assert rerun.exit_code == 0
    assert json.loads(rerun.stdout)["manifest"] == payload["manifest"]
