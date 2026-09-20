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
TUITION_COLUMNS = {
    "in_district": "CHG1AY3",
    "in_state": "CHG2AY3",
    "out_of_state": "CHG3AY3",
}
TUITION_STATUS_COLUMNS = {
    "in_district": "XCHG1AY3",
    "in_state": "XCHG2AY3",
    "out_of_state": "XCHG3AY3",
}
BOOKS_COLUMN = "CHG4AY3"
BOOKS_STATUS_COLUMN = "XCHG4AY3"
COST_COLUMNS = {"costs.tuition_and_fees": "CHG2AY3", "costs.books_and_supplies": BOOKS_COLUMN}
COST_STATUS_COLUMNS = {
    "costs.tuition_and_fees": "XCHG2AY3",
    "costs.books_and_supplies": BOOKS_STATUS_COLUMN,
}
REQUIRED_COLUMNS = frozenset({UNITID_COLUMN, *COST_COLUMNS.values()})
