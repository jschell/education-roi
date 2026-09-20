"""Stable identifiers and field contracts for IPEDS academic-year charges."""

from education_roi.provenance.models import DatasetDefinition

IPEDS_CHARGES_DATASET = DatasetDefinition(
    dataset_id="ipeds-institutional-characteristics",
    publisher="National Center for Education Statistics",
    name="IPEDS Institutional Characteristics: Academic Year Charges",
    allowed_domains=("nces.ed.gov",),
)
IPEDS_DICTIONARY_DATASET = DatasetDefinition(
    dataset_id="ipeds-institutional-characteristics-dictionary",
    publisher="National Center for Education Statistics",
    name="IPEDS Institutional Characteristics: Academic Year Charges Dictionary",
    allowed_domains=("nces.ed.gov",),
)

IPEDS_SCHEMA_VERSION = "ipeds-ic-ay-v1"
UNITID_COLUMN = "UNITID"
COST_COLUMNS = {
    "costs.tuition_and_fees": "CHG2AY3",
    "costs.books_and_supplies": "CHG4AY3",
}
COST_STATUS_COLUMNS = {
    "costs.tuition_and_fees": "XCHG2AY3",
    "costs.books_and_supplies": "XCHG4AY3",
}
REQUIRED_COLUMNS = frozenset({UNITID_COLUMN, *COST_COLUMNS.values()})
