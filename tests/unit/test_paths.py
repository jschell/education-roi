from pathlib import Path

from pytest import MonkeyPatch

from education_roi.config import ProjectPaths


def test_explicit_root_takes_precedence(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EDU_ROI_ROOT", str(tmp_path / "ignored"))
    paths = ProjectPaths.from_environment(tmp_path)
    assert paths.root == tmp_path.resolve()
    assert paths.data == tmp_path.resolve() / "data"
    assert paths.results == tmp_path.resolve() / "results"


def test_environment_root(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EDU_ROI_ROOT", str(tmp_path))
    assert ProjectPaths.from_environment().root == tmp_path.resolve()
