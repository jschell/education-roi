import io
import zipfile
from pathlib import Path

import httpx
import pytest

from education_roi.acs.discovery import ACSDiscoveryError, ACSReleaseDiscoverer, parse_vintages
from education_roi.acs.models import ACSProduct, ACSRelease
from education_roi.acs.registration import (
    ACSDictionaryError,
    ACSPersonSchemaError,
    register_acs_release,
)
from education_roi.config.paths import ProjectPaths
from education_roi.provenance.downloader import HttpDownloader
from education_roi.provenance.store import Registry


def person_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        columns = "SERIALNO,SPORDER,ADJINC,PWGTP,AGEP,SCH,SCHL,WAGP,FOD1P,NATIVITY"
        bundle.writestr("psam_p53.csv", columns + "\n1,1,1000000,1,30,1,21,10,1101,1\n")
    return output.getvalue()


def dictionary_csv(*, complete: bool = True) -> bytes:
    variables = [
        "SERIALNO",
        "SPORDER",
        "ADJINC",
        "PWGTP",
        "AGEP",
        "SCH",
        "SCHL",
        "WAGP",
        "FOD1P",
        "NATIVITY",
    ]
    if not complete:
        variables.remove("ADJINC")
    return "".join(f'NAME,{name},C,1,"description"\n' for name in variables).encode()


@pytest.mark.integration
def test_discovery_requires_archive_in_product_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pums/"):
            return httpx.Response(200, text='<a href="2023/">2023</a><a href="2024/">2024</a>')
        if "/2024/1-Year/" in request.url.path:
            return httpx.Response(200, text='<a href="csv_pwa.zip">csv_pwa.zip</a>')
        return httpx.Response(200, text='<a href="csv_pca.zip">csv_pca.zip</a>')

    releases = ACSReleaseDiscoverer(
        ACSProduct.ONE_YEAR,
        "wa",
        max_releases=2,
        transport=httpx.MockTransport(handler),
    ).discover()
    assert [release.release for release in releases] == ["2024-1yr-wa"]


def test_vintage_parser_ignores_invalid_links() -> None:
    assert parse_vintages('<a href="2024/">ok</a><a href="latest/">no</a>') == (2024,)
    with pytest.raises(ACSDiscoveryError, match="valid vintages"):
        ACSReleaseDiscoverer(
            ACSProduct.ONE_YEAR,
            "wa",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="empty")),
        ).discover()


@pytest.mark.integration
def test_release_bundle_downloads_validates_and_registers(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".zip"):
            return httpx.Response(200, content=person_zip())
        return httpx.Response(200, content=dictionary_csv())

    release = ACSRelease(vintage=2024, product=ACSProduct.ONE_YEAR, geography="wa")
    registered = register_acs_release(
        release,
        ProjectPaths(tmp_path),
        downloader=HttpDownloader(transport=httpx.MockTransport(handler)),
    )

    assert registered.person.dataset_id == "acs-pums"
    assert registered.person.storage_path.endswith("/csv_pwa.zip")
    assert registered.dictionary.dataset_id == "acs-pums-dictionary"
    assert registered.dictionary.storage_path.endswith("/PUMS_Data_Dictionary_2024.csv")
    registry = Registry(tmp_path / "data" / "manifests" / "registry.sqlite")
    assert len(registry.list_artifacts()) == 2


@pytest.mark.integration
def test_invalid_dictionary_registers_nothing(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = (
            person_zip() if request.url.path.endswith(".zip") else dictionary_csv(complete=False)
        )
        return httpx.Response(200, content=content)

    release = ACSRelease(vintage=2024, product=ACSProduct.ONE_YEAR, geography="wa")
    with pytest.raises(ACSDictionaryError, match="ADJINC"):
        register_acs_release(
            release,
            ProjectPaths(tmp_path),
            downloader=HttpDownloader(transport=httpx.MockTransport(handler)),
        )
    assert not (tmp_path / "data" / "manifests" / "registry.sqlite").exists()


@pytest.mark.integration
def test_invalid_person_schema_registers_nothing(tmp_path: Path) -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        bundle.writestr("psam_p53.csv", "SERIALNO,SPORDER\n1,1\n")

    def handler(request: httpx.Request) -> httpx.Response:
        content = output.getvalue() if request.url.path.endswith(".zip") else dictionary_csv()
        return httpx.Response(200, content=content)

    release = ACSRelease(vintage=2024, product=ACSProduct.ONE_YEAR, geography="wa")
    with pytest.raises(ACSPersonSchemaError, match="ADJINC"):
        register_acs_release(
            release,
            ProjectPaths(tmp_path),
            downloader=HttpDownloader(transport=httpx.MockTransport(handler)),
        )
    assert not (tmp_path / "data" / "manifests" / "registry.sqlite").exists()
