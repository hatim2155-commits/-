from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Any


class SignalParseError(ValueError):
    """Raised when a router response contains no recognized signal readings."""


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def flatten_response(response: str | Mapping[str, Any]) -> dict[str, str]:
    """Flatten a Huawei XML or decoded response into normalized scalar fields."""
    values: dict[str, str] = {}

    if isinstance(response, str):
        try:
            root = ET.fromstring(response)
        except ET.ParseError as exc:
            raise SignalParseError("استجابة الراوتر ليست XML صالحًا") from exc

        for node in root.iter():
            if len(node) == 0 and node.text and node.text.strip():
                values[_key(node.tag.rsplit("}", 1)[-1])] = node.text.strip()
        return values

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for name, child in item.items():
                if isinstance(child, (str, int, float)) and str(child).strip():
                    values[_key(str(name))] = str(child).strip()
                else:
                    visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(response)
    return values


SIGNAL_FIELDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "4G LTE": (
        ("lte_rsrp", "rsrp"),
        ("lte_rsrq", "rsrq"),
        ("lte_sinr", "sinr", "lte_snr"),
        ("lte_pci", "pci"),
        ("lte_band", "band"),
        ("lte_earfcn", "earfcn"),
        ("lte_cell_id", "cell_id"),
    ),
    "5G NR": (
        ("nr_rsrp", "nrrsrp", "nr5g_rsrp"),
        ("nr_rsrq", "nrrsrq", "nr5g_rsrq"),
        ("nr_sinr", "nrsinr", "nr5g_sinr"),
        ("nr_pci", "nrpci", "nr5g_pci"),
        ("nr_band", "nrbands", "nr5g_band"),
        ("nr_arfcn", "nrarfcn", "nr5g_arfcn"),
        ("nr_cell_id", "nrcellid", "nr5g_cell_id"),
    ),
}

FIELD_LABELS = {
    "rsrp": ("RSRP", "dBm"),
    "rsrq": ("RSRQ", "dB"),
    "sinr": ("SINR", "dB"),
    "pci": ("PCI", ""),
    "band": ("النطاق", ""),
    "earfcn": ("EARFCN", ""),
    "cell_id": ("معرّف الخلية", ""),
    "arfcn": ("NR-ARFCN", ""),
}


def parse_signal_response(
    response: str | Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    """Return only fields explicitly present in the router's signal response."""
    values = flatten_response(response)
    readings: dict[str, dict[str, str]] = {"4G LTE": {}, "5G NR": {}}

    for technology, fields in SIGNAL_FIELDS.items():
        for aliases in fields:
            value = next((values[_key(alias)] for alias in aliases if _key(alias) in values), None)
            if value is None or value.casefold() in {"", "null", "none", "n/a", "--"}:
                continue
            canonical = _key(aliases[0])
            metric = canonical.removeprefix("lte").removeprefix("nr").removeprefix("5g")
            if metric == "cellid":
                metric = "cell_id"
            if metric not in FIELD_LABELS:
                continue
            label, unit = FIELD_LABELS[metric]
            value = re.sub(r"\s*(?:dbm|db)$", "", value, flags=re.IGNORECASE).strip()
            if value.casefold() in {"", "unknown", "no service", "n/a", "---"}:
                continue
            if metric in {"rsrp", "rsrq", "sinr"} and not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
                continue
            if metric in {"rsrp", "rsrq"} and value in {"0", "255", "-32768", "2147483647"}:
                continue
            readings[technology][label] = f"{value} {unit}".strip()

    if not any(readings.values()):
        raise SignalParseError(
            "وصل رد من الراوتر لكنه لا يحتوي على حقول إشارة معروفة؛ "
            "قد تختلف واجهة هذا الطراز."
        )
    return readings


def parse_cell_info(response: str | Mapping[str, Any]) -> dict[str, str]:
    """Extract serving-cell identifiers when the router provides them."""
    values = flatten_response(response)
    aliases = {
        "معرّف الخلية": ("cell_id", "cellid", "cell_identity"),
        "PCI": ("pci", "physical_cell_id"),
        "النطاق": ("band", "frequency_band"),
        "القناة": ("earfcn", "arfcn", "dl_earfcn"),
        "نوع الشبكة": ("network_type", "currentnetworktype", "rat"),
    }
    result = {}
    for label, names in aliases.items():
        value = next((values[_key(name)] for name in names if _key(name) in values), None)
        if value and value.casefold() not in {"null", "none", "n/a", "--"}:
            result[label] = value
    return result
