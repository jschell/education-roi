"""Exact, paired evidence for final C2023_A program award counts."""

import csv
import io
import re
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

PROGRAM_DATA = DatasetDefinition(
    dataset_id="ipeds-program-awards",
    publisher="National Center for Education Statistics",
    name="IPEDS C2023_A awards by program and award level",
    allowed_domains=("nces.ed.gov",),
)
PROGRAM_DICTIONARY = DatasetDefinition(
    dataset_id="ipeds-program-awards-dictionary",
    publisher="National Center for Education Statistics",
    name="IPEDS C2023_A awards dictionary",
    allowed_domains=("nces.ed.gov",),
)
REQUIRED = frozenset({"UNITID", "CIPCODE", "MAJORNUM", "AWLEVEL", "CTOTALT", "XCTOTALT"})
LABELS = {
    "UNITID": ("Unique identification number of the institution", ""),
    "CIPCODE": ("CIP Code -  2020 Classification", ""),
    "MAJORNUM": ("First or Second Major", ""),
    "AWLEVEL": ("Award Level code", ""),
    "CTOTALT": ("Grand total", "XCTOTALT"),
}
CIP_PATTERN = re.compile(r"^\d{2}\.\d{4}$")


class IPEDSProgramAwardsError(ValueError):
    """Invalid release, dictionary, archive, or exact-key observation."""


class ProgramAwardObservation(StrictModel):
    status: str
    unitid: int = Field(gt=0)
    cip_code: str
    cip_version: str = "2020"
    major_number: int
    award_level: int
    award_count: int | None
    raw_award_count: str | None
    source_status: str | None
    release_id: str
    publication_status: str
    period_start: str = "2022-07-01"
    period_end: str = "2023-06-30"
    data_artifact_id: str
    dictionary_artifact_id: str
    reason: str | None = None
    interpretation: str = (
        "Awards conferred at an exact institution, CIP 2020 code, major number, and "
        "award level. Not distinct graduates or a program completion probability."
    )


@dataclass(frozen=True)
class RegisteredProgramAwards:
    data: ArtifactManifest
    dictionary: ArtifactManifest


def _require_release(release: IPEDSRelease) -> None:
    if (
        release.component is not IPEDSComponent.COMPLETIONS_BY_PROGRAM
        or release.release_id != "2023-24-final"
        or release.publication_status is not IPEDSPublicationStatus.FINAL
        or release.data_member != "C2023_a_RV.csv"
    ):
        raise IPEDSProgramAwardsError("requires reviewed final C2023_A revised release")


def verify_program_dictionary(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            if archive.namelist() != ["C2023_a_dict.xlsx"]:
                raise IPEDSProgramAwardsError("dictionary requires C2023_a_dict.xlsx")
            workbook = archive.read("C2023_a_dict.xlsx")
        introduction = _xlsx_rows(workbook, sheet_names=frozenset({"Introduction"}))
        definitions = _xlsx_rows(workbook, sheet_names=frozenset({"Varlist"}))
        frequencies = _xlsx_rows(workbook, sheet_names=frozenset({"FrequenciesRV"}))
    except (OSError, BadZipFile, KeyError, IPEDSDictionaryError) as error:
        raise IPEDSProgramAwardsError(f"could not verify program dictionary: {error}") from error
    found = [row for row in definitions if len(row) >= 7 and row[1] in LABELS]
    if (
        len(found) != len(LABELS)
        or {row[1] for row in found} != LABELS.keys()
        or any((row[6], row[5]) != LABELS[row[1]] for row in found)
        or not any("(Final/revised release)" in cell for row in introduction for cell in row)
        or not any(
            "2020 Classification of Instructional Programs" in cell
            for row in introduction
            for cell in row
        )
        or not any(
            len(row) > 3 and row[1:4] == ["MAJORNUM", "1", "First major"] for row in frequencies
        )
        or not any(
            len(row) > 3 and row[1:4] == ["AWLEVEL", "5", "Bachelor's degree"]
            for row in frequencies
        )
    ):
        raise IPEDSProgramAwardsError("dictionary lacks reviewed final program definitions")


def _read_awards(
    path: Path, member: str, target: tuple[int, str, int, int] | None = None
) -> tuple[int, dict[str, str] | None]:
    seen: set[tuple[int, str, int, int]] = set()
    match = None
    try:
        with ZipFile(path) as archive:
            if member not in archive.namelist():
                raise IPEDSProgramAwardsError(f"program archive is missing {member}")
            with archive.open(member) as source:
                reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))
                missing = REQUIRED.difference(reader.fieldnames or ())
                if missing:
                    raise IPEDSProgramAwardsError(
                        "program archive is missing " + ", ".join(sorted(missing))
                    )
                for line, row in enumerate(reader, 2):
                    if None in row or any(row.get(field) is None for field in REQUIRED):
                        raise IPEDSProgramAwardsError(f"malformed program row {line}")
                    try:
                        key = (
                            int(row["UNITID"]),
                            row["CIPCODE"].strip(),
                            int(row["MAJORNUM"]),
                            int(row["AWLEVEL"]),
                        )
                    except (TypeError, ValueError) as error:
                        raise IPEDSProgramAwardsError(
                            f"invalid program key on row {line}"
                        ) from error
                    if (
                        key[0] <= 0
                        or key[2] not in (1, 2)
                        or key[3] <= 0
                        or (not CIP_PATTERN.fullmatch(key[1]) and key[1] != "99")
                    ):
                        raise IPEDSProgramAwardsError(f"invalid program key on row {line}")
                    if key in seen:
                        raise IPEDSProgramAwardsError(f"duplicate program key on row {line}")
                    seen.add(key)
                    raw = row["CTOTALT"].strip()
                    if raw:
                        try:
                            int(raw)
                        except ValueError as error:
                            raise IPEDSProgramAwardsError(
                                f"invalid award count on row {line}"
                            ) from error
                    if key == target:
                        match = {field: value.strip() for field, value in row.items()}
    except (OSError, BadZipFile, UnicodeError, csv.Error) as error:
        raise IPEDSProgramAwardsError(f"could not read program archive: {error}") from error
    if not seen:
        raise IPEDSProgramAwardsError("program archive has no rows")
    return len(seen), match


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
        raise IPEDSProgramAwardsError("program artifact does not match validated final source")
    try:
        matches = sha256_file(path) == (manifest.sha256, manifest.file_size)
    except OSError as error:
        raise IPEDSProgramAwardsError(f"could not read program artifact: {error}") from error
    if not matches:
        raise IPEDSProgramAwardsError("program artifact bytes do not match manifest")


