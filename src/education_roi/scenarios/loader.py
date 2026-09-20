"""Safe YAML loading for versioned scenario documents."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from education_roi.scenarios.models import ScenarioDocument


class ScenarioValidationError(ValueError):
    pass


def parse_scenario_yaml(content: str, *, source: str = "<memory>") -> ScenarioDocument:
    try:
        value = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise ScenarioValidationError(f"invalid YAML in {source}: {error}") from error
    if not isinstance(value, dict):
        raise ScenarioValidationError(f"scenario document in {source} must be a mapping")
    try:
        return ScenarioDocument.model_validate(value)
    except ValidationError as error:
        raise ScenarioValidationError(f"invalid scenario in {source}: {error}") from error


def load_scenario_file(path: Path) -> ScenarioDocument:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ScenarioValidationError(f"cannot read scenario file {path}: {error}") from error
    return parse_scenario_yaml(content, source=str(path))
