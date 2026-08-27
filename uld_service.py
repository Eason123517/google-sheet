from __future__ import annotations

from typing import Iterable

import pandas as pd

from b777_uld_rules import (
    ULD_114_LENGTH_CM,
    ULD_114_MAX_CARGO_HEIGHT_CM,
    ULD_114_WIDTH_CM,
    ULD_96_LENGTH_CM,
    ULD_96_WIDTH_CM,
    ULD_96_MAX_CARGO_HEIGHT_CM,
    normalized_uld_id,
    requires_upper_deck,
)


EDITOR_COLUMNS = [
    "ULD ID",
    "名稱",
    "長(cm)",
    "寬(cm)",
    "高(cm)",
    "最大載重(kg)",
    "適用機型",
    "適用區域",
    "可中央裝載",
    "中央裝載盤位數",
    "啟用",
    "備註",
]


def _aircraft_list(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        text = str(value).replace("；", ",").replace("，", ",")
        raw = text.split(",")

    result = []
    for x in raw:
        code = str(x).strip().upper()
        if code and code not in result:
            result.append(code)
    return result


def get_compatible_ulds(
    boxes: list[dict],
    aircraft_code: str,
    enabled_only: bool = True,
    zone: str | None = None,
) -> list[dict]:
    code = aircraft_code.strip().upper()
    zone_code = zone.strip().upper() if zone else None
    result = []

    for box in boxes:
        if enabled_only and not bool(box.get("enabled", True)):
            continue

        compatible = _aircraft_list(box.get("compatible_aircraft", []))
        if code not in compatible:
            continue

        if zone_code:
            zones = _aircraft_list(box.get("compatible_zones", []))
            if zone_code not in zones:
                continue

        result.append(box)

    return result


def boxes_to_editor_dataframe(boxes: list[dict]) -> pd.DataFrame:
    rows = []

    for box in boxes:
        rows.append(
            {
                "ULD ID": box.get("box_id", ""),
                "名稱": box.get("name", ""),
                "長(cm)": float(box.get("l", 0) or 0),
                "寬(cm)": float(box.get("w", 0) or 0),
                "高(cm)": float(box.get("h", 0) or 0),
                "最大載重(kg)": float(box.get("max_weight", 0) or 0),
                "適用機型": ",".join(_aircraft_list(box.get("compatible_aircraft", []))),
                "適用區域": ",".join(_aircraft_list(box.get("compatible_zones", []))),
                "可中央裝載": bool(box.get("allow_center_load", False)),
                "中央裝載盤位數": int(box.get("center_positions", 2) or 2),
                "啟用": bool(box.get("enabled", True)),
                "備註": str(box.get("notes", "") or ""),
            }
        )

    return pd.DataFrame(rows, columns=EDITOR_COLUMNS)


def editor_dataframe_to_boxes(
    df: pd.DataFrame,
    valid_aircraft_codes: Iterable[str],
) -> list[dict]:
    valid_codes = {str(x).strip().upper() for x in valid_aircraft_codes}
    boxes = []

    for _, row in df.iterrows():
        box_id = str(row.get("ULD ID", "") or "").strip()
        name = str(row.get("名稱", "") or "").strip()

        # Dynamic editor's blank row is ignored.
        if not box_id and not name:
            continue

        compatible = _aircraft_list(row.get("適用機型", ""))
        zones = _aircraft_list(row.get("適用區域", ""))
        allow_center_load = bool(row.get("可中央裝載", False))

        try:
            center_positions = int(float(row.get("中央裝載盤位數", 2) or 2))
        except Exception:
            center_positions = 0

        boxes.append(
            {
                "box_id": box_id,
                "name": name,
                "l": float(row.get("長(cm)", 0) or 0),
                "w": float(row.get("寬(cm)", 0) or 0),
                "h": float(row.get("高(cm)", 0) or 0),
                "max_weight": float(row.get("最大載重(kg)", 0) or 0),
                "compatible_aircraft": compatible,
                "compatible_zones": zones,
                "allow_center_load": allow_center_load,
                "center_positions": center_positions,
                "enabled": bool(row.get("啟用", True)),
                "notes": str(row.get("備註", "") or "").strip(),
            }
        )

    return boxes


def validate_uld_records(
    boxes: list[dict],
    valid_aircraft_codes: Iterable[str],
) -> list[str]:
    errors = []
    valid_codes = {str(x).strip().upper() for x in valid_aircraft_codes}
    seen = set()

    for index, box in enumerate(boxes, 1):
        box_id = str(box.get("box_id", "")).strip()
        name = str(box.get("name", "")).strip()

        if not box_id:
            errors.append(f"第 {index} 列：ULD ID 不可空白。")
            continue

        if box_id in seen:
            errors.append(f"第 {index} 列：ULD ID「{box_id}」重複。")
        seen.add(box_id)

        if not name:
            errors.append(f"第 {index} 列（{box_id}）：名稱不可空白。")

        for field, label in [
            ("l", "長"),
            ("w", "寬"),
            ("h", "高"),
            ("max_weight", "最大載重"),
        ]:
            try:
                value = float(box.get(field, 0) or 0)
            except Exception:
                errors.append(f"第 {index} 列（{box_id}）：{label} 必須是數字。")
                continue

            if value <= 0:
                errors.append(f"第 {index} 列（{box_id}）：{label} 必須大於 0。")

        compatible = _aircraft_list(box.get("compatible_aircraft", []))
        unknown = [x for x in compatible if x not in valid_codes]
        if unknown:
            errors.append(
                f"第 {index} 列（{box_id}）：未知機型 {', '.join(unknown)}。"
            )

        zones = _aircraft_list(box.get("compatible_zones", []))
        uid = normalized_uld_id(box_id)

        if requires_upper_deck(uid):
            if "B777" not in compatible:
                errors.append(
                    f"第 {index} 列（{box_id}）：{uid} 只能設定於 B777 上貨艙。"
                )

            if zones != ["B777_UPPER_BM"]:
                errors.append(
                    f"第 {index} 列（{box_id}）：{uid} 只能使用 B777_UPPER_BM。"
                )

        if uid == "PGA":
            try:
                center_positions_value = int(
                    box.get("center_positions", 0) or 0
                )
            except Exception:
                center_positions_value = 0

            if center_positions_value != 4:
                errors.append(
                    f"第 {index} 列（{box_id}）：PGA 中央裝載固定占 4 個 118 盤位，"
                    "中央裝載盤位數請設為 4。"
                )

        if uid == "114":
            if abs(float(box.get("l", 0) or 0) - ULD_114_LENGTH_CM) > 1e-6:
                errors.append(
                    f"第 {index} 列（{box_id}）：114 長度應為 310 cm。"
                )

            if abs(float(box.get("w", 0) or 0) - ULD_114_WIDTH_CM) > 1e-6:
                errors.append(
                    f"第 {index} 列（{box_id}）：114 寬度應為 236 cm。"
                )

            if float(box.get("h", 0) or 0) > ULD_114_MAX_CARGO_HEIGHT_CM:
                errors.append(
                    f"第 {index} 列（{box_id}）：114 目前最高只能設定 140 cm。"
                )

            if bool(box.get("allow_center_load", False)):
                errors.append(
                    f"第 {index} 列（{box_id}）：114 中央裝載盤位規則尚未提供，"
                    "目前請關閉「可中央裝載」。"
                )

        if uid == "96":
            if abs(float(box.get("l", 0) or 0) - ULD_96_LENGTH_CM) > 1e-6:
                errors.append(
                    f"第 {index} 列（{box_id}）：尾端 96 長度應為 317 cm。"
                )

            if abs(float(box.get("w", 0) or 0) - ULD_96_WIDTH_CM) > 1e-6:
                errors.append(
                    f"第 {index} 列（{box_id}）：尾端 96 寬度應為 243 cm。"
                )

            if abs(float(box.get("h", 0) or 0) - ULD_96_MAX_CARGO_HEIGHT_CM) > 1e-6:
                errors.append(
                    f"第 {index} 列（{box_id}）：尾端 96 高度應為 234 cm。"
                )

            if bool(box.get("allow_center_load", False)):
                errors.append(
                    f"第 {index} 列（{box_id}）：96 為機尾唯一中央專用盤位，"
                    "不使用一般『可中央裝載』開關，請保持關閉。"
                )

        if (
            "B777_UPPER_BM" in zones
            and bool(box.get("allow_center_load", False))
        ):
            try:
                center_positions = int(box.get("center_positions", 0) or 0)
            except Exception:
                center_positions = 0

            if center_positions < 2 or center_positions % 2 != 0:
                errors.append(
                    f"第 {index} 列（{box_id}）：B777 中央裝載盤位數必須是 2 以上的偶數。"
                )
            elif center_positions > 24:
                errors.append(
                    f"第 {index} 列（{box_id}）：中央裝載盤位數目前不可超過上艙 22 個 118 等效盤位。"
                )

    return errors
