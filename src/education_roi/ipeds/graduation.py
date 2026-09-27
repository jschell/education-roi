"""Pinned GR2023 four-year bachelor's graduation observations."""

import csv
import io
from enum import StrEnum
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from pydantic import Field, model_validator

from education_roi.ipeds.catalog import IPEDSComponent, IPEDSPublicationStatus, IPEDSRelease
from education_roi.ipeds.completion import (
    GraduationAwardOutcome,
    GraduationCohortScope,
    IPEDSGraduationObservation,
)
from education_roi.ipeds.dictionary import _xlsx_rows
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ApprovalState, ArtifactManifest
from education_roi.scenarios.models import StrictModel

GR2023_DATASET_ID = "ipeds-graduation-rates"
GR2023_DICTIONARY_DATASET_ID = "ipeds-graduation-rates-dictionary"
REQUIRED_GR_COLUMNS = frozenset(
    {"UNITID", "GRTYPE", "CHRTSTAT", "SECTION", "COHORT", "LINE", "GRTOTLT", "XGRTOTLT"}
)
ROW_CODES = {"8": ("12", "50"), "12": ("16", "18A")}
TWO_YEAR_ROW_CODES = {"29": ("12", "50"), "30": ("13", "29A")}


class IPEDSGraduationError(ValueError):
    """An exact GR release lacks the expected dictionary, rows, or lineage."""


class IPEDSGraduationStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class IPEDSGraduationResolution(StrictModel):
    unitid: int = Field(gt=0)
    release_id: str
    status: IPEDSGraduationStatus
    observation: IPEDSGraduationObservation | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def consistent_status(self) -> "IPEDSGraduationResolution":
        if self.status is IPEDSGraduationStatus.AVAILABLE and self.observation is None:
            raise ValueError("available graduation evidence requires an observation")
        if self.status is IPEDSGraduationStatus.INSUFFICIENT_DATA and not self.reason:
            raise ValueError("insufficient graduation evidence requires a reason")
        return self


def _verify_manifest(
    path: Path, manifest: ArtifactManifest, release: IPEDSRelease, dataset_id: str, url: str
) -> None:
    if (
        manifest.dataset_id != dataset_id
        or manifest.release != release.release_id
        or manifest.publication_status != release.publication_status.value
        or str(manifest.source_url) != url
        or str(manifest.final_url) != url
        or manifest.state not in {ApprovalState.VALIDATED, ApprovalState.APPROVED}
    ):
        raise IPEDSGraduationError("graduation artifact is not validated for this exact release")
    if sha256_file(path) != (manifest.sha256, manifest.file_size):
        raise IPEDSGraduationError("graduation artifact bytes do not match their manifest")


