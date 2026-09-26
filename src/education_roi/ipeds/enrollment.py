"""Pinned final EF2023A fall enrollment cohort observations."""

import csv
import io
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse
from zipfile import BadZipFile, ZipFile

from pydantic import Field

from education_roi.config.paths import ProjectPaths
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSPublicationStatus, IPEDSRelease
from education_roi.ipeds.dictionary import IPEDSDictionaryError, _xlsx_rows
from education_roi.provenance.downloader import HttpDownloader
from education_roi.provenance.integrity import sha256_file
from education_roi.provenance.models import ApprovalState, ArtifactManifest, DatasetDefinition
from education_roi.provenance.store import ArtifactStore, Registry
from education_roi.scenarios.models import StrictModel

ENROLLMENT_DATA = DatasetDefinition(
    dataset_id="ipeds-fall-enrollment",
    publisher="National Center for Education Statistics",
    name="IPEDS final EF2023A fall enrollment",
    allowed_domains=("nces.ed.gov",),
)
ENROLLMENT_DICTIONARY = DatasetDefinition(
    dataset_id="ipeds-fall-enrollment-dictionary",
    publisher="National Center for Education Statistics",
    name="IPEDS final EF2023A dictionary",
    allowed_domains=("nces.ed.gov",),
)


class EnrollmentCohort(StrEnum):
    ALL_STUDENTS = "all_students"
    FULL_TIME_FIRST_TIME = "full_time_first_time"
    FULL_TIME_TRANSFER_IN = "full_time_transfer_in"
    PART_TIME_FIRST_TIME = "part_time_first_time"
    PART_TIME_TRANSFER_IN = "part_time_transfer_in"


# Exact EFALEVEL, LINE, SECTION, LSTUDY and official revised workbook label.
COHORTS = {
    EnrollmentCohort.ALL_STUDENTS: (
        "1",
        "29",
        "3",
        "4",
        "All students total",
    ),
    EnrollmentCohort.FULL_TIME_FIRST_TIME: (
        "24",
        "1",
        "1",
        "1",
        "Full-time students, Undergraduate, Degree/certificate-seeking, First-time",
    ),
    EnrollmentCohort.FULL_TIME_TRANSFER_IN: (
        "39",
        "2",
        "1",
        "1",
        "Full-time students, Undergraduate, Other degree/certificatee-seeking, Transfer-ins",
    ),
    EnrollmentCohort.PART_TIME_FIRST_TIME: (
        "44",
        "15",
        "2",
        "1",
        "Part-time students, Undergraduate, Degree/certificate-seeking, First-time",
    ),
    EnrollmentCohort.PART_TIME_TRANSFER_IN: (
        "59",
        "16",
        "2",
        "1",
        "Part-time students, Undergraduate, Other degree/certificatee-seeking, Transfer-ins",
    ),
}
REQUIRED = frozenset(
    {
        "UNITID",
        "EFALEVEL",
        "LINE",
        "SECTION",
        "LSTUDY",
        "EFTOTLT",
        "XEFTOTLT",
    }
)
DEFINITIONS = {
    "UNITID": ("", "Unique identification number of the institution"),
    "EFALEVEL": ("", "Level of student"),
    "LINE": ("", "Level of student (original line number on survey form)"),
    "SECTION": ("", "Attendance status of student"),
    "LSTUDY": ("", "Level of student"),
    "EFTOTLT": ("XEFTOTLT", "Grand total"),
}


class IPEDSEnrollmentError(ValueError):
    """Invalid source, cohort definition, or paired provenance."""


class EnrollmentObservation(StrictModel):
    status: str
    unitid: int = Field(gt=0)
    cohort: EnrollmentCohort
    population: str
    fall_year: int = 2023
    efalevel: str
    line: str
    section: str
    lstudy: str
    enrollment_count: int | None
    raw_enrollment_count: str | None
    source_status: str | None
    release_id: str
    publication_status: str
    data_artifact_id: str
    dictionary_artifact_id: str
    reason: str | None = None
    interpretation: str = (
        "Observed fall enrollment at one institution, not admissions, completion, "
        "or transfer-out probability; reviewed categories overlap."
    )


