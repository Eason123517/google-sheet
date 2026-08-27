"""
B777 B-M upper-deck contour rules.

目前支援：
1. 單側裝載（LEFT / RIGHT）：
   貨物橫向從中心線往外側延伸 width，
   以最外緣 width 查 contour 最大高度。

2. 中央裝載（CENTER）：
   貨物置中於機身中心線，
   左右各延伸 width/2，
   以 width/2 查 contour 最大高度。

3. 若單側可行，優先單側。
   單側不可行才考慮中央。

4. 縱向占位：
   暫以 96 inch = 243.84 cm 為測試節距。
   CENTER：
       1 longitudinal bay => 2 盤位（左右各 1）
       2 longitudinal bays => 4 盤位（左右各 2）
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from b777_contours import (
    BM_MAX_HEIGHT_CM,
    BM_MAX_HALF_WIDTH_CM,
    max_height_at_half_width,
)
from b777_positions import (
    TEST_POSITION_PITCH_CM,
    MAX_TEST_LONGITUDINAL_BAYS,
)


@dataclass(frozen=True)
class B777LoadOption:
    loading_mode: str       # SIDE / CENTER
    side: str | None        # L / R / None
    length: float           # longitudinal dimension
    width: float            # transverse dimension
    height: float
    rotation: tuple
    longitudinal_bays: int
    positions_used: int
    contour_limit_height: float
    height_clearance: float


def orientation_candidates(item):
    """
    與通用 engine 相同概念，但此模組獨立，不依賴 app.py。
    尺寸回傳順序：length, width, height。
    """
    L, W, H = float(item.l), float(item.w), float(item.h)
    out = []

    def add(dims, rot):
        if dims not in [d for d, _ in out]:
            out.append((dims, rot))

    add((L, W, H), (0, 0, 0))

    if bool(item.horizontal_rotate):
        add((W, L, H), (0, 0, 90))

    if bool(item.vertical_rotate):
        add((H, W, L), (0, 90, 0))
        add((L, H, W), (90, 0, 0))

        if bool(item.horizontal_rotate):
            add((H, L, W), (0, 90, 90))
            add((W, H, L), (90, 0, 90))

    return out


def longitudinal_bay_count(length_cm: float) -> int:
    if length_cm <= 0:
        return 0
    return int(math.ceil(length_cm / TEST_POSITION_PITCH_CM - 1e-12))


def evaluate_side_option(item, dims, rotation, side: str):
    length, width, height = dims

    if height > BM_MAX_HEIGHT_CM + 1e-9:
        return None

    if width > BM_MAX_HALF_WIDTH_CM + 1e-9:
        return None

    limit_height = max_height_at_half_width(width)
    if limit_height is None or height > limit_height + 1e-9:
        return None

    bays = longitudinal_bay_count(length)
    if bays <= 0 or bays > MAX_TEST_LONGITUDINAL_BAYS:
        return None

    return B777LoadOption(
        loading_mode="SIDE",
        side=side,
        length=length,
        width=width,
        height=height,
        rotation=rotation,
        longitudinal_bays=bays,
        positions_used=bays,
        contour_limit_height=limit_height,
        height_clearance=limit_height - height,
    )


def evaluate_center_option(item, dims, rotation):
    length, width, height = dims

    if height > BM_MAX_HEIGHT_CM + 1e-9:
        return None

    half_width = width / 2.0

    if half_width > BM_MAX_HALF_WIDTH_CM + 1e-9:
        return None

    limit_height = max_height_at_half_width(half_width)
    if limit_height is None or height > limit_height + 1e-9:
        return None

    bays = longitudinal_bay_count(length)
    if bays <= 0 or bays > MAX_TEST_LONGITUDINAL_BAYS:
        return None

    return B777LoadOption(
        loading_mode="CENTER",
        side=None,
        length=length,
        width=width,
        height=height,
        rotation=rotation,
        longitudinal_bays=bays,
        positions_used=bays * 2,
        contour_limit_height=limit_height,
        height_clearance=limit_height - height,
    )


def feasible_options(item):
    side_options = []
    center_options = []

    for dims, rotation in orientation_candidates(item):
        for side in ("L", "R"):
            option = evaluate_side_option(item, dims, rotation, side)
            if option is not None:
                side_options.append(option)

        center = evaluate_center_option(item, dims, rotation)
        if center is not None:
            center_options.append(center)

    # 使用者規則：單側能放先採單側；單側無法才考慮中央。
    if side_options:
        side_options.sort(
            key=lambda x: (
                x.longitudinal_bays,
                -x.height_clearance,
                x.width,
                x.height,
            )
        )
        return side_options

    center_options.sort(
        key=lambda x: (
            x.longitudinal_bays,
            x.positions_used,
            -x.height_clearance,
            x.width,
            x.height,
        )
    )
    return center_options


def best_option(item):
    options = feasible_options(item)
    return options[0] if options else None


def explain_piece(item):
    option = best_option(item)

    if option is not None:
        return {
            "貨物ID": item.item_id,
            "可裝載": True,
            "模式": "單側" if option.loading_mode == "SIDE" else "中央",
            "側別": option.side or "-",
            "長(cm)": option.length,
            "寬(cm)": option.width,
            "高(cm)": option.height,
            "輪廓允許高(cm)": round(option.contour_limit_height, 2),
            "高度餘裕(cm)": round(option.height_clearance, 2),
            "縱向bay數": option.longitudinal_bays,
            "占用盤位": option.positions_used,
            "RX": option.rotation[0],
            "RY": option.rotation[1],
            "RZ": option.rotation[2],
            "原因": "",
        }

    # 提供簡單失敗原因。
    min_height = min(
        float(item.h),
        float(item.l) if bool(item.vertical_rotate) else float(item.h),
        float(item.w) if bool(item.vertical_rotate) else float(item.h),
    )
    max_dim = max(float(item.l), float(item.w), float(item.h))

    if min_height > BM_MAX_HEIGHT_CM:
        reason = "所有允許方向的高度皆超過 300 cm。"
    elif max_dim > BM_MAX_HALF_WIDTH_CM * 2 and not bool(item.vertical_rotate):
        reason = "貨物橫向寬度超過中央裝載可用總寬。"
    else:
        reason = (
            "所有允許旋轉方向皆無法同時符合 B-M contour 與目前測試盤位長度。"
        )

    return {
        "貨物ID": item.item_id,
        "可裝載": False,
        "模式": "-",
        "側別": "-",
        "長(cm)": float(item.l),
        "寬(cm)": float(item.w),
        "高(cm)": float(item.h),
        "輪廓允許高(cm)": None,
        "高度餘裕(cm)": None,
        "縱向bay數": None,
        "占用盤位": None,
        "RX": None,
        "RY": None,
        "RZ": None,
        "原因": reason,
    }
