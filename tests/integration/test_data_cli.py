import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.provenance.downloader import DownloadResult, HttpDownloader

runner = CliRunner()


def write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "definition": {
                            "dataset_id": "test-data",
                            "publisher": "Test Publisher",
                            "name": "Test data",
                            "allowed_domains": ["example.gov"],
                        },
                        "releases": [
                            {
                                "release": "2026",
                                "source_url": "https://example.gov/data.csv",
                                "publication_status": "final",
                                "schema_version": "1",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_check_update_validate_workflow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "sources.json"
    download = tmp_path / "fixture.csv"
    download.write_bytes(b"header\nvalue\n")
    write_config(config)

    check = runner.invoke(app, ["data", "check", "--config", str(config)])
    assert check.exit_code == 0
    assert '"release": "2026"' in check.stdout

    def fake_download(
        self: HttpDownloader,
        url: str,
        destination_directory: Path,
        allowed_domains: tuple[str, ...],
    ) -> DownloadResult:
        return DownloadResult(download, url, url, download.stat().st_size)

    monkeypatch.setattr(
        "education_roi.cli.app.HttpDownloader.download",
        fake_download,
    )
    update = runner.invoke(
        app,
        [
            "data",
            "update",
            "test-data",
            "--config",
            str(config),
            "--root",
            str(tmp_path),
        ],
    )
    assert update.exit_code == 0, update.output
    payload = json.loads(update.stdout)
    assert payload["dataset_id"] == "test-data"

    validate = runner.invoke(app, ["data", "validate", "--root", str(tmp_path)])
    assert validate.exit_code == 0
    assert json.loads(validate.stdout) == {"checked": 1, "failures": []}

    stored = tmp_path / "data" / "raw" / payload["storage_path"]
    stored.chmod(0o644)
    stored.write_bytes(b"tampered")
    invalid = runner.invoke(app, ["data", "validate", "--root", str(tmp_path)])
    assert invalid.exit_code == 1
    assert json.loads(invalid.stdout)["failures"][0]["error"] == "integrity mismatch"
