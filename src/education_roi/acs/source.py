"""ACS PUMS source registration policy."""

from education_roi.provenance.models import DatasetDefinition

ACS_PUMS_DATASET = DatasetDefinition(
    dataset_id="acs-pums",
    publisher="U.S. Census Bureau",
    name="American Community Survey Public Use Microdata Sample",
    allowed_domains=("census.gov",),
)

REQUIRED_PERSON_COLUMNS = frozenset(
    {
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
    }
)
