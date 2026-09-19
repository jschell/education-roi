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
