"""
快速尺寸文字轉換器。

支援：
121*102*147*1
121x102x147x1
121X102X147X1
121×102×147×1
121 * 102 * 147 * 1
121 102 147 1

固定解讀：
長 × 寬 × 高 × 數量
"""

from __future__ import annotations

import re


SEPARATOR_RE = re.compile(r"[\*xX×]")


def _clean_number(value: float):
    """整數維持整數顯示，否則保留小數。"""
    if float(value).is_integer():
        return int(value)
    return float(value)


def parse_dimension_text(
    text: str,
    id_prefix: str = "CARGO",
    name_prefix: str = "貨物",
    agt: str = "",
):
    """
    回傳：
      rows: 可直接轉成目前程式 ITEM_COLUMNS 的 dict list
      errors: [{line, input, reason}, ...]

    空白行自動略過。
    """
    rows = []
    errors = []

    prefix = str(id_prefix or "CARGO").strip() or "CARGO"
    name_prefix = str(name_prefix or "貨物").strip() or "貨物"
    agt = str(agt or "").strip()

    source_lines = str(text or "").splitlines()
    valid_index = 0

    for line_no, raw_line in enumerate(source_lines, start=1):
        original = raw_line.strip()

        if not original:
            continue

        # *, x, X, × 全部先轉成空白。
        # 因此「121 * 102 * 147 * 1」與單純空白分隔皆可處理。
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
        cargo_id = f"{prefix}{valid_index:03d}"

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
