import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from education_roi.ipeds import (
    IPEDSCatalogError,
    IPEDSComponent,
    IPEDSInventoryChangeType,
    IPEDSPublicationStatus,
    IPEDSRelease,
    IPEDSReleaseCatalog,
    compare_release_catalogs,
    select_release,
)

PROJECT_ROOT = Path(__file__).parents[2]


def release(
    year: int,
    status: IPEDSPublicationStatus,
    component: IPEDSComponent = IPEDSComponent.ACADEMIC_YEAR_CHARGES,
) -> IPEDSRelease:
    release_id = f"{year}-{str(year + 1)[-2:]}-{status.value}"
    return IPEDSRelease.model_validate(
        {
            "release_id": release_id,
            "collection_year": year,
            "component": component,
            "publication_status": status,
            "data_url": f"https://nces.ed.gov/ipeds/datacenter/data/{release_id}.zip",
            "dictionary_url": (
                f"https://nces.ed.gov/ipeds/datacenter/data/{release_id}-dictionary.xlsx"
            ),
            "inventory_url": "https://nces.ed.gov/ipeds/datacenter/InstitutionList.aspx",
        }
    )


def catalog(*releases: IPEDSRelease) -> IPEDSReleaseCatalog:
    return IPEDSReleaseCatalog(reviewed_at="2026-09-20", releases=releases)


def test_default_selects_newest_final_for_exact_component() -> None:
    inventory = catalog(
        release(2023, IPEDSPublicationStatus.FINAL),
        release(2024, IPEDSPublicationStatus.PROVISIONAL),
        release(
            2025,
            IPEDSPublicationStatus.PROVISIONAL,
            IPEDSComponent.INSTITUTIONAL_CHARACTERISTICS,
        ),
    )
    selected = select_release(inventory, IPEDSComponent.ACADEMIC_YEAR_CHARGES)
    assert selected.release_id == "2023-24-final"


def test_nonfinal_exact_release_requires_explicit_opt_in() -> None:
    inventory = catalog(release(2024, IPEDSPublicationStatus.PROVISIONAL))
    with pytest.raises(IPEDSCatalogError, match="explicit opt-in required"):
        select_release(
            inventory,
            IPEDSComponent.ACADEMIC_YEAR_CHARGES,
            release_id="2024-25-provisional",
        )
    selected = select_release(
        inventory,
        IPEDSComponent.ACADEMIC_YEAR_CHARGES,
        release_id="2024-25-provisional",
        allow_nonfinal=True,
    )
    assert selected.publication_status is IPEDSPublicationStatus.PROVISIONAL


def test_default_does_not_fall_back_to_provisional() -> None:
    inventory = catalog(release(2024, IPEDSPublicationStatus.PROVISIONAL))
    with pytest.raises(IPEDSCatalogError, match="no final"):
        select_release(inventory, IPEDSComponent.ACADEMIC_YEAR_CHARGES)


def test_catalog_rejects_nonofficial_urls_and_inconsistent_release_ids() -> None:
    payload = release(2023, IPEDSPublicationStatus.FINAL).model_dump()
    with pytest.raises(ValidationError, match="official NCES domain"):
        IPEDSRelease.model_validate({**payload, "data_url": "https://example.com/data.zip"})
    with pytest.raises(ValidationError, match="collection year"):
        IPEDSRelease.model_validate({**payload, "release_id": "2022-23-final"})


def test_catalog_file_is_strict_and_duplicate_pairs_are_rejected(tmp_path: Path) -> None:
    item = release(2023, IPEDSPublicationStatus.FINAL)
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "reviewed_at": "2026-09-20",
                "releases": [item.model_dump(mode="json"), item.model_dump(mode="json")],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(IPEDSCatalogError, match="duplicate"):
        IPEDSReleaseCatalog.from_file(path)


def test_reviewed_catalog_pins_official_provisional_charge_pair() -> None:
    inventory = IPEDSReleaseCatalog.from_file(
        PROJECT_ROOT / "data/manifests/ipeds-release-catalog.json"
    )
    selected = select_release(
        inventory,
        IPEDSComponent.ACADEMIC_YEAR_CHARGES,
        release_id="2023-24-provisional",
        allow_nonfinal=True,
    )
    assert str(selected.data_url) == ("https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip")
    assert str(selected.dictionary_url) == (
        "https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY_Dict.zip"
    )
    with pytest.raises(IPEDSCatalogError, match="no final"):
        select_release(inventory, IPEDSComponent.ACADEMIC_YEAR_CHARGES)


def test_reviewed_gr_sources_keep_legacy_final_distinct_from_default() -> None:
    inventory = IPEDSReleaseCatalog.from_file(
        PROJECT_ROOT / "data/manifests/ipeds-release-catalog.json"
    )
    legacy = select_release(inventory, IPEDSComponent.GRADUATION_RATES, release_id="2022-23-final")
    assert str(legacy.data_url) == "https://nces.ed.gov/ipeds/datacenter/data/GR2022.zip"
    assert str(legacy.dictionary_url) == (
        "https://nces.ed.gov/ipeds/datacenter/data/GR2022_Dict.zip"
    )
    assert legacy.data_member == "gr2022_rv.csv"
    assert select_release(inventory, IPEDSComponent.GRADUATION_RATES).release_id == (
        "2023-24-final"
    )


def test_inventory_comparison_classifies_changes_without_promoting_them() -> None:
    retained = release(2023, IPEDSPublicationStatus.FINAL)
    changed_payload = retained.model_dump()
    changed_payload["dictionary_url"] = (
        "https://nces.ed.gov/ipeds/complete-data-files/revised-dictionary.zip"
    )
    changed = IPEDSRelease.model_validate(changed_payload)
    missing = release(2022, IPEDSPublicationStatus.FINAL)
    discovered = release(2024, IPEDSPublicationStatus.PROVISIONAL)

    comparison = compare_release_catalogs(
        catalog(retained, missing),
        IPEDSReleaseCatalog(
            reviewed_at="2026-09-21",
            releases=(changed, discovered),
        ),
    )

    assert comparison.review_required
    assert comparison.reviewed_at == "2026-09-20"
    assert comparison.observed_at == "2026-09-21"
    assert [item.change_type for item in comparison.changes] == [
        IPEDSInventoryChangeType.MISSING,
        IPEDSInventoryChangeType.CHANGED,
        IPEDSInventoryChangeType.DISCOVERED,
    ]
    assert comparison.changes[1].previous == retained
    assert comparison.changes[1].observed == changed


def test_identical_inventory_comparison_is_deterministically_empty() -> None:
    item = release(2023, IPEDSPublicationStatus.FINAL)
    comparison = compare_release_catalogs(catalog(item), catalog(item))
    assert not comparison.review_required
    assert comparison.changes == ()
