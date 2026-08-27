"""
B777 upper-deck position model — v1.11.

118 等效盤位：
- 左側 11
- 右側 11
- 共 22

114 專用位置：
- 最前方 2 個
- 最後方 2 個
- 皆位於中間專用位置列，不畫在左/右側盤位列
- 不可放其他 ULD
- 頭尾精細 contour 待使用者後續提供

96 尾端專用位置：
- 每架 B777 僅 1 個
- 位於後方 114 位置之後
- 位於機尾中央
- 只能放 96
"""

from __future__ import annotations

from b777_uld_rules import (
    UPPER_118_MAX_POSITIONS,
    UPPER_118_POSITIONS_PER_SIDE,
)

UPPER_118_BAYS = tuple(
    f"{i:02d}"
    for i in range(1, UPPER_118_POSITIONS_PER_SIDE + 1)
)
SIDES = ("L", "R")

UPPER_114_FRONT_POSITIONS = (
    "114-F1",
    "114-F2",
)

UPPER_114_REAR_POSITIONS = (
    "114-R1",
    "114-R2",
)

UPPER_114_SPECIAL_POSITIONS = (
    *UPPER_114_FRONT_POSITIONS,
    *UPPER_114_REAR_POSITIONS,
)

UPPER_96_TAIL_POSITION = "96-T"

POSITION_RULE_NOTE = (
    "B777 上艙 118 等效盤位上限為 22：左右各 11。"
    "PGA 單側占 2 個連續 118 盤位，中央裝載占 4 個 118 盤位。"
    "114 位於最前方與最後方各 2 個中央專用位置；"
    "機尾最後另有唯一 1 個 96 專用盤位，位置在機尾中間。"
)


def upper_118_position_id(bay: str, side: str) -> str:
    return f"{bay}{side}"


def all_118_position_ids() -> list[str]:
    return [
        upper_118_position_id(bay, side)
        for bay in UPPER_118_BAYS
        for side in SIDES
    ]


def all_position_ids() -> list[str]:
    return (
        list(UPPER_114_FRONT_POSITIONS)
        + all_118_position_ids()
        + list(UPPER_114_REAR_POSITIONS)
        + [UPPER_96_TAIL_POSITION]
    )


assert len(all_118_position_ids()) == UPPER_118_MAX_POSITIONS
