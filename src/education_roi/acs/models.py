"""Stable identifiers for ACS PUMS releases."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ACSProduct(StrEnum):
    """Published ACS PUMS products."""

    ONE_YEAR = "1-Year"
    FIVE_YEAR = "5-Year"

    @property
    def release_label(self) -> str:
        """Return the compact product label used in project release IDs."""
        return "1yr" if self is ACSProduct.ONE_YEAR else "5yr"


class ACSRelease(BaseModel):
    """An exact ACS PUMS person-file release and geography."""

    model_config = ConfigDict(frozen=True)

    vintage: int = Field(ge=2005, le=2100)
    product: ACSProduct
    geography: str = Field(pattern=r"^(us|[a-z]{2})$")
    publication_status: str = "final"

    @property
    def release_id(self) -> str:
        return f"{self.vintage}-{self.product.release_label}-{self.geography}"

    @property
    def person_archive_url(self) -> str:
        root = "https://www2.census.gov/programs-surveys/acs/data/pums"
        return f"{root}/{self.vintage}/{self.product.value}/csv_p{self.geography}.zip"

    @property
    def variables_url(self) -> str:
        product = "acs1" if self.product is ACSProduct.ONE_YEAR else "acs5"
        return f"https://api.census.gov/data/{self.vintage}/acs/{product}/pums/variables.json"
