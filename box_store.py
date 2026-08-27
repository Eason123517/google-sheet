"""
ULD / 箱型資料存取穩定入口。

本地：boxes.json
未來：box_store_gsheets.py

compatible_zones 用於區分：
- A333_GENERIC
- B777_UPPER_BM
- 未來 B777_REAR_UPPER / B777_LOWER 等
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
JSON_PATH = APP_DIR / "boxes.json"

CANONICAL_COLUMNS = [
    "box_id",
    "name",
    "l",
    "w",
    "h",
    "max_weight",
    "compatible_aircraft",
    "compatible_zones",
    "allow_center_load",
    "center_positions",
    "enabled",
    "notes",
]

DEFAULT_BOXES = [
    {
        "box_id": "64",
        "name": "PMC",
        "l": 318.0,
        "w": 244.0,
        "h": 160.0,
        "max_weight": 6800.0,
        "compatible_aircraft": [
            "A333"
        ],
        "compatible_zones": [
            "A333_GENERIC"
        ],
        "allow_center_load": False,
        "center_positions": 2,
        "enabled": True,
        "notes": ""
    },
    {
        "box_id": "PLA",
        "name": "PLA",
        "l": 318.0,
        "w": 153.0,
        "h": 160.0,
        "max_weight": 3175.0,
        "compatible_aircraft": [
            "A333"
        ],
        "compatible_zones": [
            "A333_GENERIC"
        ],
        "allow_center_load": False,
        "center_positions": 2,
        "enabled": True,
        "notes": ""
    },
    {
        "box_id": "118",
        "name": "118",
        "l": 310.0,
        "w": 236.0,
        "h": 300.0,
        "max_weight": 5000.0,
        "compatible_aircraft": [
            "B777"
        ],
        "compatible_zones": [
            "B777_UPPER_BM"
        ],
        "allow_center_load": False,
        "center_positions": 2,
        "enabled": True,
        "notes": ""
    },
    {
        "box_id": "96",
        "name": "96",
        "l": 317.0,
        "w": 243.0,
        "h": 234.0,
        "max_weight": 5000.0,
        "compatible_aircraft": [
            "B777"
        ],
        "compatible_zones": [
            "B777_UPPER_BM"
        ],
        "allow_center_load": False,
        "center_positions": 2,
        "enabled": True,
        "notes": ""
    },
    {
        "box_id": "PGA",
        "name": "PGA",
        "l": 606.0,
        "w": 244.0,
        "h": 300.0,
        "max_weight": 13680.0,
        "compatible_aircraft": [
            "B777"
        ],
        "compatible_zones": [
            "B777_UPPER_BM"
        ],
        "allow_center_load": False,
        "center_positions": 4,
        "enabled": True,
        "notes": ""
    },
    {
        "box_id": "AKE",
        "name": "AKE",
        "l": 156.0,
        "w": 153.0,
        "h": 160.0,
        "max_weight": 1588.0,
        "compatible_aircraft": [
            "A333"
        ],
        "compatible_zones": [
            "A333_GENERIC"
        ],
        "allow_center_load": False,
        "center_positions": 2,
        "enabled": True,
        "notes": ""
    },
    {
        "box_id": "PMC",
        "name": "PMC",
        "l": 318.0,
        "w": 244.0,
        "h": 160.0,
        "max_weight": 6800.0,
        "compatible_aircraft": [
            "B777"
        ],
        "compatible_zones": [
            "B777_UPPER_BM"
        ],
        "allow_center_load": False,
        "center_positions": 2,
        "enabled": True,
        "notes": ""
    }
]


def _parse_list(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = str(value).replace("；", ",").replace("，", ",").split(",")

    result = []

    for x in raw:
        code = str(x).strip().upper()

        if code and code not in result:
            result.append(code)

    return result


def _parse_bool(value, default=True) -> bool:
    if isinstance(value, bool):
        return value

    if value is None or value == "":
        return default

    text = str(value).strip().lower()

    if text in {"1", "true", "yes", "y", "是", "啟用", "on"}:
        return True

    if text in {"0", "false", "no", "n", "否", "停用", "off"}:
        return False

    return default


def normalize_box(box: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "box_name": "name",
        "length": "l",
        "width": "w",
        "height": "h",
        "L": "l",
        "W": "w",
        "H": "h",
        "weight": "max_weight",
        "aircraft": "compatible_aircraft",
        "aircrafts": "compatible_aircraft",
        "compatible_models": "compatible_aircraft",
        "zone": "compatible_zones",
        "zones": "compatible_zones",
        "center_position_count": "center_positions",
        "center_positions_count": "center_positions",
        "allow_center": "allow_center_load",
        "center_loading": "allow_center_load",
        "active": "enabled",
        "remark": "notes",
    }

    normalized = {
        aliases.get(str(k), str(k)): v
        for k, v in box.items()
    }

    box_id = str(normalized.get("box_id", "")).strip()
    name = str(normalized.get("name", "")).strip()

    if not box_id:
        box_id = name or "ULD"

    def num(key: str, default: float = 0.0) -> float:
        value = normalized.get(key, default)

        if value is None or value == "":
            return float(default)

        return float(value)

    compatible = _parse_list(
        normalized.get("compatible_aircraft", [])
    )
    zones = _parse_list(
        normalized.get("compatible_zones", [])
    )

    # Backward compatibility for old local files.
    if not compatible and box_id == "BOX-01":
        compatible = ["A333"]

    if not zones and "A333" in compatible:
        zones = ["A333_GENERIC"]

    return {
        "box_id": box_id,
        "name": name or box_id,
        "l": num("l"),
        "w": num("w"),
        "h": num("h"),
        "max_weight": num("max_weight", 9999.0),
        "compatible_aircraft": compatible,
        "compatible_zones": zones,
        "allow_center_load": _parse_bool(
            normalized.get("allow_center_load", False),
            False,
        ),
        "center_positions": int(num("center_positions", 2)),
        "enabled": _parse_bool(
            normalized.get("enabled", True),
            True,
        ),
        "notes": str(
            normalized.get("notes", "") or ""
        ).strip(),
    }


class JsonBoxStore:
    def __init__(self, path: Path = JSON_PATH):
        self.path = path

    def load_boxes(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            self.save_boxes(DEFAULT_BOXES)

        try:
            raw = json.loads(
                self.path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            raw = []

        if not isinstance(raw, list):
            raw = []

        return [
            normalize_box(x)
            for x in raw
            if isinstance(x, dict)
        ]

    def save_boxes(self, boxes: list[dict[str, Any]]) -> None:
        normalized = [
            normalize_box(x)
            for x in boxes
        ]

        self.path.write_text(
            json.dumps(
                normalized,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


_store = None


def _build_store():
    backend = os.getenv(
        "BOX_STORE_BACKEND",
        "gsheets",
    ).strip().lower()

    if backend in {"json", "local", ""}:
        return JsonBoxStore()

    if backend in {
        "gsheets",
        "google_sheets",
        "google",
    }:
        from box_store_gsheets import GoogleSheetsBoxStore
        return GoogleSheetsBoxStore()

    raise RuntimeError(
        f"未知 BOX_STORE_BACKEND={backend!r}；"
        "可使用 json 或 gsheets。"
    )


def get_box_store():
    global _store

    if _store is None:
        _store = _build_store()

    return _store


def load_boxes() -> list[dict[str, Any]]:
    return get_box_store().load_boxes()


def save_boxes(boxes: list[dict[str, Any]]) -> None:
    get_box_store().save_boxes(boxes)


def storage_backend_name() -> str:
    backend = os.getenv(
        "BOX_STORE_BACKEND",
        "gsheets",
    ).strip().lower()

    if backend in {
        "gsheets",
        "google_sheets",
        "google",
    }:
        return "Google Sheets"

    return "本地 boxes.json"



def storage_connection_info() -> dict:
    store = get_box_store()

    if hasattr(store, "connection_info"):
        return store.connection_info()

    return {
        "backend": "本地 boxes.json",
        "spreadsheet": "",
        "worksheet": "",
    }


def storage_healthcheck() -> tuple[bool, str]:
    store = get_box_store()

    if hasattr(store, "healthcheck"):
        return store.healthcheck()

    return True, "本地 boxes.json 可用"


def seed_missing_default_boxes() -> tuple[int, list[str]]:
    """
    將 DEFAULT_BOXES 中缺少的 ULD 補進目前 storage。
    不覆蓋同 box_id 的既有雲端資料。
    """
    current = load_boxes()
    existing_ids = {
        str(x.get("box_id", "")).strip()
        for x in current
    }

    added = []

    for default in DEFAULT_BOXES:
        box_id = str(default.get("box_id", "")).strip()

        if box_id and box_id not in existing_ids:
            current.append(normalize_box(default))
            existing_ids.add(box_id)
            added.append(box_id)

    if added:
        save_boxes(current)

    return len(added), added
