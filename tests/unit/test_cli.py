from pathlib import Path

from typer.testing import CliRunner

from education_roi.cli.app import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Reproducible education" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_paths(tmp_path: Path) -> None:
    result = runner.invoke(app, ["paths", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert f"root={tmp_path.resolve()}" in result.stdout


def test_data_contracts_are_visible() -> None:
    result = runner.invoke(app, ["data", "--help"])
    assert result.exit_code == 0
    assert "check" in result.stdout
    assert "update" in result.stdout
    assert "validate" in result.stdout


def test_ipeds_inventory_contract_is_visible() -> None:
    result = runner.invoke(app, ["ipeds", "--help"])
    assert result.exit_code == 0
    assert "compare-inventory" in result.stdout


def test_scenario_ipeds_resolution_contract_is_visible() -> None:
    result = runner.invoke(app, ["scenario", "--help"])
    assert result.exit_code == 0
    assert "resolve-ipeds" in result.stdout


def test_reproduction_bundle_contract_is_visible() -> None:
    result = runner.invoke(app, ["reproduce", "--help"])
    assert result.exit_code == 0
    assert "verify-bundle" in result.stdout
    assert "synthetic-run" in result.stdout
