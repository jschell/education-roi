"""Conservative discovery of published ACS PUMS releases."""

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from education_roi.acs.models import ACSProduct, ACSRelease
from education_roi.provenance.discovery import DiscoveredRelease
from education_roi.provenance.store import validate_source_url

ACS_PUMS_INDEX_URL = "https://www2.census.gov/programs-surveys/acs/data/pums/"


class ACSDiscoveryError(RuntimeError):
    """Publisher indexes could not be interpreted safely."""


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value is not None:
                self.hrefs.append(value)


def _hrefs(document: str) -> tuple[str, ...]:
    parser = _HrefParser()
    parser.feed(document)
    return tuple(parser.hrefs)


def parse_vintages(document: str) -> tuple[int, ...]:
    """Extract plausible ACS vintages from the publisher directory index."""
    vintages = {
        int(href.rstrip("/"))
        for href in _hrefs(document)
        if href.rstrip("/").isdigit() and len(href.rstrip("/")) == 4
    }
    return tuple(sorted(year for year in vintages if 2005 <= year <= 2100))


class ACSReleaseDiscoverer:
    """Verify exact person archives advertised by Census product indexes."""

    def __init__(
        self,
        product: ACSProduct,
        geography: str,
        *,
        max_releases: int = 1,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if max_releases < 1:
            raise ValueError("max_releases must be positive")
        self.product = product
        self.geography = geography
        self.max_releases = max_releases
        self.timeout = timeout
        self.transport = transport

    def _get_text(self, client: httpx.Client, url: str) -> str:
        validate_source_url(url, ("census.gov",))
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ACSDiscoveryError(f"could not read Census index {url}: {error}") from error
        final_url = str(response.url)
        validate_source_url(final_url, ("census.gov",))
        return response.text

    def discover(self) -> tuple[DiscoveredRelease, ...]:
        """Return newest verified archive candidates, oldest first."""
        found: list[DiscoveredRelease] = []
        with httpx.Client(
            follow_redirects=True,
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            vintages = parse_vintages(self._get_text(client, ACS_PUMS_INDEX_URL))
            if not vintages:
                raise ACSDiscoveryError("Census PUMS index did not contain any valid vintages")
            for vintage in reversed(vintages):
                release = ACSRelease(
                    vintage=vintage,
                    product=self.product,
                    geography=self.geography,
                )
                try:
                    product_index = self._get_text(client, release.product_index_url)
                except ACSDiscoveryError:
                    continue
                advertised = {
                    urlparse(urljoin(release.product_index_url, href)).path.rsplit("/", 1)[-1]
                    for href in _hrefs(product_index)
                }
                archive_name = release.person_archive_url.rsplit("/", 1)[-1]
                if archive_name not in advertised:
                    continue
                found.append(
                    DiscoveredRelease(
                        dataset_id="acs-pums",
                        release=release.release_id,
                        source_url=release.person_archive_url,
                        publication_status=release.publication_status,
                    )
                )
                if len(found) == self.max_releases:
                    break
        return tuple(reversed(found))
