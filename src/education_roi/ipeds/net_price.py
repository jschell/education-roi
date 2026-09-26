"""Pinned final SFA2223 institutional net-price group observations."""

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

NET_PRICE_DATA = DatasetDefinition(
    dataset_id="ipeds-net-price",
    publisher="National Center for Education Statistics",
    name="IPEDS final SFA2223 student financial aid and net price",
    allowed_domains=("nces.ed.gov",),
)
NET_PRICE_DICTIONARY = DatasetDefinition(
    dataset_id="ipeds-net-price-dictionary",
    publisher="National Center for Education Statistics",
    name="IPEDS final SFA2223 dictionary",
    allowed_domains=("nces.ed.gov",),
)


class NetPriceBasis(StrEnum):
    PUBLIC_GRANT = "public_in_state_grant"
    PUBLIC_TITLE_IV_0_30K = "public_in_state_title_iv_0_30k"
    OTHER_GRANT = "other_reporting_grant"
    OTHER_TITLE_IV_0_30K = "other_reporting_title_iv_0_30k"


FIELDS = {
    NetPriceBasis.PUBLIC_GRANT: (
        "NPIST2",
        "Average net price-students awarded grant or scholarship aid, 2022-23",
        "paying the in-state or in-district tuition rate who were awarded grant or scholarship aid",
        "Applicable to public institutions",
    ),
    NetPriceBasis.PUBLIC_TITLE_IV_0_30K: (
        "NPIS412",
        "Average net price (income 0-30,000)-students awarded Title IV federal financial aid, "
        "2022-23",
        "paying the in-state or in-district tuition rate who were awarded title IV "
        "federal student aid",
        "Applicable to public institutions",
    ),
    NetPriceBasis.OTHER_GRANT: (
        "NPGRN2",
        "Average net price-students awarded grant or scholarship aid, 2022-23",
        "who were awarded grant or scholarship aid",
        "Applicable to private not-for-profit and for-profit institutions",
    ),
    NetPriceBasis.OTHER_TITLE_IV_0_30K: (
        "NPT412",
        "Average net price (income 0-30,000)-students awarded Title IV federal financial aid, "
        "2022-23",
        "who were awarded title IV federal student aid",
        "Applicable to private not-for-profit and for-profit institutions",
    ),
}
REQUIRED = frozenset({"UNITID"}) | frozenset(
    field for code, *_ in FIELDS.values() for field in (code, "X" + code)
)


class IPEDSNetPriceError(ValueError):
    """Invalid source, basis, or paired provenance."""


class NetPriceObservation(StrictModel):
    status: str
    unitid: int = Field(gt=0)
    basis: NetPriceBasis
    source_field: str
    average_net_price: int | None
    raw_average_net_price: str | None
    source_status: str | None
    release_id: str
    publication_status: str
    aid_year: str = "2022-23"
    data_artifact_id: str
    dictionary_artifact_id: str
    reason: str | None = None
    interpretation: str = (
        "Historical institutional average for a selected aid-recipient group. "
        "Already reflects qualifying grants; not a student-specific offer or tuition alone."
    )


@dataclass(frozen=True)
class RegisteredNetPrice:
    data: ArtifactManifest
    dictionary: ArtifactManifest


def _require_release(release: IPEDSRelease) -> None:
    if (
        release.component is not IPEDSComponent.STUDENT_FINANCIAL_AID
        or release.release_id != "2023-24-final"
        or release.publication_status is not IPEDSPublicationStatus.FINAL
        or release.data_member != "sfa2223_RV.csv"
    ):
        raise IPEDSNetPriceError("requires reviewed final SFA2223 revised release")


