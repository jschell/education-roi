"""Configuration-backed adapter used to exercise generic provenance workflows."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from education_roi.provenance.discovery import DiscoveredRelease
from education_roi.provenance.models import DatasetDefinition


class ConfiguredRelease(BaseModel):
    """One explicitly configured publisher release."""

    model_config = ConfigDict(frozen=True)

    release: str
    source_url: str
    publication_status: str
    schema_version: str
    vintage: str | None = None
    expected_sha256: str | None = None


class ConfiguredDataset(BaseModel):
    """Dataset definition and explicitly configured releases."""

    model_config = ConfigDict(frozen=True)

    definition: DatasetDefinition
    releases: tuple[ConfiguredRelease, ...]

    def discover(self) -> tuple[DiscoveredRelease, ...]:
        return tuple(
            DiscoveredRelease(
                dataset_id=self.definition.dataset_id,
                release=item.release,
                source_url=item.source_url,
                publication_status=item.publication_status,
            )
            for item in self.releases
        )


class SourceConfiguration(BaseModel):
    """Portable configuration for generic source orchestration."""

    model_config = ConfigDict(frozen=True)

    datasets: tuple[ConfiguredDataset, ...]

    @classmethod
    def load(cls, path: Path) -> "SourceConfiguration":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def dataset(self, dataset_id: str) -> ConfiguredDataset:
        for configured in self.datasets:
            if configured.definition.dataset_id == dataset_id:
                return configured
        raise KeyError(dataset_id)
