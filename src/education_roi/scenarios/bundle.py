"""Immutable deterministic comparison-run bundles with integrity verification."""

import csv
from hashlib import sha256
from io import StringIO
from json import dumps, loads
from pathlib import Path
from shutil import rmtree

from education_roi.scenarios.analysis import EarningsFixture
from education_roi.scenarios.comparison import ComparisonReport
from education_roi.scenarios.models import ResolvedScenarioGraph
from education_roi.scenarios.resolution import ResolvedConfigurationGraph


class ComparisonBundleError(ValueError):
    pass


def _json(value: object) -> str:
    return dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def _digest(content: bytes) -> str:
    return sha256(content).hexdigest()


def _csv(report: ComparisonReport) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "record_type",
            "option_id",
            "counterfactual_id",
            "perspective",
            "status",
            "npv",
            "irr_status",
            "irr_roots",
            "lifetime_net_value",
            "lifetime_earnings",
            "break_even_age",
        ]
    )

    def write_row(
        record_type: str,
        option_id: str,
        counterfactual_id: str,
        status: str,
        result: dict[str, object] | None,
    ) -> None:
        metrics = None if result is None else result.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        irr = metrics.get("internal_rate_of_return", {})
        irr = irr if isinstance(irr, dict) else {}
        break_even = metrics.get("break_even", {})
        break_even = break_even if isinstance(break_even, dict) else {}
        writer.writerow(
            [
                record_type,
                option_id,
                counterfactual_id,
                report.perspective.value,
                status,
                metrics.get("net_present_value", ""),
                irr.get("status", ""),
                ";".join(str(item) for item in irr.get("roots", [])),
                metrics.get("lifetime_net_value", ""),
                metrics.get("lifetime_earnings", ""),
                break_even.get("age", ""),
            ]
        )

    for analysis in report.scenario_analyses:
        write_row(
            "scenario_vs_common_counterfactual",
            analysis.scenario_id,
            report.common_counterfactual_id,
            analysis.status.value,
            analysis.result,
        )
    for pair in report.pairwise_comparisons:
        write_row(
            "pairwise_option_comparison",
            pair.option_id,
            pair.counterfactual_id,
            pair.status.value,
            pair.result,
        )
    return stream.getvalue()


def write_comparison_bundle(
    destination: Path,
    *,
    scenario_files: tuple[Path, ...],
    source_graph: ResolvedScenarioGraph,
    resolved_graph: ResolvedConfigurationGraph,
    earnings_fixture: EarningsFixture,
    report: ComparisonReport,
) -> Path:
    if destination.exists():
        raise ComparisonBundleError(f"run directory already exists: {destination}")
    names = tuple(path.name for path in scenario_files)
    if len(names) != len(set(names)):
        raise ComparisonBundleError("scenario filenames must be unique within a run bundle")
    try:
        destination.mkdir(parents=True)
        scenario_dir = destination / "scenarios"
        scenario_dir.mkdir()
        contents: dict[str, bytes] = {}
        for path in sorted(scenario_files, key=lambda item: item.name):
            contents[f"scenarios/{path.name}"] = path.read_bytes()
        contents.update(
            {
                "resolved.json": _json(resolved_graph.as_dict()).encode(),
                "earnings.json": _json(earnings_fixture.model_dump(mode="json")).encode(),
                "comparison.json": _json(report.as_dict()).encode(),
                "results.csv": _csv(report).encode(),
                "assumptions.json": _json(
                    {
                        item.id: item.assumptions.model_dump(mode="json")
                        for item in source_graph.scenarios
                    }
                ).encode(),
                "datasets.json": _json(
                    {
                        item.id: [
                            entry.model_dump(mode="json") for entry in item.dataset_references
                        ]
                        for item in resolved_graph.scenarios
                    }
                ).encode(),
                "validation.json": _json(
                    {
                        "status": report.status.value,
                        "provisional": report.provisional,
                        "findings": list(report.validation_findings),
                    }
                ).encode(),
            }
        )
        for relative, content in contents.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        manifest = {
            "schema_version": "1.0",
            "report_hash": report.report_hash,
            "files": [
                {"path": path, "sha256": _digest(content), "size": len(content)}
                for path, content in sorted(contents.items())
            ],
        }
        (destination / "manifest.json").write_text(_json(manifest), encoding="utf-8")
    except Exception:
        if destination.exists():
            rmtree(destination)
        raise
    return destination


def verify_comparison_bundle(destination: Path) -> dict[str, object]:
    try:
        manifest = loads((destination / "manifest.json").read_text(encoding="utf-8"))
        for record in manifest["files"]:
            path = destination / record["path"]
            content = path.read_bytes()
            if len(content) != record["size"] or _digest(content) != record["sha256"]:
                raise ComparisonBundleError(f"integrity mismatch: {record['path']}")
    except (OSError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, ComparisonBundleError):
            raise
        raise ComparisonBundleError(f"invalid comparison bundle: {error}") from error
    return manifest
