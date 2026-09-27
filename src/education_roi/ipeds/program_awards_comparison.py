"""Review one exact C2022_A→C2023_A program award key across verified tables."""

import json
import math
import tempfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import Field

from education_roi.ipeds.identity import (
    InstitutionHistory,
    InstitutionPairingReport,
    InstitutionRelationship,
    pair_unitids,
)
from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict, _publish_immutable
from education_roi.ipeds.program_awards_evidence import (
    IPEDSProgramAwardsTableError,
    ProgramAwardEvidence,
    resolve_program_awards_evidence,
)
from education_roi.provenance.integrity import sha256_file
from education_roi.scenarios.models import StrictModel


class IPEDSProgramAwardsComparisonError(ValueError):
    """The reviewed releases, key, or table evidence are incompatible."""


class ProgramAwardKeyComparison(StrictModel):
    status: str
    source_unitid: int = Field(gt=0)
    target_unitid: int = Field(gt=0)
    cip_code: str
    major_number: int
    award_level: int
    relative_count_threshold: float = Field(gt=0)
    previous: ProgramAwardEvidence
    current: ProgramAwardEvidence
    institution_pairing: InstitutionPairingReport
    absolute_count_change: int | None
    relative_count_change: float | None
    review_reasons: tuple[str, ...]
    interpretation: str = (
        "Awards are counts from distinct reporting periods, not distinct graduates, "
        "completion probabilities, or a causal change in program quality."
    )


def compare_program_award_key(
    previous_table: Path,
    current_table: Path,
    unitid: int,
    cip_code: str,
    major_number: int,
    award_level: int,
    *,
    target_unitid: int | None = None,
    relative_count_threshold: float = 0.25,
    institution_history: InstitutionHistory | None = None,
) -> ProgramAwardKeyComparison:
    """Compare only a compatible exact key after full-table and identity verification."""
    if not math.isfinite(relative_count_threshold) or relative_count_threshold <= 0:
        raise ValueError("relative count threshold must be positive")
    target = target_unitid if target_unitid is not None else unitid
    try:
        previous = resolve_program_awards_evidence(
            previous_table, unitid, cip_code, major_number, award_level
        )
        current = resolve_program_awards_evidence(
            current_table, target, cip_code, major_number, award_level
        )
    except IPEDSProgramAwardsTableError as error:
        raise IPEDSProgramAwardsComparisonError(str(error)) from error
    if (
        previous.release_id != "2022-23-final"
        or current.release_id != "2023-24-final"
        or previous.cip_version != "2020"
        or current.cip_version != "2020"
        or (previous.period_start, previous.period_end) != ("2021-07-01", "2022-06-30")
        or (current.period_start, current.period_end) != ("2022-07-01", "2023-06-30")
    ):
        raise IPEDSProgramAwardsComparisonError("requires ordered, compatible C2022_A/C2023_A")
    pairing = pair_unitids(
        (unitid,),
        (target,),
        previous.release_id,
        current.release_id,
        history=institution_history,
    )
    reasons = []
    comparable = (
        len(pairing.pairings) == 1
        and not pairing.findings
        and pairing.pairings[0].relationship is InstitutionRelationship.CONTINUING
        and not pairing.pairings[0].review_required
    )
    if not comparable:
        reasons.append("institution identity or target coverage requires review")
    if previous.status != "OBSERVED" or current.status != "OBSERVED":
        reasons.append("an exact program award count is unavailable in one release")
    if previous.source_status != current.source_status:
        reasons.append("source imputation status changed across releases")
    if previous.source_status_review_required or current.source_status_review_required:
        reasons.append("a source imputation status requires review")
    absolute = None
    relative = None
    if comparable and previous.award_count is not None and current.award_count is not None:
        absolute = current.award_count - previous.award_count
        relative = abs(absolute) / previous.award_count if previous.award_count > 0 else None
        if absolute != 0 and (relative is None or relative >= relative_count_threshold):
            reasons.append("relative award-count change meets review threshold")
    return ProgramAwardKeyComparison(
        status="REVIEW_REQUIRED" if reasons else "ACCEPTABLE",
        source_unitid=unitid,
        target_unitid=target,
        cip_code=cip_code,
        major_number=major_number,
        award_level=award_level,
        relative_count_threshold=relative_count_threshold,
        previous=previous,
        current=current,
        institution_pairing=pairing,
        absolute_count_change=absolute,
        relative_count_change=relative,
        review_reasons=tuple(reasons),
    )