def verify_net_price_dictionary(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            if archive.namelist() != ["sfa2223.xlsx"]:
                raise IPEDSNetPriceError("dictionary requires sfa2223.xlsx")
            workbook = archive.read("sfa2223.xlsx")
        intro = _xlsx_rows(workbook, sheet_names=frozenset({"Introduction"}))
        varlist = _xlsx_rows(workbook, sheet_names=frozenset({"Varlist"}))
        descriptions = _xlsx_rows(workbook, sheet_names=frozenset({"Description"}))
    except (OSError, BadZipFile, KeyError, IPEDSDictionaryError) as error:
        raise IPEDSNetPriceError(f"could not verify net-price dictionary: {error}") from error
    if not any("(Final/revised release)" in cell for row in intro for cell in row):
        raise IPEDSNetPriceError("dictionary is not a final revised release")
    for code, label, population, reporting_basis in FIELDS.values():
        definitions = [row for row in varlist if len(row) >= 7 and row[1] == code]
        detail = [row for row in descriptions if len(row) >= 3 and row[1] == code]
        if (
            len(definitions) != 1
            or definitions[0][6] != label
            or definitions[0][5] != "X" + code
            or len(detail) != 1
            or population not in detail[0][2]
            or reporting_basis not in detail[0][2]
        ):
            raise IPEDSNetPriceError(f"dictionary lacks reviewed population for {code}")


def read_net_price_rows(path: Path, member: str) -> dict[int, dict[str, str]]:
    """Read exact revised member, rejecting duplicate UNITIDs and malformed cells."""
    rows: dict[int, dict[str, str]] = {}
    try:
        with ZipFile(path) as archive:
            if member not in archive.namelist():
                raise IPEDSNetPriceError(f"net-price archive is missing {member}")
            with archive.open(member) as stream:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
                missing = REQUIRED.difference(reader.fieldnames or ())
                if missing:
                    raise IPEDSNetPriceError(
                        "net-price archive is missing " + ", ".join(sorted(missing))
                    )
                for index, row in enumerate(reader, 2):
                    if None in row or any(row.get(field) is None for field in REQUIRED):
                        raise IPEDSNetPriceError(f"malformed net-price row {index}")
                    try:
                        unitid = int(row["UNITID"])
                        for code, *_ in FIELDS.values():
                            if row[code].strip():
                                int(row[code])
                    except (TypeError, ValueError) as error:
                        raise IPEDSNetPriceError(f"invalid net-price row {index}") from error
                    if unitid <= 0 or unitid in rows:
                        raise IPEDSNetPriceError(f"duplicate or invalid UNITID {unitid}")
                    rows[unitid] = {
                        field: row[field].strip() for field in REQUIRED if field != "UNITID"
                    }
    except (OSError, BadZipFile, UnicodeError, csv.Error) as error:
        raise IPEDSNetPriceError(f"could not read net-price archive: {error}") from error
    if not rows:
        raise IPEDSNetPriceError("net-price archive has no institutions")
    return rows


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
        raise IPEDSNetPriceError("net-price artifact does not match validated final source")
    try:
        matches = sha256_file(path) == (manifest.sha256, manifest.file_size)
    except OSError as error:
        raise IPEDSNetPriceError(f"could not read net-price artifact: {error}") from error
    if not matches:
        raise IPEDSNetPriceError("net-price artifact bytes do not match manifest")


def register_net_price(
    release: IPEDSRelease, paths: ProjectPaths, *, downloader: HttpDownloader | None = None
) -> RegisteredNetPrice:
    _require_release(release)
    downloader = downloader or HttpDownloader()
    downloads = []
    try:
        for url in (str(release.data_url), str(release.dictionary_url)):
            downloads.append(downloader.download(url, paths.data / ".downloads", ("nces.ed.gov",)))
        read_net_price_rows(downloads[0].path, release.data_member or "")
        verify_net_price_dictionary(downloads[1].path)
        registry = Registry(paths.data / "manifests" / "registry.sqlite")
        store = ArtifactStore(paths.data / "raw", registry)
        manifests = []
        for definition, download in zip(
            (NET_PRICE_DATA, NET_PRICE_DICTIONARY), downloads, strict=True
        ):
            registry.add_dataset(definition)
            manifest = store.register(
                download.path,
                definition,
                release=release.release_id,
                source_url=download.source_url,
                final_url=download.final_url,
                publication_status="final",
                schema_version="ipeds-sfa2223-v1",
                vintage=release.release_id,
                artifact_name=Path(urlparse(download.final_url).path).name,
            )
            if manifest.state is ApprovalState.DOWNLOADED:
                manifest = registry.transition(
                    manifest.artifact_id,
                    ApprovalState.VALIDATED,
                    "SFA2223 revised net-price populations and dictionary validated",
                )
            manifests.append(manifest)
        return RegisteredNetPrice(manifests[0], manifests[1])
    finally:
        for download in downloads:
            download.path.unlink(missing_ok=True)


def resolve_net_price(
    archive: Path,
    dictionary: Path,
    release: IPEDSRelease,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    unitid: int,
    basis: NetPriceBasis,
) -> NetPriceObservation:
    """Return only the explicitly selected historical population, with raw status."""
    _require_release(release)
    if unitid <= 0:
        raise IPEDSNetPriceError("UNITID must be positive")
    _verify_manifest(
        archive, data_manifest, release, NET_PRICE_DATA.dataset_id, str(release.data_url)
    )
    _verify_manifest(
        dictionary,
        dictionary_manifest,
        release,
        NET_PRICE_DICTIONARY.dataset_id,
        str(release.dictionary_url),
    )
    verify_net_price_dictionary(dictionary)
    row = read_net_price_rows(archive, release.data_member or "").get(unitid)
    code = FIELDS[basis][0]
    raw = row[code] if row else None
    value = int(raw) if raw else None
    return NetPriceObservation(
        status="OBSERVED" if value is not None and value >= 0 else "INSUFFICIENT_DATA",
        unitid=unitid,
        basis=basis,
        source_field=code,
        average_net_price=value if value is not None and value >= 0 else None,
        raw_average_net_price=raw,
        source_status=row["X" + code] if row else None,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        data_artifact_id=data_manifest.artifact_id,
        dictionary_artifact_id=dictionary_manifest.artifact_id,
        reason=None
        if value is not None and value >= 0
        else "source row absent or net price unavailable",
    )
