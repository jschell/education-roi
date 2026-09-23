"""Versioned institution identity history without inferred UNITID continuity."""

from enum import StrEnum
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from pydantic import Field, HttpUrl, field_validator, model_validator

from education_roi.scenarios.models import StrictModel


class InstitutionHistoryError(ValueError):
    """Institution identity evidence is missing, incompatible, or ambiguous."""


class InstitutionRelationship(StrEnum):
    CONTINUING = "continuing"
    ID_CHANGED = "id_changed"
    MERGED = "merged"
    SPLIT = "split"
    CLOSED = "closed"


class InstitutionMappingConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InstitutionHistoryEntry(StrictModel):
    source_unitid: int = Field(gt=0)
    target_unitid: int | None = Field(default=None, gt=0)
    relationship: InstitutionRelationship
    confidence: InstitutionMappingConfidence
    note: str | None = None

    @model_validator(mode="after")
    def target_matches_relationship(self) -> Self:
        if self.relationship is InstitutionRelationship.CLOSED:
            if self.target_unitid is not None:
                raise ValueError("closed institution history entries cannot have a target UNITID")
        elif self.target_unitid is None:
            raise ValueError("non-closure institution history entries require a target UNITID")
        return self


class InstitutionHistory(StrictModel):
    """One immutable, directional history between exact IPEDS releases."""

    history_id: str = Field(min_length=1)
    source_release: str = Field(min_length=1)
    target_release: str = Field(min_length=1)
    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: tuple[InstitutionHistoryEntry, ...] = Field(min_length=1)

    @field_validator("source_url")
    @classmethod
    def require_official_nces_source(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlparse(str(value))
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not (host == "nces.ed.gov" or host.endswith(".nces.ed.gov")):
            raise ValueError("institution history source must use HTTPS on an official NCES domain")
        return value

    @model_validator(mode="after")
    def validate_direction_and_entries(self) -> Self:
        if self.source_release == self.target_release:
            raise ValueError("institution history source and target releases must differ")
        keys = [
            (entry.source_unitid, entry.target_unitid, entry.relationship) for entry in self.entries
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("institution history contains duplicate entries")
        return self

    @classmethod
    def from_file(cls, path: Path) -> Self:
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise InstitutionHistoryError(f"invalid institution history {path}: {error}") from error


class InstitutionResolutionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class InstitutionResolution(StrictModel):
    source_unitid: int = Field(gt=0)
    source_release: str
    target_unitid: int | None = Field(default=None, gt=0)
    target_release: str
    relationship: InstitutionRelationship
    confidence: InstitutionMappingConfidence
    status: InstitutionResolutionStatus
    history_id: str | None = None
    history_sha256: str | None = None
    review_required: bool


class InstitutionPairingFindingType(StrEnum):
    ADDED = "added"
    MISSING_HISTORY = "missing_history"
    CLOSED = "closed"
    AMBIGUOUS_HISTORY = "ambiguous_history"
    TARGET_MISSING = "target_missing"
    TARGET_COLLISION = "target_collision"


class InstitutionPairing(StrictModel):
    source_unitid: int = Field(gt=0)
    target_unitid: int = Field(gt=0)
    relationship: InstitutionRelationship
    confidence: InstitutionMappingConfidence
    review_required: bool


class InstitutionPairingFinding(StrictModel):
    finding_type: InstitutionPairingFindingType
    source_unitids: tuple[int, ...] = ()
    target_unitids: tuple[int, ...] = ()
    review_required: bool = True
    reason: str


class InstitutionPairingReport(StrictModel):
    source_release: str
    target_release: str
    source_count: int = Field(ge=0)
    target_count: int = Field(ge=0)
    history_id: str | None = None
    history_sha256: str | None = None
    pairings: tuple[InstitutionPairing, ...]
    findings: tuple[InstitutionPairingFinding, ...]
    review_required: bool


def resolve_unitid(
    source_unitid: int,
    source_release: str,
    target_release: str,
    *,
    history: InstitutionHistory | None = None,
    target_unitid: int | None = None,
) -> InstitutionResolution:
    """Resolve one UNITID using exact directional history and explicit disambiguation."""
    if source_release == target_release:
        if history is not None or (target_unitid is not None and target_unitid != source_unitid):
            raise InstitutionHistoryError(
                "same-release institution resolution must preserve the source UNITID"
            )
        return InstitutionResolution(
            source_unitid=source_unitid,
            source_release=source_release,
            target_unitid=source_unitid,
            target_release=target_release,
            relationship=InstitutionRelationship.CONTINUING,
            confidence=InstitutionMappingConfidence.HIGH,
            status=InstitutionResolutionStatus.ACTIVE,
            review_required=False,
        )
    if history is None:
        raise InstitutionHistoryError(
            f"UNITID resolution from {source_release} to {target_release} requires explicit history"
        )
    if (history.source_release, history.target_release) != (source_release, target_release):
        raise InstitutionHistoryError(
            "institution history direction does not match requested releases"
        )
    matches = tuple(entry for entry in history.entries if entry.source_unitid == source_unitid)
    if target_unitid is not None:
        matches = tuple(entry for entry in matches if entry.target_unitid == target_unitid)
    if not matches:
        raise InstitutionHistoryError(
            f"institution history has no entry for UNITID {source_unitid}"
        )
    if len(matches) != 1:
        targets = ", ".join(
            "closed" if entry.target_unitid is None else str(entry.target_unitid)
            for entry in sorted(matches, key=lambda item: item.target_unitid or 0)
        )
        raise InstitutionHistoryError(
            f"UNITID {source_unitid} history is ambiguous; choose one target: {targets}"
        )
    entry = matches[0]
    closed = entry.relationship is InstitutionRelationship.CLOSED
    return InstitutionResolution(
        source_unitid=source_unitid,
        source_release=source_release,
        target_unitid=entry.target_unitid,
        target_release=target_release,
        relationship=entry.relationship,
        confidence=entry.confidence,
        status=(
            InstitutionResolutionStatus.CLOSED if closed else InstitutionResolutionStatus.ACTIVE
        ),
        history_id=history.history_id,
        history_sha256=history.source_sha256,
        review_required=(
            entry.relationship is not InstitutionRelationship.CONTINUING
            or entry.confidence is not InstitutionMappingConfidence.HIGH
        ),
    )


def pair_unitids(
    source_unitids: tuple[int, ...],
    target_unitids: tuple[int, ...],
    source_release: str,
    target_release: str,
    *,
    history: InstitutionHistory | None = None,
) -> InstitutionPairingReport:
    """Pair cross-release UNITIDs without aggregating ambiguous institution histories."""
    if source_release == target_release:
        raise InstitutionHistoryError("institution pairing requires different releases")
    if len(source_unitids) != len(set(source_unitids)) or len(target_unitids) != len(
        set(target_unitids)
    ):
        raise InstitutionHistoryError("institution pairing inputs contain duplicate UNITIDs")
    if any(unitid <= 0 for unitid in (*source_unitids, *target_unitids)):
        raise InstitutionHistoryError("institution pairing inputs require positive UNITIDs")
    if history is not None and (history.source_release, history.target_release) != (
        source_release,
        target_release,
    ):
        raise InstitutionHistoryError(
            "institution history direction does not match requested releases"
        )

    target_set = set(target_unitids)
    entries_by_source: dict[int, list[InstitutionHistoryEntry]] = {}
    if history is not None:
        for entry in history.entries:
            entries_by_source.setdefault(entry.source_unitid, []).append(entry)

    candidates: dict[int, list[InstitutionPairing]] = {}
    findings: list[InstitutionPairingFinding] = []
    for source_unitid in sorted(source_unitids):
        entries = entries_by_source.get(source_unitid, [])
        if not entries:
            if source_unitid in target_set:
                candidates.setdefault(source_unitid, []).append(
                    InstitutionPairing(
                        source_unitid=source_unitid,
                        target_unitid=source_unitid,
                        relationship=InstitutionRelationship.CONTINUING,
                        confidence=InstitutionMappingConfidence.HIGH,
                        review_required=False,
                    )
                )
            else:
                findings.append(
                    InstitutionPairingFinding(
                        finding_type=InstitutionPairingFindingType.MISSING_HISTORY,
                        source_unitids=(source_unitid,),
                        reason="source UNITID is absent from target release without history",
                    )
                )
            continue
        if len(entries) != 1:
            findings.append(
                InstitutionPairingFinding(
                    finding_type=InstitutionPairingFindingType.AMBIGUOUS_HISTORY,
                    source_unitids=(source_unitid,),
                    target_unitids=tuple(
                        sorted(
                            entry.target_unitid
                            for entry in entries
                            if entry.target_unitid is not None
                        )
                    ),
                    reason="history has multiple targets; automatic aggregation is prohibited",
                )
            )
            continue
        entry = entries[0]
        if entry.relationship is InstitutionRelationship.CLOSED:
            findings.append(
                InstitutionPairingFinding(
                    finding_type=InstitutionPairingFindingType.CLOSED,
                    source_unitids=(source_unitid,),
                    reason="authoritative history explicitly marks the institution closed",
                )
            )
            continue
        assert entry.target_unitid is not None
        if entry.target_unitid not in target_set:
            findings.append(
                InstitutionPairingFinding(
                    finding_type=InstitutionPairingFindingType.TARGET_MISSING,
                    source_unitids=(source_unitid,),
                    target_unitids=(entry.target_unitid,),
                    reason="history target UNITID is absent from the target table",
                )
            )
            continue
        candidates.setdefault(entry.target_unitid, []).append(
            InstitutionPairing(
                source_unitid=source_unitid,
                target_unitid=entry.target_unitid,
                relationship=entry.relationship,
                confidence=entry.confidence,
                review_required=(
                    entry.relationship is not InstitutionRelationship.CONTINUING
                    or entry.confidence is not InstitutionMappingConfidence.HIGH
                ),
            )
        )

    pairings: list[InstitutionPairing] = []
    for target_unitid, target_candidates in sorted(candidates.items()):
        if len(target_candidates) == 1:
            pairings.append(target_candidates[0])
            continue
        findings.append(
            InstitutionPairingFinding(
                finding_type=InstitutionPairingFindingType.TARGET_COLLISION,
                source_unitids=tuple(
                    sorted(candidate.source_unitid for candidate in target_candidates)
                ),
                target_unitids=(target_unitid,),
                reason=(
                    "multiple source UNITIDs map to one target; automatic aggregation is prohibited"
                ),
            )
        )

    paired_targets = {pairing.target_unitid for pairing in pairings}
    for target_unitid in sorted(target_set.difference(paired_targets)):
        findings.append(
            InstitutionPairingFinding(
                finding_type=InstitutionPairingFindingType.ADDED,
                target_unitids=(target_unitid,),
                reason="target UNITID has no unambiguous source pairing",
            )
        )
    ordered_findings = tuple(
        sorted(
            findings,
            key=lambda item: (
                item.finding_type.value,
                item.source_unitids,
                item.target_unitids,
            ),
        )
    )
    ordered_pairings = tuple(sorted(pairings, key=lambda item: item.source_unitid))
    return InstitutionPairingReport(
        source_release=source_release,
        target_release=target_release,
        source_count=len(source_unitids),
        target_count=len(target_unitids),
        history_id=history.history_id if history is not None else None,
        history_sha256=history.source_sha256 if history is not None else None,
        pairings=ordered_pairings,
        findings=ordered_findings,
        review_required=(
            bool(ordered_findings) or any(pairing.review_required for pairing in ordered_pairings)
        ),
    )
