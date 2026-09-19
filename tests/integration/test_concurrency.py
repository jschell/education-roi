import multiprocessing
from pathlib import Path
from typing import Any

import pytest

from education_roi.provenance.models import DatasetDefinition
from education_roi.provenance.store import ArtifactStore, Registry


def register_worker(root_text: str, source_text: str, output: Any) -> None:
    root = Path(root_text)
    source = Path(source_text)
    dataset = DatasetDefinition(
        dataset_id="test-data",
        publisher="Test Publisher",
        name="Test data",
        allowed_domains=("example.gov",),
    )
    try:
        registry = Registry(root / "registry.sqlite")
        registry.add_dataset(dataset)
        manifest = ArtifactStore(root / "raw", registry).register(
            source,
            dataset,
            release="2026",
            source_url="https://example.gov/data.csv",
            final_url="https://example.gov/data.csv",
            publication_status="final",
            schema_version="1",
        )
        output.put(("ok", manifest.artifact_id))
    except Exception as error:  # pragma: no cover - reported to parent assertion
        output.put(("error", repr(error)))


@pytest.mark.integration
def test_concurrent_registration_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_bytes(b"header\nvalue\n")
    Registry(tmp_path / "registry.sqlite")
    context = multiprocessing.get_context("spawn")
    output = context.Queue()
    processes = [
        context.Process(target=register_worker, args=(str(tmp_path), str(source), output))
        for _ in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    results = [output.get(timeout=5) for _ in processes]
    assert {result[0] for result in results} == {"ok"}, results
    assert len({result[1] for result in results}) == 1
    registry = Registry(tmp_path / "registry.sqlite")
    assert len(registry.list_artifacts()) == 1
    raw_files = [path for path in (tmp_path / "raw").rglob("*") if path.is_file()]
    assert len([path for path in raw_files if not path.name.endswith(".json")]) == 1
    assert not list((tmp_path / "raw").rglob("*.partial"))
