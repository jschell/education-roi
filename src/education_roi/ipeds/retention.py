"""Pinned final EF2023D revised institutional first-year retention evidence."""

import csv
import io
from dataclasses import dataclass
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

RETENTION_DATA = DatasetDefinition(
    dataset_id="ipeds-fall-retention",
    publisher="National Center for Education Statistics",
    name="IPEDS fall first-year retention EF2023D",
    allowed_domains=("nces.ed.gov",),
)
RETENTION_DICTIONARY = DatasetDefinition(
    dataset_id="ipeds-fall-retention-dictionary",
    publisher="National Center for Education Statistics",
    name="IPEDS fall first-year retention dictionary EF2023D",
    allowed_domains=("nces.ed.gov",),
)
REQUIRED = frozenset(
    {"UNITID", "RRFTCTA", "XRRFTCTA", "RET_NMF", "XRET_NMF", "RET_PCF", "XRET_PCF"}
)
LABELS = {
    "RRFTCTA": "Full-time adjusted fall 2022 cohort",
    "RET_NMF": "Students from the full-time adjusted fall 2022 cohort enrolled in fall 2023",
    "RET_PCF": "Full-time retention rate, 2023",
}


class IPEDSRetentionError(ValueError):
    """An exact retention source or cohort definition failed validation."""


class IPEDSRetentionObservation(StrictModel):
    unitid: int = Field(gt=0)
    release_id: str
    publication_status: str
    entry_cohort_year: int = 2022
    observation_year: int = 2023
    population: str = "first_time_full_time_degree_or_certificate_seeking_undergraduate"
    status: str
    adjusted_cohort: int | None
    enrolled_next_fall: int | None
    reported_retention_percent: int | None
    raw_cells: dict[str, str | None]
    source_statuses: dict[str, str | None]
    data_artifact_id: str
    dictionary_artifact_id: str
    interpretation: str = (
        "Observed institutional first-year retention; source percent may be rounded and "
        "is not a bachelor's completion probability or an individual forecast."
    )


@dataclass(frozen=True)
class RegisteredIPEDSRetention:
    data: ArtifactManifest
    dictionary: ArtifactManifest


def _require_release(release: IPEDSRelease) -> None:
    if (
        release.component is not IPEDSComponent.FALL_RETENTION
        or release.release_id != "2023-24-final"
        or release.publication_status is not IPEDSPublicationStatus.FINAL
        or release.data_member != "ef2023d_rv.csv"
    ):
        raise IPEDSRetentionError("requires reviewed final EF2023D revised release")


