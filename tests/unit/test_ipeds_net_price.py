"""Final SFA2223 exact population net-price evidence."""

import json
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from education_roi.cli.app import app
from education_roi.config.paths import ProjectPaths
from education_roi.ipeds.catalog import IPEDSComponent, IPEDSReleaseCatalog, select_release
from education_roi.ipeds.net_price import (
    FIELDS,
    IPEDSNetPriceError,
    NetPriceBasis,
    read_net_price_rows,
    register_net_price,
    resolve_net_price,
    verify_net_price_dictionary,
)
from education_roi.provenance.downloader import DownloadResult
from education_roi.provenance.store import Registry

CATALOG = Path(__file__).parents[2] / "data/manifests/ipeds-release-catalog.json"
HEADER = "UNITID,NPIST2,XNPIST2,NPIS412,XNPIS412,NPGRN2,XNPGRN2,NPT412,XNPT412\n"


def sources(root: Path, rows: str) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    data, dictionary = root / "SFA2223.zip", root / "SFA2223_Dict.zip"
    with ZipFile(data, "w") as output:
        output.writestr("sfa2223.csv", HEADER + "236948,999,R,999,R,,, ,\n")
        output.writestr("sfa2223_RV.csv", HEADER + rows)
    with ZipFile(dictionary, "w") as output:
        output.writestr("sfa2223.xlsx", b"fixture")
    return data, dictionary


def test_dictionary_requires_reviewed_populations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dictionary = sources(tmp_path, "236948,11023,R,6398,R,,A,,A\n")[1]
    definitions = [["", code, "", "", "", "X" + code, label] for code, label, *_ in FIELDS.values()]
    descriptions = [
        ["", code, population + " " + reporting]
        for code, _, population, reporting in FIELDS.values()
    ]

    def rows(data: bytes, *, sheet_names: frozenset[str]) -> list[list[str]]:
        if sheet_names == {"Introduction"}:
            return [["(Final/revised release)"]]
        if sheet_names == {"Varlist"}:
            return definitions
        assert sheet_names == {"Description"}
        return descriptions

    monkeypatch.setattr("education_roi.ipeds.net_price._xlsx_rows", rows)
    verify_net_price_dictionary(dictionary)
    descriptions[0][2] = "Different population"
    with pytest.raises(IPEDSNetPriceError, match="reviewed population"):
        verify_net_price_dictionary(dictionary)


@pytest.mark.parametrize(
    "rows",
    [
        "236948,1,R,2,R,,A,,A\n236948,3,R,4,R,,A,,A\n",
        "236948,nope,R,2,R,,A,,A\n",
        "236948,1,R,2,R,,A,,A,extra\n",
    ],
)
def test_rejects_malformed_rows(tmp_path: Path, rows: str) -> None:
    data = sources(tmp_path, rows)[0]
    with pytest.raises(IPEDSNetPriceError):
        read_net_price_rows(data, "sfa2223_RV.csv")


