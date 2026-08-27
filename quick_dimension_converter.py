"""
快速尺寸文字轉換器 — v1.13.9.1

支援：
121*102*147*1
121x102x147x1
121X102X147X1
121×102×147×1
121 * 102 * 147 * 1
121 102 147 1

固定解讀：
長 × 寬 × 高 × 數量

相容性：
- v1.13.9 新版呼叫：cargo_id="09673823"
- v1.13.8 舊版呼叫：id_prefix="09673823"

不論使用哪個參數名稱，都會視為「固定 ID」，
不再自動附加 001、002 流水號。
"""

from __future__ import annotations

import re


SEPARATOR_RE = re.compile(r"[\*xX×]")


def _clean_number(value: float):
    if float(value).is_integer():
        return int(value)
    return float(value)


def parse_dimension_text(
    text: str,
    cargo_id: str = "A",
    name_prefix: str = "貨物",
    agt: str = "",
    id_prefix: str | None = None,
    **_ignored,
):
    """
    將尺寸文字轉為目前程式可讀的貨物列。

    cargo_id:
        v1.13.9 起正式參數名稱，該次所有尺寸列使用同一 ID。

    id_prefix:
        僅為向下相容舊版 app.py；若有傳入，會直接當固定 ID 使用，
        不會再自行產生流水號。
    """
    rows = []
    errors = []

    # 若舊版 app 還傳 id_prefix，優先採用它。
    if id_prefix is not None and str(id_prefix).strip():
        cargo_id = id_prefix

    cargo_id = str(cargo_id or "A").strip() or "A"
    name_prefix = str(name_prefix or "貨物").strip() or "貨物"
    agt = str(agt or "").strip()

    source_lines = str(text or "").splitlines()
    valid_index = 0

    for line_no, raw_line in enumerate(source_lines, start=1):
        original = raw_line.strip()

        if not original:
            continue

        normalized = SEPARATOR_RE.sub(" ", original)
        parts = normalized.split()

        if len(parts) != 4:
            errors.append(
                {
                    "行號": line_no,
                    "原始內容": original,
                    "錯誤": (
                        "必須剛好有 4 個數值：長、寬、高、數量。"
                        f"目前辨識到 {len(parts)} 個欄位。"
                    ),
                }
            )
            continue

        try:
            l, w, h = [float(x) for x in parts[:3]]
        except ValueError:
            errors.append(
                {
                    "行號": line_no,
                    "原始內容": original,
                    "錯誤": "長、寬、高必須是數字。",
                }
            )
            continue

        try:
            qty_value = float(parts[3])
        except ValueError:
            errors.append(
                {
                    "行號": line_no,
                    "原始內容": original,
                    "錯誤": "數量必須是整數。",
                }
            )
            continue

        if l <= 0 or w <= 0 or h <= 0:
            errors.append(
                {
                    "行號": line_no,
                    "原始內容": original,
                    "錯誤": "長、寬、高必須大於 0。",
                }
            )
            continue

        if qty_value <= 0 or not qty_value.is_integer():
            errors.append(
                {
                    "行號": line_no,
                    "原始內容": original,
                    "錯誤": "數量必須是大於 0 的整數。",
                }
            )
            continue

        valid_index += 1

        rows.append(
            {
                "ID": cargo_id,
                "名稱": f"{name_prefix}{valid_index:03d}",
                "AGT": agt,
                "BUP": False,
                "長(cm)": _clean_number(l),
                "寬(cm)": _clean_number(w),
                "高(cm)": _clean_number(h),
                "數量": int(qty_value),
                "總重量(kg)": 0.0,
                "水平旋轉": True,
                "垂直旋轉": False,
                "不能疊": False,
            }
        )

    return rows, errors