def register_program_awards(
    release: IPEDSRelease, paths: ProjectPaths, *, downloader: HttpDownloader | None = None
) -> RegisteredProgramAwards:
    """Validate full revised archive and paired dictionary before immutable registration."""
    _require_release(release)
    downloader = downloader or HttpDownloader()
    downloads = []
    try:
        for url in (str(release.data_url), str(release.dictionary_url)):
            downloads.append(downloader.download(url, paths.data / ".downloads", ("nces.ed.gov",)))
        _read_awards(downloads[0].path, release.data_member or "")
        verify_program_dictionary(downloads[1].path)
        registry = Registry(paths.data / "manifests" / "registry.sqlite")
        store = ArtifactStore(paths.data / "raw", registry)
        manifests = []
        for definition, download in zip((PROGRAM_DATA, PROGRAM_DICTIONARY), downloads, strict=True):
            registry.add_dataset(definition)
            manifest = store.register(
                download.path,
                definition,
                release=release.release_id,
                source_url=download.source_url,
                final_url=download.final_url,
                publication_status="final",
                schema_version="ipeds-c2023a-v1",
                vintage=release.release_id,
                artifact_name=Path(urlparse(download.final_url).path).name,
            )
            if manifest.state is ApprovalState.DOWNLOADED:
                manifest = registry.transition(
                    manifest.artifact_id,
                    ApprovalState.VALIDATED,
                    "C2023_A revised program keys and paired dictionary validated",
                )
            manifests.append(manifest)
        return RegisteredProgramAwards(manifests[0], manifests[1])
    finally:
        for download in downloads:
            download.path.unlink(missing_ok=True)


def resolve_program_awards(
    archive: Path,
    dictionary: Path,
    release: IPEDSRelease,
    data_manifest: ArtifactManifest,
    dictionary_manifest: ArtifactManifest,
    unitid: int,
    cip_code: str,
    major_number: int,
    award_level: int,
) -> ProgramAwardObservation:
    """Return one award cell without aggregation or completion-rate inference."""
    _require_release(release)
    if (
        unitid <= 0
        or not CIP_PATTERN.fullmatch(cip_code)
        or major_number not in (1, 2)
        or award_level <= 0
    ):
        raise IPEDSProgramAwardsError(
            "requires positive UNITID, six-digit CIP, major 1/2 and award level"
        )
    _verify_manifest(
        archive, data_manifest, release, PROGRAM_DATA.dataset_id, str(release.data_url)
    )
    _verify_manifest(
        dictionary,
        dictionary_manifest,
        release,
        PROGRAM_DICTIONARY.dataset_id,
        str(release.dictionary_url),
    )
    verify_program_dictionary(dictionary)
    _, row = _read_awards(
        archive, release.data_member or "", (unitid, cip_code, major_number, award_level)
    )
    raw = row["CTOTALT"] if row else None
    value = int(raw) if raw else None
    return ProgramAwardObservation(
        status="OBSERVED" if value is not None and value >= 0 else "INSUFFICIENT_DATA",
        unitid=unitid,
        cip_code=cip_code,
        major_number=major_number,
        award_level=award_level,
        award_count=value if value is not None and value >= 0 else None,
        raw_award_count=raw,
        source_status=row["XCTOTALT"] if row else None,
        release_id=release.release_id,
        publication_status=release.publication_status.value,
        data_artifact_id=data_manifest.artifact_id,
        dictionary_artifact_id=dictionary_manifest.artifact_id,
        reason=None
        if value is not None and value >= 0
        else "source row absent or count unavailable",
    )