def _verify_dictionary(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            if archive.namelist() != ["gr2023.xlsx"]:
                raise IPEDSGraduationError("GR2023 dictionary must contain gr2023.xlsx")
            rows = _xlsx_rows(archive.read("gr2023.xlsx"))
    except (OSError, BadZipFile, KeyError, UnicodeError, ValueError) as error:
        raise IPEDSGraduationError(f"could not read GR2023 dictionary: {error}") from error
    labels = {
        (row[0], row[2]): row[7]
        for row in rows
        if len(row) >= 8 and row[0] == "GRTYPE" and row[3] == "gr2023_RV"
    }
    if not (
        any("Final/revised release" in cell for row in rows for cell in row)
        and "Adjusted cohort" in labels.get(("GRTYPE", "8"), "")
        and "bachelor's or equivalent degrees total" in labels.get(("GRTYPE", "12"), "")
        and (REQUIRED_GR_COLUMNS - {"XGRTOTLT"}).issubset(
            {row[1] for row in rows if len(row) >= 2 and row[0].isdigit()}
        )
        and any(len(row) >= 6 and row[1] == "GRTOTLT" and row[5] == "XGRTOTLT" for row in rows)
    ):
        raise IPEDSGraduationError("GR2023 dictionary does not support the selected final rows")


def _target_rows(archive_path: Path, member: str, unitid: int) -> dict[str, dict[str, str]]:
    try:
        with ZipFile(archive_path) as archive:
            if member not in archive.namelist():
                raise IPEDSGraduationError(f"GR2023 archive is missing {member}")
            with archive.open(member) as stream:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
                missing = REQUIRED_GR_COLUMNS.difference(reader.fieldnames or ())
                if missing:
                    raise IPEDSGraduationError(
                        "GR2023 archive is missing columns: " + ", ".join(sorted(missing))
                    )
                selected: dict[str, dict[str, str]] = {}
                for row in reader:
                    if row["UNITID"] != str(unitid) or row["GRTYPE"] not in ROW_CODES:
                        continue
                    code = row["GRTYPE"]
                    status, line = ROW_CODES[code]
                    if (row["CHRTSTAT"], row["SECTION"], row["COHORT"], row["LINE"]) != (
                        status,
                        "2",
                        "2",
                        line,
                    ):
                        raise IPEDSGraduationError(
                            f"GR2023 row {code} has incompatible cohort keys"
                        )
                    if code in selected:
                        raise IPEDSGraduationError(
                            f"duplicate GR2023 row {code} for UNITID {unitid}"
                        )
                    selected[code] = row
                return selected
    except (OSError, BadZipFile, UnicodeError, csv.Error) as error:
        raise IPEDSGraduationError(f"could not read GR2023 archive: {error}") from error


def validate_gr2023_archive(path: Path, member: str, *, strip_codes: bool = False) -> int:
    """Stream the selected cohort rows; legacy 2022 codes require explicit trimming."""
    seen: set[tuple[int, str]] = set()
    try:
        with ZipFile(path) as archive:
            if member not in archive.namelist():
                raise IPEDSGraduationError(f"GR2023 archive is missing {member}")
            with archive.open(member) as stream:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
                missing = REQUIRED_GR_COLUMNS.difference(reader.fieldnames or ())
                if missing:
                    raise IPEDSGraduationError(
                        "GR2023 archive is missing columns: " + ", ".join(sorted(missing))
                    )
                for number, row in enumerate(reader, start=2):
                    code = (row["GRTYPE"] or "").strip() if strip_codes else row["GRTYPE"]
                    section = (row["SECTION"] or "").strip() if strip_codes else row["SECTION"]
                    if code not in ROW_CODES or section != "2":
                        continue
                    try:
                        unitid = int(row["UNITID"])
                    except (TypeError, ValueError) as error:
                        raise IPEDSGraduationError(
                            f"invalid GR2023 UNITID on row {number}"
                        ) from error
                    if unitid <= 0:
                        raise IPEDSGraduationError(f"invalid GR2023 UNITID on row {number}")
                    status, line = ROW_CODES[code]
                    row_keys = (row["CHRTSTAT"], row["COHORT"], row["LINE"])
                    if strip_codes:
                        row_keys = (
                            (row_keys[0] or "").strip(),
                            (row_keys[1] or "").strip(),
                            (row_keys[2] or "").strip(),
                        )
                    if row_keys != (status, "2", line):
                        raise IPEDSGraduationError(
                            f"incompatible GR2023 cohort keys on row {number}"
                        )
                    key = (unitid, code)
                    if key in seen:
                        raise IPEDSGraduationError(
                            f"duplicate GR2023 row {code} for UNITID {unitid}"
                        )
                    seen.add(key)
    except (OSError, BadZipFile, UnicodeError, csv.Error) as error:
        raise IPEDSGraduationError(f"could not read GR2023 archive: {error}") from error
    if not seen:
        raise IPEDSGraduationError("GR2023 archive has no bachelor's cohort rows")
    return len(seen)


def resolve_gr2023_bachelors(
    archive_path: Path,
    dictionary_path: Path,
    release: IPEDSRelease,
    archive_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    unitid: int,
) -> IPEDSGraduationResolution:
    """Resolve bachelor's awards/adjusted bachelor's-seeking cohort for one institution."""
    if unitid <= 0:
        raise IPEDSGraduationError("UNITID must be positive")
    if (
        release.component is not IPEDSComponent.GRADUATION_RATES
        or release.release_id != "2023-24-final"
        or release.publication_status is not IPEDSPublicationStatus.FINAL
        or release.data_member != "gr2023_RV.csv"
    ):
        raise IPEDSGraduationError("resolver requires the pinned final GR2023_RV release")
    _verify_manifest(
        archive_path, archive_manifest, release, GR2023_DATASET_ID, str(release.data_url)
    )
    _verify_manifest(
        dictionary_path,
        dictionary_manifest,
        release,
        GR2023_DICTIONARY_DATASET_ID,
        str(release.dictionary_url),
    )
    _verify_dictionary(dictionary_path)
    rows = _target_rows(archive_path, release.data_member, unitid)
    if rows.keys() != ROW_CODES.keys():
        return IPEDSGraduationResolution(
            unitid=unitid,
            release_id=release.release_id,
            status=IPEDSGraduationStatus.INSUFFICIENT_DATA,
            reason="bachelor's adjusted cohort or bachelor's award row is missing",
        )
    if any(not rows[code]["GRTOTLT"].strip() for code in ROW_CODES):
        return IPEDSGraduationResolution(
            unitid=unitid,
            release_id=release.release_id,
            status=IPEDSGraduationStatus.INSUFFICIENT_DATA,
            reason="GR2023 total count is blank",
        )
    try:
        denominator, numerator = (int(rows[code]["GRTOTLT"]) for code in ROW_CODES)
    except (ValueError, TypeError) as error:
        raise IPEDSGraduationError("GR2023 total count is not an integer") from error
    if denominator < 0 or numerator < 0:
        return IPEDSGraduationResolution(
            unitid=unitid,
            release_id=release.release_id,
            status=IPEDSGraduationStatus.INSUFFICIENT_DATA,
            reason="GR2023 total count contains a negative sentinel",
        )
    if numerator > denominator:
        raise IPEDSGraduationError("GR2023 bachelor's awards exceed adjusted cohort")
    return IPEDSGraduationResolution(
        unitid=unitid,
        release_id=release.release_id,
        status=IPEDSGraduationStatus.AVAILABLE,
        observation=IPEDSGraduationObservation(
            unitid=unitid,
            release_id=release.release_id,
            publication_status=release.publication_status,
            component=release.component,
            cohort_year=2017,
            cohort_scope=GraduationCohortScope.BACHELORS_SEEKING,
            award_outcome=GraduationAwardOutcome.BACHELORS_DEGREE,
            normal_time_percent=150,
            adjusted_cohort=denominator,
            completers=numerator,
            source_artifact_id=archive_manifest.artifact_id,
            dictionary_artifact_id=dictionary_manifest.artifact_id,
            source_columns=("GRTOTLT[GRTYPE=8]", "GRTOTLT[GRTYPE=12]"),
            source_row_keys=("COHORT=2;SECTION=2;GRTYPE=8", "COHORT=2;SECTION=2;GRTYPE=12"),
            source_statuses=(rows["8"]["XGRTOTLT"], rows["12"]["XGRTOTLT"]),
        ),
    )


def resolve_gr2023_two_year_any_award(
    archive_path: Path,
    dictionary_path: Path,
    release: IPEDSRelease,
    archive_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    unitid: int,
) -> IPEDSGraduationResolution:
    """Resolve the 2020 two-year entrant cohort's any-award 150% outcome."""
    if unitid <= 0:
        raise IPEDSGraduationError("UNITID must be positive")
    if (
        release.component is not IPEDSComponent.GRADUATION_RATES
        or release.release_id != "2023-24-final"
        or release.publication_status is not IPEDSPublicationStatus.FINAL
        or release.data_member != "gr2023_RV.csv"
    ):
        raise IPEDSGraduationError("resolver requires the pinned final GR2023_RV release")
    _verify_manifest(
        archive_path, archive_manifest, release, GR2023_DATASET_ID, str(release.data_url)
    )
    _verify_manifest(
        dictionary_path,
        dictionary_manifest,
        release,
        GR2023_DICTIONARY_DATASET_ID,
        str(release.dictionary_url),
    )
    _verify_dictionary(dictionary_path)
    try:
        with ZipFile(dictionary_path) as archive:
            rows = _xlsx_rows(archive.read("gr2023.xlsx"))
    except (OSError, BadZipFile, KeyError, UnicodeError, ValueError) as error:
        raise IPEDSGraduationError(f"could not read GR2023 dictionary: {error}") from error
    labels = {
        row[2]: row[7]
        for row in rows
        if len(row) >= 8 and row[0] == "GRTYPE" and row[3] == "gr2023_RV"
    }
    if (
        "Adjusted cohort" not in labels.get("29", "")
        or "Completers within 150% of normal time total" not in labels.get("30", "")
        or "2-year institutions" not in labels.get("27", "")
    ):
        raise IPEDSGraduationError("GR2023 dictionary does not support the two-year cohort")
    selected: dict[str, dict[str, str]] = {}
    seen: set[tuple[int, str]] = set()
    try:
        with ZipFile(archive_path) as archive:
            if release.data_member not in archive.namelist():
                raise IPEDSGraduationError(f"GR2023 archive is missing {release.data_member}")
            stream = archive.open(release.data_member)
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
            if REQUIRED_GR_COLUMNS.difference(reader.fieldnames or ()):
                raise IPEDSGraduationError("GR2023 archive is missing required columns")
            for number, row in enumerate(reader, start=2):
                code = row["GRTYPE"]
                if code not in TWO_YEAR_ROW_CODES or row["SECTION"] != "4":
                    continue
                try:
                    source_unitid = int(row["UNITID"])
                except (TypeError, ValueError) as error:
                    raise IPEDSGraduationError(
                        f"invalid two-year UNITID on row {number}"
                    ) from error
                status, line = TWO_YEAR_ROW_CODES[code]
                if source_unitid <= 0 or (row["CHRTSTAT"], row["COHORT"], row["LINE"]) != (
                    status,
                    "4",
                    line,
                ):
                    raise IPEDSGraduationError(f"incompatible two-year cohort keys on row {number}")
                key = (source_unitid, code)
                if key in seen:
                    raise IPEDSGraduationError(f"duplicate two-year cohort row on row {number}")
                if row["GRTOTLT"] is None or row["XGRTOTLT"] is None:
                    raise IPEDSGraduationError(f"malformed two-year count row {number}")
                seen.add(key)
                if source_unitid == unitid:
                    selected[code] = row
    except (OSError, BadZipFile, UnicodeError, csv.Error) as error:
        raise IPEDSGraduationError(f"could not read GR2023 archive: {error}") from error
    if not seen:
        raise IPEDSGraduationError("GR2023 archive has no two-year cohort rows")
    if selected.keys() != TWO_YEAR_ROW_CODES.keys():
        return IPEDSGraduationResolution(
            unitid=unitid,
            release_id=release.release_id,
            status=IPEDSGraduationStatus.INSUFFICIENT_DATA,
            reason="two-year adjusted cohort or any-award row is missing",
        )
    raw = [selected[code]["GRTOTLT"].strip() for code in TWO_YEAR_ROW_CODES]
    if not all(raw):
        return IPEDSGraduationResolution(
            unitid=unitid,
            release_id=release.release_id,
            status=IPEDSGraduationStatus.INSUFFICIENT_DATA,
            reason="GR2023 two-year count is blank",
        )
    try:
        denominator, numerator = (int(value) for value in raw)
    except ValueError as error:
        raise IPEDSGraduationError("GR2023 two-year count is not an integer") from error
    if denominator < 0 or numerator < 0:
        return IPEDSGraduationResolution(
            unitid=unitid,
            release_id=release.release_id,
            status=IPEDSGraduationStatus.INSUFFICIENT_DATA,
            reason="GR2023 two-year count contains a negative sentinel",
        )
    if numerator > denominator:
        raise IPEDSGraduationError("GR2023 two-year awards exceed adjusted cohort")
    return IPEDSGraduationResolution(
        unitid=unitid,
        release_id=release.release_id,
        status=IPEDSGraduationStatus.AVAILABLE,
        observation=IPEDSGraduationObservation(
            unitid=unitid,
            release_id=release.release_id,
            publication_status=release.publication_status,
            component=release.component,
            cohort_year=2020,
            cohort_scope=GraduationCohortScope.ALL_DEGREE_OR_CERTIFICATE_SEEKING,
            award_outcome=GraduationAwardOutcome.ANY_AWARD,
            normal_time_percent=150,
            adjusted_cohort=denominator,
            completers=numerator,
            source_artifact_id=archive_manifest.artifact_id,
            dictionary_artifact_id=dictionary_manifest.artifact_id,
            source_columns=("GRTOTLT[GRTYPE=29]", "GRTOTLT[GRTYPE=30]"),
            source_row_keys=("COHORT=4;SECTION=4;GRTYPE=29", "COHORT=4;SECTION=4;GRTYPE=30"),
            source_statuses=(selected["29"]["XGRTOTLT"], selected["30"]["XGRTOTLT"]),
        ),
    )
