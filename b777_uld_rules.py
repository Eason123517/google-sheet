"""
B777 upper-deck ULD operational rules — v1.10.

已確認規則：
1. B777 上艙 118 等效盤位最多 22 個：左右各 11 個。
2. PGA 單側占 2 個連續 118 盤位；中央裝載占 4 個 118 盤位。
3. 114：
   - 長、寬同 118：310 x 236 cm。
   - 貨物最高 140 cm。
   - 只能使用上艙前後共 4 個 114 專用位置。
   - 這 4 個位置不能放其他盤。
   - 前/後位置更精細的 contour 高度資料待補圖後加入。
4. 118 / PGA / 114 / 96 只允許上貨艙。
5. 96 為機尾中間唯一專用盤位：
   - 317 x 243 x 243 cm。
   - 每架 B777 僅 1 個此位置。
   - 位於後方 114 專用位置之後。
   - 不能放在一般 118 等效盤位。

114 最大載重尚未提供，因此不自行加入 boxes.json。
若之後使用者新增 box_id=114，本模組會自動套用 114 專用規則。
"""

from __future__ import annotations


UPPER_118_MAX_POSITIONS = 22
UPPER_118_POSITIONS_PER_SIDE = 11

ULD_118_IDS = {"118"}
ULD_PGA_IDS = {"PGA"}
ULD_114_IDS = {"114"}
ULD_96_IDS = {"96"}

UPPER_ONLY_IDS = ULD_118_IDS | ULD_PGA_IDS | ULD_114_IDS | ULD_96_IDS

ULD_114_LENGTH_CM = 310.0
ULD_114_WIDTH_CM = 236.0
ULD_114_MAX_CARGO_HEIGHT_CM = 140.0

ULD_96_LENGTH_CM = 317.0
ULD_96_WIDTH_CM = 243.0
ULD_96_MAX_CARGO_HEIGHT_CM = 243.0


def normalized_uld_id(value) -> str:
    return str(value or "").strip().upper()


def position_family_for_uld(uld_id: str) -> str:
    """
    118_EQUIV:
        一般 B777 上艙位置家族，最多 22 個（左右各 11）。

    114_SPECIAL:
        114 專用前/後 4 位置，不與其他盤共用。
    """
    uid = normalized_uld_id(uld_id)

    if uid in ULD_114_IDS:
        return "114_SPECIAL"

    if uid in ULD_96_IDS:
        return "96_TAIL"

    return "118_EQUIV"


def side_118_positions_for_uld(uld_id: str) -> int:
    uid = normalized_uld_id(uld_id)

    if uid in ULD_PGA_IDS:
        return 2

    if uid in ULD_114_IDS or uid in ULD_96_IDS:
        return 0

    return 1


def center_118_positions_for_uld(
    uld_id: str,
    configured_center_positions: int,
) -> int:
    uid = normalized_uld_id(uld_id)

    if uid in ULD_PGA_IDS:
        return 4

    if uid in ULD_114_IDS:
        # 114 中央裝載位置規則尚未提供，不自行開放。
        return 0

    if uid in ULD_96_IDS:
        # 96 為機尾中間唯一專用盤位，不提供一般中央裝載候選。
        return 0

    return int(configured_center_positions)


def fixed_height_limit_for_uld(uld_id: str) -> float | None:
    uid = normalized_uld_id(uld_id)

    if uid in ULD_114_IDS:
        return ULD_114_MAX_CARGO_HEIGHT_CM

    if uid in ULD_96_IDS:
        return ULD_96_MAX_CARGO_HEIGHT_CM

    return None


def requires_upper_deck(uld_id: str) -> bool:
    return normalized_uld_id(uld_id) in UPPER_ONLY_IDS


def config_warnings(uld: dict) -> list[str]:
    """
    非致命提示。
    """
    warnings = []
    uid = normalized_uld_id(uld.get("box_id"))

    if uid == "PGA":
        if bool(uld.get("allow_center_load", False)):
            try:
                configured = int(uld.get("center_positions", 0) or 0)
            except Exception:
                configured = 0

            if configured != 4:
                warnings.append(
                    "PGA 中央裝載固定占 4 個 118 盤位；"
                    "程式將以 4 個盤位計算，不使用目前填寫值。"
                )

    if uid == "114":
        warnings.append(
            "114 前/後 4 個專用位置的精細頭尾 contour 尚未提供；"
            "目前只套用 140 cm 固定高度上限。"
        )

    return warnings
