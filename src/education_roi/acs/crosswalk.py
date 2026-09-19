"""Versioned crosswalk safeguards for ACS field-of-degree codes."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CrosswalkStatus(StrEnum):
    """Evidence state for a classification crosswalk."""

    PROVISIONAL = "PROVISIONAL"
    VERIFIED = "VERIFIED"


class ReproductionCrosswalkError(ValueError):
    """Raised when an unverified crosswalk is used for paper reproduction."""


class DegreeCrosswalk(BaseModel):
    """A versioned mapping from ACS FOD1P codes to analysis categories."""

    model_config = ConfigDict(frozen=True)

    version: str = Field(min_length=1)
    status: CrosswalkStatus
    source: str = Field(min_length=1)
    mappings: dict[str, str] = Field(min_length=1)

    def require_verified_for_reproduction(self) -> None:
        """Prevent provisional mappings from supporting a Zhang reproduction claim."""
        if self.status is not CrosswalkStatus.VERIFIED:
            raise ReproductionCrosswalkError(
                "Zhang reproduction requires the supplement-verified Table A1 crosswalk"
            )
