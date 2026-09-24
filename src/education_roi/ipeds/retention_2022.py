"""Pinned final revised EF2022D institutional first-year retention evidence."""

from pathlib import Path
from urllib.parse import urlparse
from zipfile import BadZipFile, ZipFile

from education_roi.config.paths import ProjectPaths
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSPublicationStatus, IPEDSRelease
from education_roi.ipeds.dictionary import IPEDSDictionaryError, _xlsx_rows
from education_roi.ipeds.retention import (
    IPEDSRetentionError,
    IPEDSRetentionObservation,
    RegisteredIPEDSRetention,
    _count,
    _percent,
    _verify_manifest,
    read_retention_rows,
)
from education_roi.provenance.downloader import HttpDownloader
from education_roi.provenance.models import ApprovalState, ArtifactManifest, DatasetDefinition
from education_roi.provenance.store import ArtifactStore, Registry

DATA_URL = "https://nces.ed.gov/ipeds/datacenter/data/EF2022D.zip"
DICTIONARY_URL = "https://nces.ed.gov/ipeds/datacenter/data/EF2022D_Dict.zip"
DATA = DatasetDefinition(
    dataset_id="ipeds-fall-retention-2022",
    publisher="National Center for Education Statistics",
    name="IPEDS fall first-year retention EF2022D",
    allowed_domains=("nces.ed.gov",),
)
DICTIONARY = DatasetDefinition(
    dataset_id="ipeds-fall-retention-2022-dictionary",
    publisher="National Center for Education Statistics",
    name="IPEDS fall first-year retention dictionary EF2022D",
    allowed_domains=("nces.ed.gov",),
)
LABELS = {
    "RRFTCTA": "Full-time adjusted fall 2021 cohort",
    "RET_NMF": "Students from the full-time adjusted fall 2021 cohort enrolled in fall 2022",
    "RET_PCF": "Full-time retention rate, 2022",
}


def require_release(release: IPEDSRelease) -> None:
    if (
        release.component is not IPEDSComponent.FALL_RETENTION
        or release.release_id != "2022-23-final"
        or release.publication_status is not IPEDSPublicationStatus.FINAL
        or release.data_member != "ef2022d_rv.csv"
        or str(release.data_url) != DATA_URL
        or str(release.dictionary_url) != DICTIONARY_URL
    ):
        raise IPEDSRetentionError("requires reviewed final EF2022D revised source pair")


def verify_dictionary(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            if archive.namelist() != ["ef2022d.xlsx"]:
                raise IPEDSRetentionError("EF2022D dictionary requires ef2022d.xlsx")
            workbook = archive.read("ef2022d.xlsx")
        intro = _xlsx_rows(workbook, sheet_names=frozenset({"Introduction"}))
        rows = _xlsx_rows(workbook, sheet_names=frozenset({"varlist"}))
    except (OSError, BadZipFile, KeyError, IPEDSDictionaryError) as error:
        raise IPEDSRetentionError(f"could not verify EF2022D dictionary: {error}") from error
    found = [row for row in rows if len(row) >= 7 and row[1] in LABELS]
    if (
        not any("(Final/revised release)" in cell for row in intro for cell in row)
        or len(found) != len(LABELS)
        or any(row[6] != LABELS[row[1]] or row[5] != "X" + row[1] or row[2] != "N" for row in found)
    ):
        raise IPEDSRetentionError("EF2022D dictionary lacks reviewed final cohort definitions")


def resolve_retention_2022(
    archive: Path,
    dictionary: Path,
    release: IPEDSRelease,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    unitid: int,
) -> IPEDSRetentionObservation:
    """Return a fall 2021 cohort observation without implying graduation risk."""
    require_release(release)
    if unitid <= 0:
        raise IPEDSRetentionError("UNITID must be positive")
    _verify_manifest(archive, data_manifest, release, DATA.dataset_id, DATA_URL)
    _verify_manifest(
        dictionary, dictionary_manifest, release, DICTIONARY.dataset_id, DICTIONARY_URL
    )
    verify_dictionary(dictionary)
    row = read_retention_rows(archive, release.data_member or "").get(unitid)
    cohort = _count(row["RRFTCTA"]) if row else None
    enrolled = _count(row["RET_NMF"]) if row else None
    percent = _percent(row["RET_PCF"]) if row else None
    if cohort is not None and enrolled is not None and enrolled > cohort:
        raise IPEDSRetentionError(f"enrolled count exceeds adjusted cohort for UNITID {unitid}")
    return IPEDSRetentionObservation(
        unitid=unitid,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        entry_cohort_year=2021,
        observation_year=2022,
        status="OBSERVED"
        if cohort and enrolled is not None and percent is not None
        else "INSUFFICIENT_DATA",
        adjusted_cohort=cohort,
        enrolled_next_fall=enrolled,
        reported_retention_percent=percent,
        raw_cells={code: row[code] or None if row else None for code in LABELS},
        source_statuses={code: row["X" + code] or None if row else None for code in LABELS},
        data_artifact_id=data_manifest.artifact_id,
        dictionary_artifact_id=dictionary_manifest.artifact_id,
    )


def register_retention_2022(
    release: IPEDSRelease,
    paths: ProjectPaths,
    *,
    downloader: HttpDownloader | None = None,
) -> RegisteredIPEDSRetention:
    """Register the exact final revised CSV and the older lowercase-varlist workbook."""
    require_release(release)
    downloader = downloader or HttpDownloader()
    downloads = []
    try:
        for url in (DATA_URL, DICTIONARY_URL):
            downloads.append(downloader.download(url, paths.data / ".downloads", ("nces.ed.gov",)))
        read_retention_rows(downloads[0].path, release.data_member or "")
        verify_dictionary(downloads[1].path)
        registry = Registry(paths.data / "manifests" / "registry.sqlite")
        store = ArtifactStore(paths.data / "raw", registry)
        manifests = []
        for definition, download in zip((DATA, DICTIONARY), downloads, strict=True):
            registry.add_dataset(definition)
            manifest = store.register(
                download.path,
                definition,
                release=release.release_id,
                source_url=download.source_url,
                final_url=download.final_url,
                publication_status="final",
                schema_version="ipeds-ef2022d-v1",
                vintage=release.release_id,
                artifact_name=Path(urlparse(download.final_url).path).name,
            )
            if manifest.state is ApprovalState.DOWNLOADED:
                manifest = registry.transition(
                    manifest.artifact_id,
                    ApprovalState.VALIDATED,
                    "EF2022D revised retention columns and paired dictionary validated",
                )
            manifests.append(manifest)
        return RegisteredIPEDSRetention(manifests[0], manifests[1])
    finally:
        for download in downloads:
            download.path.unlink(missing_ok=True)