def compare_program_award_tables(
    previous_table: Path,
    current_table: Path,
    output: Path,
    *,
    relative_count_threshold: float = 0.25,
    institution_history: InstitutionHistory | None = None,
) -> dict[str, object]:
    """Write deterministic JSONL review findings for every comparable exact key."""
    if not math.isfinite(relative_count_threshold) or relative_count_threshold <= 0:
        raise ValueError("relative count threshold must be positive")
    if output.exists() and not output.is_file():
        raise ValueError("output must be a file path")
    try:
        # The resolver checks every row, the full schema, source cells and sidecar.
        previous_first = pl.read_parquet(
            previous_table, columns=["unitid", "cip_code", "major_number", "award_level"]
        ).row(0)
        current_first = pl.read_parquet(
            current_table, columns=["unitid", "cip_code", "major_number", "award_level"]
        ).row(0)
        previous = resolve_program_awards_evidence(previous_table, *previous_first)
        current = resolve_program_awards_evidence(current_table, *current_first)
        if (previous.release_id, current.release_id) != ("2022-23-final", "2023-24-final"):
            raise IPEDSProgramAwardsComparisonError("requires ordered, compatible C2022_A/C2023_A")
        columns = [
            "unitid",
            "cip_code",
            "major_number",
            "award_level",
            "award_count",
            "source_status",
            "unavailable_reason",
        ]
        earlier = pl.read_parquet(previous_table, columns=columns)
        later = pl.read_parquet(current_table, columns=columns)
        if (
            sha256_file(previous_table)[0] != previous.table_sha256
            or sha256_file(current_table)[0] != current.table_sha256
        ):
            raise IPEDSProgramAwardsComparisonError("program table changed during comparison")
    except (IPEDSProgramAwardsTableError, OSError, IndexError, pl.exceptions.PolarsError) as error:
        raise IPEDSProgramAwardsComparisonError(str(error)) from error
    pairing = pair_unitids(
        tuple(earlier["unitid"].unique().to_list()),
        tuple(later["unitid"].unique().to_list()),
        previous.release_id,
        current.release_id,
        history=institution_history,
    )
    comparable = {
        item.source_unitid
        for item in pairing.pairings
        if item.relationship is InstitutionRelationship.CONTINUING
        and not item.review_required
        and item.source_unitid == item.target_unitid
    }
    counts: Counter[str] = Counter()
    compared = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        temporary = Path(directory) / "findings.jsonl"
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:

            def emit(kind: str, **details: object) -> None:
                counts[kind] += 1
                stream.write(
                    json.dumps(
                        {"finding_type": kind, **details}, sort_keys=True, separators=(",", ":")
                    )
                    + "\n"
                )

            for item in pairing.findings:
                emit(
                    "institution_" + item.finding_type.value,
                    source_unitids=item.source_unitids,
                    target_unitids=item.target_unitids,
                    reason=item.reason,
                )
            for paired in pairing.pairings:
                if paired.source_unitid not in comparable:
                    emit(
                        "institution_pairing_review",
                        source_unitids=[paired.source_unitid],
                        target_unitids=[paired.target_unitid],
                        relationship=paired.relationship.value,
                        confidence=paired.confidence.value,
                    )

            def keys(frame: pl.DataFrame) -> Iterator[dict[str, Any]]:
                return iter(frame.filter(pl.col("unitid").is_in(comparable)).iter_rows(named=True))

            left, right = keys(earlier), keys(later)
            a, b = next(left, None), next(right, None)

            def key(row: dict[str, Any]) -> tuple[Any, ...]:
                return tuple(
                    row[name] for name in ("unitid", "cip_code", "major_number", "award_level")
                )

            while a is not None or b is not None:
                ak, bk = key(a) if a is not None else None, key(b) if b is not None else None
                if a is not None and (b is None or (ak is not None and bk is not None and ak < bk)):
                    emit(
                        "program_removed",
                        unitid=a["unitid"],
                        cip_code=a["cip_code"],
                        major_number=a["major_number"],
                        award_level=a["award_level"],
                        previous_count=a["award_count"],
                    )
                    a = next(left, None)
                elif b is not None and (
                    a is None or (ak is not None and bk is not None and bk < ak)
                ):
                    emit(
                        "program_added",
                        unitid=b["unitid"],
                        cip_code=b["cip_code"],
                        major_number=b["major_number"],
                        award_level=b["award_level"],
                        current_count=b["award_count"],
                    )
                    b = next(right, None)
                else:
                    assert a is not None and b is not None
                    compared += 1
                    details = dict(
                        unitid=a["unitid"],
                        cip_code=a["cip_code"],
                        major_number=a["major_number"],
                        award_level=a["award_level"],
                        previous_count=a["award_count"],
                        current_count=b["award_count"],
                        previous_status=a["source_status"],
                        current_status=b["source_status"],
                    )
                    if a["award_count"] is None or b["award_count"] is None:
                        emit("count_unavailable", **details)
                    if a["source_status"] != b["source_status"]:
                        emit("source_status_changed", **details)
                    if a["source_status"] not in (None, "R") or b["source_status"] not in (
                        None,
                        "R",
                    ):
                        emit("source_status_review", **details)
                    if a["award_count"] is not None and b["award_count"] is not None:
                        delta = b["award_count"] - a["award_count"]
                        relative = abs(delta) / a["award_count"] if a["award_count"] > 0 else None
                        if delta and (relative is None or relative >= relative_count_threshold):
                            emit(
                                "count_change",
                                **details,
                                absolute_change=delta,
                                relative_change=relative,
                            )
                    a, b = next(left, None), next(right, None)
        try:
            _publish_immutable(temporary, output)
        except IPEDSProcessedArtifactConflict as error:
            raise IPEDSProgramAwardsComparisonError(str(error)) from error
    return {
        "status": "REVIEW_REQUIRED" if counts else "ACCEPTABLE",
        "previous_table_sha256": previous.table_sha256,
        "previous_manifest_sha256": previous.manifest_sha256,
        "current_table_sha256": current.table_sha256,
        "current_manifest_sha256": current.manifest_sha256,
        "relative_count_threshold": relative_count_threshold,
        "institution_source_count": pairing.source_count,
        "institution_target_count": pairing.target_count,
        "comparable_institution_count": len(comparable),
        "history_id": pairing.history_id,
        "history_sha256": pairing.history_sha256,
        "compared_program_keys": compared,
        "findings_by_type": dict(sorted(counts.items())),
        "findings_count": sum(counts.values()),
        "findings_path": str(output),
        "findings_sha256": sha256_file(output)[0],
        "interpretation": (
            "Awards count distinct reporting periods, not distinct graduates "
            "or causal program quality changes."
        ),
    }
