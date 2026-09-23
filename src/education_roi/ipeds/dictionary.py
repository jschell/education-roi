"""Parse and validate IPEDS dictionary archives without spreadsheet dependencies."""

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from education_roi.ipeds.source import REQUIRED_COLUMNS


class IPEDSDictionaryError(ValueError):
    """The paired IPEDS dictionary is unreadable or lacks required definitions."""


@dataclass(frozen=True)
class IPEDSVariableDefinition:
    name: str
    metadata: tuple[str, ...]


def _csv_rows(data: bytes) -> list[list[str]]:
    text = data.decode("utf-8-sig")
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text))]


def _xlsx_rows(data: bytes, *, sheet_names: frozenset[str] | None = None) -> list[list[str]]:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        with ZipFile(io.BytesIO(data)) as workbook:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in workbook.namelist():
                root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
                shared = ["".join(node.itertext()) for node in root.findall(f"{namespace}si")]
            sheets = sorted(
                name
                for name in workbook.namelist()
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
            )
            if sheet_names is not None:
                workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
                relationship_root = ElementTree.fromstring(
                    workbook.read("xl/_rels/workbook.xml.rels")
                )
                relationship_ids = {
                    element.attrib["Id"]: element.attrib["Target"]
                    for element in relationship_root.iter()
                    if element.tag.endswith("}Relationship")
                }
                selected = set()
                for element in workbook_root.iter():
                    if element.tag.endswith("}sheet") and element.attrib.get("name") in sheet_names:
                        identifier = element.attrib.get(
                            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                        )
                        target = relationship_ids.get(identifier or "", "")
                        path = target.lstrip("/") if target.startswith("/xl/") else "xl/" + target
                        if path in sheets:
                            selected.add(path)
                if len(selected) != len(sheet_names):
                    raise IPEDSDictionaryError("required workbook worksheet is missing")
                sheets = sorted(selected)
            rows: list[list[str]] = []
            for sheet in sheets:
                root = ElementTree.fromstring(workbook.read(sheet))
                for row in root.iter(f"{namespace}row"):
                    cells: list[str] = []
                    for cell in row.findall(f"{namespace}c"):
                        kind = cell.attrib.get("t")
                        value_node = cell.find(f"{namespace}v")
                        if kind == "inlineStr":
                            text_node = cell.find(f"{namespace}is")
                            value = "" if text_node is None else "".join(text_node.itertext())
                        elif value_node is None:
                            value = ""
                        elif kind == "s":
                            value = shared[int(value_node.text or "0")]
                        else:
                            value = value_node.text or ""
                        cells.append(value.strip())
                    rows.append(cells)
            return rows
    except (BadZipFile, KeyError, ValueError, ElementTree.ParseError) as error:
        raise IPEDSDictionaryError(f"could not parse IPEDS dictionary workbook: {error}") from error


def read_dictionary(path: Path) -> dict[str, IPEDSVariableDefinition]:
    """Extract required variable definitions from the paired CSV/XLSX dictionary ZIP."""
    try:
        with ZipFile(path) as archive:
            members = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".csv", ".xlsx")) and not name.startswith("__MACOSX/")
            ]
            if len(members) != 1:
                raise IPEDSDictionaryError(
                    "IPEDS dictionary archive must contain exactly one CSV or XLSX file"
                )
            data = archive.read(members[0])
            rows = _csv_rows(data) if members[0].lower().endswith(".csv") else _xlsx_rows(data)
    except (OSError, BadZipFile, KeyError, UnicodeError, csv.Error) as error:
        raise IPEDSDictionaryError(f"could not read IPEDS dictionary archive: {error}") from error

    definitions: dict[str, IPEDSVariableDefinition] = {}
    for row in rows:
        normalized = {cell.upper() for cell in row}
        for variable in REQUIRED_COLUMNS.intersection(normalized):
            if variable in definitions:
                raise IPEDSDictionaryError(f"duplicate dictionary definition for {variable}")
            definitions[variable] = IPEDSVariableDefinition(variable, tuple(row))
    missing = sorted(REQUIRED_COLUMNS.difference(definitions))
    if missing:
        raise IPEDSDictionaryError("IPEDS dictionary is missing variables: " + ", ".join(missing))
    return definitions
