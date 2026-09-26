"""Attach verified historical net-price context to an education scenario."""

from pathlib import Path

from pydantic import Field

from education_roi.ipeds.net_price import NetPriceBasis
from education_roi.ipeds.net_price_evidence import NetPriceEvidence, resolve_net_price_evidence
from education_roi.scenarios.models import (
    AttendanceBasis,
    ScenarioDefinition,
    StrictModel,
    TuitionResidency,
)


class ScenarioNetPriceContextError(ValueError):
    """The scenario does not match the explicit source population or release."""


class ScenarioNetPriceContext(StrictModel):
    scenario_id: str
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    institution_unitid: int
    evidence: NetPriceEvidence
    cash_flow_use: str = "CONTEXT_ONLY"
    note: str = (
        "Historical aid-recipient institutional average. No scenario cost or grant value "
        "is changed; the cash-flow model requires separate, compatible cost components."
    )


def review_scenario_net_price(
    scenario: ScenarioDefinition, table: Path, basis: NetPriceBasis
) -> ScenarioNetPriceContext:
    """Associate exact verified evidence without changing additive cash-flow costs."""
    institution = scenario.education.institution if scenario.education is not None else None
    if institution is None:
        raise ScenarioNetPriceContextError("scenario requires an education institution")
    if institution.attendance_basis is not AttendanceBasis.FULL_TIME:
        raise ScenarioNetPriceContextError("net-price population requires full-time attendance")
    if basis in (NetPriceBasis.PUBLIC_GRANT, NetPriceBasis.PUBLIC_TITLE_IV_0_30K) and (
        institution.tuition_residency
        not in (TuitionResidency.IN_STATE, TuitionResidency.IN_DISTRICT)
    ):
        raise ScenarioNetPriceContextError(
            "public net-price basis requires in-state/in-district tuition"
        )
    pins = {pin.dataset: pin.release for pin in scenario.data.pins}
    if pins.get("ipeds-net-price") != "2023-24-final":
        raise ScenarioNetPriceContextError(
            "scenario must pin ipeds-net-price to 2023-24-final for contextual evidence"
        )
    evidence = resolve_net_price_evidence(table, institution.unitid, basis)
    return ScenarioNetPriceContext(
        scenario_id=scenario.id,
        configuration_hash=scenario.configuration_hash,
        institution_unitid=institution.unitid,
        evidence=evidence,
    )
