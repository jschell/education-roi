import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from education_roi.acs.models import ACSRelease
from education_roi.cli.app import app
from education_roi.config.paths import ProjectPaths
from education_roi.provenance.store import Registry
from education_roi.reproduction.bootstrap import (
    BootstrapItem,
    BootstrapStatus,
    bootstrap_zhang_sources,
    resolve_vintages,
)

runner = CliRunner()


def test_vintage_selection_supports_years_and_ranges() -> None:
    assert resolve_vintages((2021,), None, None) == (2021,)
    assert resolve_vintages((2022, 2021, 2022), None, None) == (2021, 2022)
    assert resolve_vintages((), 2018, 2021) == (2018, 2019, 2020, 2021)
    with pytest.raises(ValueError, match="either"):
        resolve_vintages((2021,), 2020, 2021)
    with pytest.raises(ValueError, match="together"):
        resolve_vintages((), 2020, None)
    with pytest.raises(ValueError, match="cannot exceed"):
        resolve_vintages((), 2022, 2021)


def test_dry_run_reports_supported_and_blocked_sources(tmp_path: Path) -> None:
    report = bootstrap_zhang_sources(
        ProjectPaths(tmp_path), vintages=(2019, 2020, 2021), minimum_free_gb=0
    )
    assert report.execute is False
    assert report.ready is False
    assert [item.status for item in report.items] == [
        BootstrapStatus.PLANNED,
        BootstrapStatus.BLOCKED,
        BootstrapStatus.PLANNED,
        BootstrapStatus.BLOCKED,
    ]
    assert report.items[1].release == "2020-experimental-1yr-us"
    assert report.items[-1].source == "bls-cpi"


def test_cli_dry_run_accepts_inclusive_update_range(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "data",
            "bootstrap-zhang",
            "--root",
            str(tmp_path),
            "--from-year",
            "2018",
            "--to-year",
            "2019",
            "--minimum-free-gb",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert [item["release"] for item in payload["items"][:2]] == ["2018-1yr-us", "2019-1yr-us"]


def test_cli_rejects_conflicting_year_selection(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "data",
            "bootstrap-zhang",
            "--root",
            str(tmp_path),
            "--vintage",
            "2021",
            "--from-year",
            "2020",
            "--to-year",
            "2021",
        ],
    )
    assert result.exit_code == 2
    assert "either --vintage or --from-year" in result.output


def test_execute_mode_dispatches_each_supported_year(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[int, bool]] = []

    def fake_acs_item(
        release: ACSRelease,
        paths: ProjectPaths,
        registry: Registry,
        execute: bool,
    ) -> BootstrapItem:
        del paths, registry
        calls.append((release.vintage, execute))
        return BootstrapItem(
            "acs-pums", release.release_id, BootstrapStatus.COMPLETE, "fixture complete"
        )

    monkeypatch.setattr("education_roi.reproduction.bootstrap._acs_item", fake_acs_item)
    report = bootstrap_zhang_sources(
        ProjectPaths(tmp_path),
        vintages=(2019, 2021),
        execute=True,
        minimum_free_gb=0,
    )
    assert calls == [(2019, True), (2021, True)]
    assert [item.status for item in report.items[:2]] == [
        BootstrapStatus.COMPLETE,
        BootstrapStatus.COMPLETE,
    ]
