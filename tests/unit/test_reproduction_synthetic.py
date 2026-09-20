from education_roi.reproduction.synthetic import (
    SYNTHETIC_FIXTURE_VERSION,
    synthetic_provisional_request,
)


def test_synthetic_fixture_is_hashed_and_unmistakably_provisional() -> None:
    request = synthetic_provisional_request()
    assert SYNTHETIC_FIXTURE_VERSION == "synthetic-zhang-smoke-v2"
    assert len(request.configuration_hash) == 64
    assert all(len(value) == 64 for value in request.dataset_hashes)
    assert request.blockers[0].startswith("SYNTHETIC FIXTURE")
    assert request.target_observations[0].target.paper_reference.startswith("synthetic fixture")
    assert all(
        "not paper coefficients" in fixture.coefficients.coefficient_source
        for fixture in request.profile_fixtures
    )
    assert len(request.public_cost_reproductions) == 2
    available, missing = request.public_cost_reproductions
    assert available.sensitivity is not None
    assert available.sensitivity.base.evidence.value == "PUBLIC_SUBSTITUTE"
    assert missing.candidates == ()
    assert missing.sensitivity is None