@dataclass(frozen=True)
class RegisteredEnrollment:
    data: ArtifactManifest
    dictionary: ArtifactManifest


def _require_release(release: IPEDSRelease) -> None:
    if (
        release.component is not IPEDSComponent.FALL_ENROLLMENT
        or release.release_id != "2023-24-final"
        or release.publication_status is not IPEDSPublicationStatus.FINAL
        or release.data_member != "ef2023a_rv.csv"
    ):
        raise IPEDSEnrollmentError("requires reviewed final EF2023A revised release")


def verify_enrollment_dictionary(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            if archive.namelist() != ["ef2023a.xlsx"]:
                raise IPEDSEnrollmentError("dictionary requires ef2023a.xlsx")
            workbook = archive.read("ef2023a.xlsx")
        intro = _xlsx_rows(workbook, sheet_names=frozenset({"Introduction"}))
        varlist = _xlsx_rows(workbook, sheet_names=frozenset({"Varlist"}))
        frequencies = _xlsx_rows(workbook, sheet_names=frozenset({"FrequenciesRV"}))
    except (OSError, BadZipFile, KeyError, IPEDSDictionaryError) as error:
        raise IPEDSEnrollmentError(f"could not verify enrollment dictionary: {error}") from error
    if not any("(Final/revised release)" in cell for row in intro for cell in row):
        raise IPEDSEnrollmentError("dictionary is not a final revised release")
    for code, (status, label) in DEFINITIONS.items():
        rows = [row for row in varlist if len(row) >= 6 and row[1] == code]
        allowed_tails = ([status, label],) if status else ([label], ["", label])
        if len(rows) != 1 or rows[0][2] != "N" or rows[0][5:] not in allowed_tails:
            raise IPEDSEnrollmentError(f"dictionary lacks reviewed variable {code}")
    for level, _, _, _, label in COHORTS.values():
        rows = [
            row for row in frequencies if len(row) >= 5 and row[0] == "EFALEVEL" and row[3] == level
        ]
        if len(rows) != 1 or rows[0][2] != "EF2023A_rv" or rows[0][4] != label:
            raise IPEDSEnrollmentError(f"dictionary lacks reviewed cohort {level}")


def read_enrollment_rows(path: Path, member: str) -> dict[tuple[int, str], dict[str, str]]:
    """Validate the full revised member, returning only reviewed cohort rows."""
    selected: dict[tuple[int, str], dict[str, str]] = {}
    seen: set[tuple[int, str]] = set()
    layouts = {level: (line, section, study) for level, line, section, study, _ in COHORTS.values()}
    try:
        with ZipFile(path) as archive:
            if member not in archive.namelist():
                raise IPEDSEnrollmentError(f"enrollment archive is missing {member}")
            with archive.open(member) as stream:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
                missing = REQUIRED.difference(reader.fieldnames or ())
                if missing:
                    raise IPEDSEnrollmentError(
                        "enrollment archive is missing " + ", ".join(sorted(missing))
                    )
                for index, row in enumerate(reader, 2):
                    if None in row or any(row.get(field) is None for field in REQUIRED):
                        raise IPEDSEnrollmentError(f"malformed enrollment row {index}")
                    try:
                        unitid = int(row["UNITID"])
                        level = str(int(row["EFALEVEL"]))
                        for key in ("LINE", "SECTION", "LSTUDY"):
                            int(row[key])
                        if row["EFTOTLT"].strip():
                            int(row["EFTOTLT"])
                    except (TypeError, ValueError) as error:
                        raise IPEDSEnrollmentError(f"invalid enrollment row {index}") from error
                    pair = (unitid, level)
                    if unitid <= 0 or pair in seen:
                        raise IPEDSEnrollmentError(f"duplicate or invalid enrollment key {pair}")
                    seen.add(pair)
                    if level in layouts:
                        actual = tuple(str(int(row[key])) for key in ("LINE", "SECTION", "LSTUDY"))
                        if actual != layouts[level]:
                            raise IPEDSEnrollmentError(f"cohort layout differs for {pair}")
                        selected[pair] = {
                            key: row[key].strip() for key in REQUIRED if key != "UNITID"
                        }
    except (OSError, BadZipFile, UnicodeError, csv.Error) as error:
        raise IPEDSEnrollmentError(f"could not read enrollment archive: {error}") from error
    if not selected:
        raise IPEDSEnrollmentError("enrollment archive has no reviewed cohort rows")
    return selected


def _verify_manifest(
    path: Path, manifest: ArtifactManifest, release: IPEDSRelease, dataset_id: str, url: str
) -> None:
    if (
        manifest.dataset_id != dataset_id
        or manifest.release != release.release_id
        or manifest.publication_status != "final"
        or str(manifest.source_url) != url
        or manifest.state not in {ApprovalState.VALIDATED, ApprovalState.APPROVED}
    ):
        raise IPEDSEnrollmentError("enrollment artifact does not match validated final source")
    try:
        matches = sha256_file(path) == (manifest.sha256, manifest.file_size)
    except OSError as error:
        raise IPEDSEnrollmentError(f"could not read enrollment artifact: {error}") from error
    if not matches:
        raise IPEDSEnrollmentError("enrollment artifact bytes do not match manifest")


def register_enrollment(
    release: IPEDSRelease, paths: ProjectPaths, *, downloader: HttpDownloader | None = None
) -> RegisteredEnrollment:
    _require_release(release)
    downloader = downloader or HttpDownloader()
    downloads = []
    try:
        for url in (str(release.data_url), str(release.dictionary_url)):
            downloads.append(downloader.download(url, paths.data / ".downloads", ("nces.ed.gov",)))
        read_enrollment_rows(downloads[0].path, release.data_member or "")
        verify_enrollment_dictionary(downloads[1].path)
        registry = Registry(paths.data / "manifests" / "registry.sqlite")
        store = ArtifactStore(paths.data / "raw", registry)
        manifests = []
        for definition, download in zip(
            (ENROLLMENT_DATA, ENROLLMENT_DICTIONARY), downloads, strict=True
        ):
            registry.add_dataset(definition)
            manifest = store.register(
                download.path,
                definition,
                release=release.release_id,
                source_url=download.source_url,
                final_url=download.final_url,
                publication_status="final",
                schema_version="ipeds-ef2023a-v1",
                vintage=release.release_id,
                artifact_name=Path(urlparse(download.final_url).path).name,
            )
            if manifest.state is ApprovalState.DOWNLOADED:
                manifest = registry.transition(
                    manifest.artifact_id,
                    ApprovalState.VALIDATED,
                    "EF2023A revised enrollment cohorts and dictionary validated",
                )
            manifests.append(manifest)
        return RegisteredEnrollment(manifests[0], manifests[1])
    finally:
        for download in downloads:
            download.path.unlink(missing_ok=True)


def resolve_enrollment(
    archive: Path,
    dictionary: Path,
    release: IPEDSRelease,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    unitid: int,
    cohort: EnrollmentCohort,
) -> EnrollmentObservation:
    """Return the exact institution and population without cohort substitution."""
    _require_release(release)
    if unitid <= 0:
        raise IPEDSEnrollmentError("UNITID must be positive")
    _verify_manifest(
        archive, data_manifest, release, ENROLLMENT_DATA.dataset_id, str(release.data_url)
    )
    _verify_manifest(
        dictionary,
        dictionary_manifest,
        release,
        ENROLLMENT_DICTIONARY.dataset_id,
        str(release.dictionary_url),
    )
    verify_enrollment_dictionary(dictionary)
    level, line, section, study, label = COHORTS[cohort]
    row = read_enrollment_rows(archive, release.data_member or "").get((unitid, level))
    raw = row["EFTOTLT"] if row else None
    count = int(raw) if raw else None
    available = count is not None and count >= 0
    return EnrollmentObservation(
        status="OBSERVED" if available else "INSUFFICIENT_DATA",
        unitid=unitid,
        cohort=cohort,
        population=label,
        efalevel=level,
        line=line,
        section=section,
        lstudy=study,
        enrollment_count=count if available else None,
        raw_enrollment_count=raw,
        source_status=row["XEFTOTLT"] if row else None,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        data_artifact_id=data_manifest.artifact_id,
        dictionary_artifact_id=dictionary_manifest.artifact_id,
        reason=None if available else "source cohort absent or enrollment count unavailable",
    )