def test_registration_and_exact_basis_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("education_roi.ipeds.net_price.verify_net_price_dictionary", lambda p: None)
    release = select_release(
        IPEDSReleaseCatalog.from_file(CATALOG), IPEDSComponent.STUDENT_FINANCIAL_AID
    )
    data, dictionary = sources(
        tmp_path / "source", "236948,11023,R,6398,R,,A,,A\n236949,0,R,-1,C,555,R,444,R\n"
    )

    class Downloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            destination_directory.mkdir(parents=True, exist_ok=True)
            self.index += 1
            target = destination_directory / f"download-{self.index}.zip"
            copyfile((data, dictionary)[self.index - 1], target)
            return DownloadResult(target, url, url, target.stat().st_size)

    root = tmp_path / "project"
    registered = register_net_price(release, ProjectPaths(root), downloader=Downloader())  # type: ignore[arg-type]
    registry = Registry(root / "data/manifests/registry.sqlite")
    actual_data = (
        root / "data/raw" / registry.get_artifact(registered.data.artifact_id).storage_path
    )
    actual_dictionary = (
        root / "data/raw" / registry.get_artifact(registered.dictionary.artifact_id).storage_path
    )
    args = (actual_data, actual_dictionary, release, registered.data, registered.dictionary)
    public = resolve_net_price(*args, 236948, NetPriceBasis.PUBLIC_GRANT)
    assert (public.status, public.average_net_price, public.source_field, public.source_status) == (
        "OBSERVED",
        11023,
        "NPIST2",
        "R",
    )
    assert (
        resolve_net_price(*args, 236948, NetPriceBasis.PUBLIC_TITLE_IV_0_30K).average_net_price
        == 6398
    )
    other = resolve_net_price(*args, 236948, NetPriceBasis.OTHER_GRANT)
    assert (
        other.status,
        other.average_net_price,
        other.raw_average_net_price,
        other.source_status,
    ) == ("INSUFFICIENT_DATA", None, "", "A")
    assert resolve_net_price(*args, 236949, NetPriceBasis.PUBLIC_GRANT).average_net_price == 0
    negative = resolve_net_price(*args, 236949, NetPriceBasis.PUBLIC_TITLE_IV_0_30K)
    assert (negative.status, negative.raw_average_net_price, negative.source_status) == (
        "INSUFFICIENT_DATA",
        "-1",
        "C",
    )
    assert (
        resolve_net_price(*args, 999999, NetPriceBasis.PUBLIC_GRANT).status == "INSUFFICIENT_DATA"
    )
    cli = CliRunner().invoke(
        app,
        [
            "ipeds",
            "resolve-net-price",
            "236948",
            "public_in_state_grant",
            "--catalog",
            str(CATALOG),
            "--root",
            str(root),
        ],
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["average_net_price"] == 11023
    actual_data.chmod(0o644)
    actual_data.write_bytes(b"tampered")
    with pytest.raises(IPEDSNetPriceError, match="bytes do not match"):
        resolve_net_price(*args, 236948, NetPriceBasis.PUBLIC_GRANT)


def test_immutable_net_price_table_preserves_each_basis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import polars as pl

    from education_roi.ipeds.net_price_evidence import (
        IPEDSNetPriceTableError,
        resolve_net_price_evidence,
    )
    from education_roi.ipeds.net_price_pipeline import BASIS_FIELDS, VERSION, transform_net_price
    from education_roi.ipeds.pipeline import IPEDSProcessedArtifactConflict
    from education_roi.provenance.integrity import sha256_file

    monkeypatch.setattr("education_roi.ipeds.net_price.verify_net_price_dictionary", lambda p: None)
    monkeypatch.setattr(
        "education_roi.ipeds.net_price_pipeline.verify_net_price_dictionary", lambda p: None
    )
    release = select_release(
        IPEDSReleaseCatalog.from_file(CATALOG), IPEDSComponent.STUDENT_FINANCIAL_AID
    )
    data, dictionary = sources(
        tmp_path / "source", "236948,11023,R,6398,R,,A,,A\n236949,0,R,-1,C,555,R,444,R\n"
    )

    class Downloader:
        index = 0

        def download(
            self, url: str, destination_directory: Path, allowed_domains: tuple[str, ...]
        ) -> DownloadResult:
            destination_directory.mkdir(parents=True, exist_ok=True)
            self.index += 1
            target = destination_directory / f"download-{self.index}.zip"
            copyfile((data, dictionary)[self.index - 1], target)
            return DownloadResult(target, url, url, target.stat().st_size)

    root = tmp_path / "project"
    pair = register_net_price(release, ProjectPaths(root), downloader=Downloader())  # type: ignore[arg-type]
    registry = Registry(root / "data/manifests/registry.sqlite")
    actual_data = root / "data/raw" / registry.get_artifact(pair.data.artifact_id).storage_path
    actual_dictionary = (
        root / "data/raw" / registry.get_artifact(pair.dictionary.artifact_id).storage_path
    )
    args = (
        actual_data,
        actual_dictionary,
        root / "data/processed",
        pair.data,
        pair.dictionary,
        release,
    )
    result = transform_net_price(*args)
    frame = pl.read_parquet(result.parquet_path)
    assert frame.height == 2
    assert result.manifest.key_columns == ("unitid",)
    assert result.manifest.transformation.parameters["basis_fields"] == json.dumps(
        dict(BASIS_FIELDS), sort_keys=True
    )
    assert frame["transformation_version"].to_list() == [VERSION, VERSION]
    first, second = frame.to_dicts()
    assert (first["public_in_state_grant"], first["public_in_state_title_iv_0_30k"]) == (
        11023,
        6398,
    )
    assert (
        first["other_reporting_grant"],
        first["raw_other_reporting_grant"],
        first["status_other_reporting_grant"],
    ) == (None, "", "A")
    assert (
        second["public_in_state_grant"],
        second["public_in_state_title_iv_0_30k"],
        second["raw_public_in_state_title_iv_0_30k"],
    ) == (0, None, "-1")
    assert (second["other_reporting_grant"], second["other_reporting_title_iv_0_30k"]) == (555, 444)
    assert result.manifest.transformation.output_sha256 == sha256_file(result.parquet_path)[0]
    observed = resolve_net_price_evidence(result.parquet_path, 236948, NetPriceBasis.PUBLIC_GRANT)
    assert (observed.status, observed.average_net_price, observed.source_field) == (
        "OBSERVED",
        11023,
        "NPIST2",
    )
    assert observed.table_sha256 == result.manifest.transformation.output_sha256
    other = resolve_net_price_evidence(result.parquet_path, 236948, NetPriceBasis.OTHER_GRANT)
    assert (
        other.status,
        other.average_net_price,
        other.raw_average_net_price,
        other.source_status,
    ) == ("INSUFFICIENT_DATA", None, "", "A")
    assert (
        resolve_net_price_evidence(
            result.parquet_path, 236949, NetPriceBasis.PUBLIC_GRANT
        ).average_net_price
        == 0
    )
    assert (
        resolve_net_price_evidence(result.parquet_path, 999999, NetPriceBasis.PUBLIC_GRANT).status
        == "INSUFFICIENT_DATA"
    )
    cli_lookup = CliRunner().invoke(
        app,
        [
            "ipeds",
            "resolve-net-price-table",
            str(result.parquet_path),
            "236948",
            "public_in_state_title_iv_0_30k",
        ],
    )
    assert cli_lookup.exit_code == 0, cli_lookup.stdout
    assert json.loads(cli_lookup.stdout)["average_net_price"] == 6398
    repeat = transform_net_price(*args)
    assert repeat.manifest_path == result.manifest_path
    assert repeat.manifest == result.manifest
    cli = CliRunner().invoke(
        app, ["ipeds", "build-net-price", "--catalog", str(CATALOG), "--root", str(root)]
    )
    assert cli.exit_code == 0, cli.stdout
    assert json.loads(cli.stdout)["manifest"]["row_count"] == 2
    original_table = result.parquet_path.read_bytes()
    original_manifest = result.manifest_path.read_bytes()
    forged = frame.with_columns(
        pl.when(pl.col("unitid") == 236948)
        .then(pl.lit(99999))
        .otherwise(pl.col("public_in_state_grant"))
        .alias("public_in_state_grant")
    )
    result.parquet_path.chmod(0o644)
    forged.write_parquet(
        result.parquet_path, compression="zstd", statistics=True, row_group_size=100_000
    )
    altered_hash = sha256_file(result.parquet_path)[0]
    sidecar = json.loads(original_manifest)
    sidecar["transformation"]["output_sha256"] = altered_hash
    sidecar["transformation"]["transformation_id"] = (
        f"{VERSION}:{release.release_id}:{pair.data.sha256}:{pair.dictionary.sha256}:{altered_hash}"
    )
    result.manifest_path.chmod(0o644)
    result.manifest_path.write_text(json.dumps(sidecar))
    with pytest.raises(IPEDSNetPriceTableError, match="source cell"):
        resolve_net_price_evidence(result.parquet_path, 236948, NetPriceBasis.OTHER_GRANT)
    result.parquet_path.write_bytes(original_table)
    result.manifest_path.write_bytes(original_manifest)
    result.parquet_path.chmod(0o644)
    result.parquet_path.write_bytes(b"tampered")
    with pytest.raises(IPEDSNetPriceTableError, match="hash differs"):
        resolve_net_price_evidence(result.parquet_path, 236948, NetPriceBasis.PUBLIC_GRANT)
    with pytest.raises(IPEDSProcessedArtifactConflict, match="different bytes"):
        transform_net_price(*args)