def verify_retention_dictionary(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            if archive.namelist() != ["ef2023d.xlsx"]:
                raise IPEDSRetentionError("retention dictionary requires ef2023d.xlsx")
            workbook = archive.read("ef2023d.xlsx")
        intro = _xlsx_rows(workbook, sheet_names=frozenset({"Introduction"}))
        rows = _xlsx_rows(workbook, sheet_names=frozenset({"Varlist"}))
    except (OSError, BadZipFile, KeyError, IPEDSDictionaryError) as error:
        raise IPEDSRetentionError(f"could not verify retention dictionary: {error}") from error
    found = [row for row in rows if len(row) >= 7 and row[1] in LABELS]
    if (
        not any("(Final/revised release)" in cell for row in intro for cell in row)
        or len(found) != len(LABELS)
        or {row[1] for row in found} != LABELS.keys()
        or any(row[6] != LABELS[row[1]] or row[5] != "X" + row[1] or row[2] != "N" for row in found)
    ):
        raise IPEDSRetentionError("dictionary lacks reviewed final cohort definitions")


def read_retention_rows(path: Path, member: str) -> dict[int, dict[str, str]]:
    """Select the final revised member and reject duplicate IDs or missing schema."""
    rows: dict[int, dict[str, str]] = {}
    try:
        with ZipFile(path) as archive:
            if member not in archive.namelist():
                raise IPEDSRetentionError(f"retention archive is missing {member}")
            with archive.open(member) as stream:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
                missing = REQUIRED.difference(reader.fieldnames or ())
                if missing:
                    raise IPEDSRetentionError(
                        "retention archive is missing " + ", ".join(sorted(missing))
                    )
                for index, row in enumerate(reader, 2):
                    if None in row or any(row.get(key) is None for key in REQUIRED):
                        raise IPEDSRetentionError(f"malformed retention row {index}")
                    try:
                        unitid = int(row["UNITID"])
                    except (ValueError, TypeError) as error:
                        raise IPEDSRetentionError(
                            f"invalid UNITID on retention row {index}"
                        ) from error
                    if unitid <= 0 or unitid in rows:
                        raise IPEDSRetentionError(f"duplicate or invalid UNITID {unitid}")
                    rows[unitid] = {key: (value or "").strip() for key, value in row.items()}
    except (OSError, BadZipFile, UnicodeError, csv.Error) as error:
        raise IPEDSRetentionError(f"could not read retention archive: {error}") from error
    if not rows:
        raise IPEDSRetentionError("retention archive has no institutions")
    return rows


def _count(cell: str) -> int | None:
    if not cell:
        return None
    try:
        number = int(cell)
    except ValueError as error:
        raise IPEDSRetentionError(f"invalid retention count {cell!r}") from error
    return number if number >= 0 else None


def _percent(cell: str) -> int | None:
    number = _count(cell)
    if number is not None and number > 100:
        raise IPEDSRetentionError("retention percentage exceeds 100")
    return number


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
        raise IPEDSRetentionError("retention artifact does not match validated final source")
    try:
        matches = sha256_file(path) == (manifest.sha256, manifest.file_size)
    except OSError as error:
        raise IPEDSRetentionError(f"could not read retention artifact: {error}") from error
    if not matches:
        raise IPEDSRetentionError("retention artifact bytes do not match their manifest")


def resolve_retention(
    archive: Path,
    dictionary: Path,
    release: IPEDSRelease,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    unitid: int,
) -> IPEDSRetentionObservation:
    """Report the exact source percentage and count cells without completion inference."""
    _require_release(release)
    if unitid <= 0:
        raise IPEDSRetentionError("UNITID must be positive")
    _verify_manifest(
        archive, data_manifest, release, RETENTION_DATA.dataset_id, str(release.data_url)
    )
    _verify_manifest(
        dictionary,
        dictionary_manifest,
        release,
        RETENTION_DICTIONARY.dataset_id,
        str(release.dictionary_url),
    )
    verify_retention_dictionary(dictionary)
    row = read_retention_rows(archive, release.data_member or "").get(unitid)
    cells = {code: row[code] or None if row else None for code in LABELS}
    statuses = {code: row["X" + code] or None if row else None for code in LABELS}
    cohort = _count(row["RRFTCTA"]) if row else None
    enrolled = _count(row["RET_NMF"]) if row else None
    percent = _percent(row["RET_PCF"]) if row else None
    if cohort is not None and enrolled is not None and enrolled > cohort:
        raise IPEDSRetentionError(f"enrolled count exceeds adjusted cohort for UNITID {unitid}")
    return IPEDSRetentionObservation(
        unitid=unitid,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        status=(
            "OBSERVED"
            if cohort and enrolled is not None and percent is not None
            else "INSUFFICIENT_DATA"
        ),
        adjusted_cohort=cohort,
        enrolled_next_fall=enrolled,
        reported_retention_percent=percent,
        raw_cells=cells,
        source_statuses=statuses,
        data_artifact_id=data_manifest.artifact_id,
        dictionary_artifact_id=dictionary_manifest.artifact_id,
    )


def register_retention_release(
    release: IPEDSRelease,
    paths: ProjectPaths,
    *,
    downloader: HttpDownloader | None = None,
) -> RegisteredIPEDSRetention:
    """Register the exact final revised member and its paired official dictionary."""
    _require_release(release)
    downloader = downloader or HttpDownloader()
    downloads = []
    try:
        for url in (str(release.data_url), str(release.dictionary_url)):
            downloads.append(downloader.download(url, paths.data / ".downloads", ("nces.ed.gov",)))
        read_retention_rows(downloads[0].path, release.data_member or "")
        verify_retention_dictionary(downloads[1].path)
        registry = Registry(paths.data / "manifests" / "registry.sqlite")
        store = ArtifactStore(paths.data / "raw", registry)
        manifests = []
        for definition, download in zip(
            (RETENTION_DATA, RETENTION_DICTIONARY), downloads, strict=True
        ):
            registry.add_dataset(definition)
            manifest = store.register(
                download.path,
                definition,
                release=release.release_id,
                source_url=download.source_url,
                final_url=download.final_url,
                publication_status="final",
                schema_version="ipeds-ef2023d-v1",
                vintage=release.release_id,
                artifact_name=Path(urlparse(download.final_url).path).name,
            )
            if manifest.state is ApprovalState.DOWNLOADED:
                manifest = registry.transition(
                    manifest.artifact_id,
                    ApprovalState.VALIDATED,
                    "EF2023D revised retention columns and paired dictionary validated",
                )
            manifests.append(manifest)
        return RegisteredIPEDSRetention(manifests[0], manifests[1])
    finally:
        for download in downloads:
            download.path.unlink(missing_ok=True)
