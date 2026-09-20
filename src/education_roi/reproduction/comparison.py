from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from education_roi.acs.crosswalk import CrosswalkStatus


class ReproductionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ReproductionTarget:
    target_id: str
    paper_reference: str
    published_value: float
    absolute_tolerance: float
    relative_tolerance: float | None = None
    requires_verified_crosswalk: bool = False

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.paper_reference.strip():
            raise ValueError("target identity and paper reference cannot be empty")
        if (
            not isfinite(self.published_value)
            or not isfinite(self.absolute_tolerance)
            or self.absolute_tolerance < 0
        ):
            raise ValueError("target value and tolerance must be finite and tolerance nonnegative")
        if self.relative_tolerance is not None and (
            not isfinite(self.relative_tolerance) or self.relative_tolerance < 0
        ):
            raise ValueError("relative_tolerance must be finite and nonnegative")


@dataclass(frozen=True)
class ReproductionComparison:
    target: ReproductionTarget
    reproduced_value: float | None
    absolute_difference: float | None
    relative_difference: float | None
    status: ReproductionStatus
    configuration_hash: str
    dataset_hashes: tuple[str, ...]
    ambiguity_notes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "target_id": self.target.target_id,
            "paper_reference": self.target.paper_reference,
            "published_value": self.target.published_value,
            "reproduced_value": self.reproduced_value,
            "absolute_difference": self.absolute_difference,
            "relative_difference": self.relative_difference,
            "absolute_tolerance": self.target.absolute_tolerance,
            "relative_tolerance": self.target.relative_tolerance,
            "status": self.status.value,
            "configuration_hash": self.configuration_hash,
            "dataset_hashes": list(self.dataset_hashes),
            "ambiguity_notes": list(self.ambiguity_notes),
        }


def compare_target(
    target: ReproductionTarget,
    reproduced_value: float | None,
    *,
    configuration_hash: str,
    dataset_hashes: tuple[str, ...],
    crosswalk_status: CrosswalkStatus,
    ambiguity_notes: tuple[str, ...] = (),
) -> ReproductionComparison:
    if not configuration_hash.strip() or not dataset_hashes:
        raise ValueError("configuration hash and dataset hashes are required")
    if target.requires_verified_crosswalk and crosswalk_status is not CrosswalkStatus.VERIFIED:
        return ReproductionComparison(
            target,
            None,
            None,
            None,
            ReproductionStatus.BLOCKED,
            configuration_hash,
            dataset_hashes,
            ambiguity_notes,
        )
    if reproduced_value is None:
        return ReproductionComparison(
            target,
            None,
            None,
            None,
            ReproductionStatus.REVIEW,
            configuration_hash,
            dataset_hashes,
            ambiguity_notes,
        )
    if not isfinite(reproduced_value):
        raise ValueError("reproduced_value must be finite")
    absolute = abs(reproduced_value - target.published_value)
    relative = None if target.published_value == 0 else absolute / abs(target.published_value)
    passed = absolute <= target.absolute_tolerance
    if target.relative_tolerance is not None:
        passed = passed and relative is not None and relative <= target.relative_tolerance
    return ReproductionComparison(
        target,
        reproduced_value,
        absolute,
        relative,
        ReproductionStatus.PASS if passed else ReproductionStatus.FAIL,
        configuration_hash,
        dataset_hashes,
        ambiguity_notes,
    )
