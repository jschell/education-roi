"""Deterministic machine- and human-readable Zhang reproduction reports."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from json import dumps

from education_roi.reproduction.quantiles import (
    RANK_INVARIANCE_WARNING,
    ProfileValidationReport,
    QuantileIRRResult,
    QuantileProfileFit,
)


class CertificationStatus(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    CERTIFIED = "CERTIFIED"


@dataclass(frozen=True)
class ReproductionReport:
    """Canonical report retaining all intermediate reproduction artifacts."""

    schema_version: str
    certification_status: CertificationStatus
    configuration_hash: str
    dataset_hashes: tuple[str, ...]
    blockers: tuple[str, ...]
    ambiguity_notes: tuple[str, ...]
    sample_flow: tuple[dict[str, object], ...]
    profiles: tuple[QuantileProfileFit, ...]
    profile_validations: tuple[ProfileValidationReport, ...]
    cash_flows: tuple[QuantileIRRResult, ...]
    comparisons: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        if not self.schema_version.strip() or not self.configuration_hash.strip():
            raise ValueError("report schema version and configuration hash are required")
        if not self.dataset_hashes or any(not value.strip() for value in self.dataset_hashes):
            raise ValueError("report requires nonempty dataset hashes")
        if self.certification_status is CertificationStatus.CERTIFIED and self.blockers:
            raise ValueError("a certified report cannot retain blockers")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "certification_status": self.certification_status.value,
            "configuration_hash": self.configuration_hash,
            "dataset_hashes": list(self.dataset_hashes),
            "blockers": list(self.blockers),
            "ambiguity_notes": list(self.ambiguity_notes),
            "quantile_interpretation": RANK_INVARIANCE_WARNING,
            "sample_flow": list(self.sample_flow),
            "profiles": [profile.as_dict() for profile in self.profiles],
            "profile_validations": [item.as_dict() for item in self.profile_validations],
            "cash_flows": [item.as_dict() for item in self.cash_flows],
            "comparisons": list(self.comparisons),
        }

    def to_json(self) -> str:
        """Return canonical JSON so identical inputs produce byte-identical output."""
        return dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def to_markdown(self) -> str:
        """Render a deterministic discrepancy and ambiguity report."""
        lines = [
            "# Zhang Reproduction Report",
            "",
            f"Status: **{self.certification_status.value}**",
            "",
            f"> {RANK_INVARIANCE_WARNING}",
            "",
            "## Evidence blockers",
            "",
        ]
        lines.extend(f"- {item}" for item in self.blockers)
        if not self.blockers:
            lines.append("- None")
        lines.extend(["", "## Quantile profiles", ""])
        lines.append("| Quantile | Solver | Profile |")
        lines.append("|---|---|---|")
        for fit in sorted(self.profiles, key=lambda item: item.definition.quantile):
            profile_state = "available" if fit.profile is not None else "unavailable"
            lines.append(
                f"| {fit.definition.label} | {fit.solver.status.value} | {profile_state} |"
            )
        lines.extend(["", "## Distributional IRR", ""])
        lines.append("| Quantile | Median | IRR status | Roots |")
        lines.append("|---|---:|---|---|")
        for item in sorted(self.cash_flows, key=lambda value: value.definition.quantile):
            irr = item.internal_rate_of_return
            roots = ", ".join(f"{root:.6%}" for root in irr.roots) or "—"
            lines.append(
                f"| {item.definition.label} | "
                f"{'yes' if item.definition.is_median else 'no'} | {irr.status.value} | {roots} |"
            )
        lines.extend(["", "## Discrepancies", ""])
        discrepancies = [
            comparison
            for comparison in self.comparisons
            if str(comparison.get("status", "")) != "PASS"
        ]
        if discrepancies:
            for comparison in discrepancies:
                lines.append(
                    f"- {comparison.get('target_id', 'unknown target')}: "
                    f"{comparison.get('status', 'UNKNOWN')} "
                    f"(published={comparison.get('published_value')}, "
                    f"reproduced={comparison.get('reproduced_value')}, "
                    f"difference={comparison.get('absolute_difference')})"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Ambiguities", ""])
        lines.extend(f"- {item}" for item in self.ambiguity_notes)
        if not self.ambiguity_notes:
            lines.append("- None")
        return "\n".join(lines) + "\n"


def provisional_reproduction_report(
    *,
    configuration_hash: str,
    dataset_hashes: tuple[str, ...],
    sample_flow: Sequence[dict[str, object]],
    profiles: Sequence[QuantileProfileFit],
    profile_validations: Sequence[ProfileValidationReport],
    cash_flows: Sequence[QuantileIRRResult],
    comparisons: Sequence[dict[str, object]],
    blockers: tuple[str, ...],
    ambiguity_notes: tuple[str, ...],
) -> ReproductionReport:
    """Build a report that cannot accidentally certify provisional fixture results."""
    if not blockers:
        raise ValueError("a provisional reproduction report must name its evidence blockers")
    return ReproductionReport(
        "reproduction-report-v1",
        CertificationStatus.PROVISIONAL,
        configuration_hash,
        dataset_hashes,
        blockers,
        ambiguity_notes,
        tuple(sample_flow),
        tuple(profiles),
        tuple(profile_validations),
        tuple(cash_flows),
        tuple(comparisons),
    )
