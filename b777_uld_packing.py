"""
B777 B-M upper-deck contour-aware ULD packing engine.

核心觀念：
- B777 仍然先依不同 ULD / pallet 的「長、寬、最大高度、最大載重」建立裝載表面。
- 貨物不是只有「側邊」或「中央」兩個固定位置。
- 每一件貨物都可以在 ULD 表面內移動 X / Y / Z。
- 每個候選 Y 位置都換算成飛機橫向位置，再依 B-M contour 檢查該處可用高度。
- 單側表面：中心線 -> 機身外側。
- 中央裝載：ULD 本身長、寬維持原尺寸，只把 ULD 橫向中心對準飛機中心線；貨物高度依實際橫向位置套用 contour。

目前仍是 heuristic 3D packing，不是數學上的全域最佳解。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from b777_contours import (
    BM_MAX_HEIGHT_CM,
    BM_MAX_HALF_WIDTH_CM,
    max_height_at_half_width,
)
from b777_uld_rules import (
    center_118_positions_for_uld,
    fixed_height_limit_for_uld,
    position_family_for_uld,
    side_118_positions_for_uld,
)


EPS = 1e-9


@dataclass(frozen=True)
class SurfaceSpec:
    uld_id: str
    uld_name: str
    uld_length: float
    uld_width: float
    uld_height: float
    uld_max_weight: float

    loading_mode: str       # SIDE / CENTER
    position_family: str    # 118_EQUIV / 114_SPECIAL
    span_bays: int          # longitudinal 118-equivalent bay count per side
    positions_used: int     # total aircraft positions
    uld_units_required: int # SIDE=1, CENTER=2 same-size ULDs

    base_length: float
    half_width: float
    surface_width: float
    nominal_height: float
    max_weight: float


@dataclass
class ContourPlacement:
    item_id: str
    name: str

    # Local coordinates within the current loading surface.
    x: float
    y: float
    z: float

    l: float
    w: float
    h: float

    weight: float
    rotation: tuple
    cannot_crush: bool

    # Aircraft contour data at this exact lateral placement.
    outer_half_width: float
    contour_limit_height: float


def build_surface_specs(
    ulds: list[dict],
    allow_center: bool = True,
) -> list[SurfaceSpec]:
    """
    v1.10 使用實際 B777 盤位規則建立 surface：

    - PGA：
        SIDE   = 2 個連續 118 等效盤位
        CENTER = 4 個 118 等效盤位（左右各 2）

    - 118 / PMC 等一般上艙 ULD：
        SIDE   = 依原 ULD 長寬建立 surface
        CENTER = 仍依 center_positions 占用盤位，但 packing surface 的
                 長、寬維持該 ULD 原始尺寸，不再將寬度乘以 2。
                 高度仍依貨物在飛機橫向位置的 contour 計算。

    - 114：
        只建立 114_SPECIAL 單一專用位置 surface
        最大貨物高度固定 140 cm
        中央裝載規則待後續資料，不自行開放

    - 96：
        只建立 96_TAIL 唯一機尾中間專用位置 surface
        尺寸固定 317 x 243 x 243 cm
        不進入一般 118 等效盤位
    """
    specs = []

    for uld in ulds:
        uld_id = str(uld.get("box_id", "") or "").strip()
        length = float(uld.get("l", 0) or 0)
        width = float(uld.get("w", 0) or 0)
        height = float(uld.get("h", 0) or 0)
        max_weight = float(uld.get("max_weight", 0) or 0)

        try:
            configured_center_positions = int(
                uld.get("center_positions", 2) or 2
            )
        except Exception:
            configured_center_positions = 0

        if length <= 0 or width <= 0 or height <= 0 or max_weight <= 0:
            continue

        position_family = position_family_for_uld(uld_id)
        fixed_height = fixed_height_limit_for_uld(uld_id)

        half_width = min(width, BM_MAX_HALF_WIDTH_CM)
        nominal_height = min(
            height,
            fixed_height if fixed_height is not None else BM_MAX_HEIGHT_CM,
        )

        # ----------------------------------------------------
        # 114 special position
        # ----------------------------------------------------
        if position_family == "114_SPECIAL":
            specs.append(
                SurfaceSpec(
                    uld_id=uld_id,
                    uld_name=str(uld["name"]),
                    uld_length=length,
                    uld_width=width,
                    uld_height=height,
                    uld_max_weight=max_weight,
                    loading_mode="SIDE",
                    position_family=position_family,
                    span_bays=0,
                    positions_used=1,
                    uld_units_required=1,
                    base_length=length,
                    half_width=half_width,
                    surface_width=half_width,
                    nominal_height=nominal_height,
                    max_weight=max_weight,
                )
            )
            continue

        # ----------------------------------------------------
        # 96 tail-only dedicated position
        # ----------------------------------------------------
        if position_family == "96_TAIL":
            specs.append(
                SurfaceSpec(
                    uld_id=uld_id,
                    uld_name=str(uld["name"]),
                    uld_length=length,
                    uld_width=width,
                    uld_height=height,
                    uld_max_weight=max_weight,
                    loading_mode="CENTER",
                    position_family=position_family,
                    span_bays=0,
                    positions_used=1,
                    uld_units_required=1,
                    base_length=length,
                    half_width=half_width,
                    surface_width=half_width,
                    nominal_height=nominal_height,
                    max_weight=max_weight,
                )
            )
            continue

        # ----------------------------------------------------
        # 118-equivalent upper positions
        # ----------------------------------------------------
        side_positions = side_118_positions_for_uld(uld_id)

        if side_positions > 0:
            specs.append(
                SurfaceSpec(
                    uld_id=uld_id,
                    uld_name=str(uld["name"]),
                    uld_length=length,
                    uld_width=width,
                    uld_height=height,
                    uld_max_weight=max_weight,
                    loading_mode="SIDE",
                    position_family=position_family,
                    span_bays=side_positions,
                    positions_used=side_positions,
                    uld_units_required=1,
                    base_length=length,
                    half_width=half_width,
                    surface_width=half_width,
                    nominal_height=nominal_height,
                    max_weight=max_weight,
                )
            )

        center_allowed_for_uld = bool(
            uld.get("allow_center_load", False)
        )

        center_positions = center_118_positions_for_uld(
            uld_id,
            configured_center_positions,
        )

        if (
            allow_center
            and center_allowed_for_uld
            and center_positions >= 2
            and center_positions % 2 == 0
        ):
            longitudinal_bays = center_positions // 2

            specs.append(
                SurfaceSpec(
                    uld_id=uld_id,
                    uld_name=str(uld["name"]),
                    uld_length=length,
                    uld_width=width,
                    uld_height=height,
                    uld_max_weight=max_weight,
                    loading_mode="CENTER",
                    position_family=position_family,
                    span_bays=longitudinal_bays,
                    positions_used=center_positions,
                    uld_units_required=2,
                    base_length=length,
                    half_width=half_width,
                    # 中央裝載只改變「放在飛機中央」與盤位占用方式，
                    # 不把兩個盤位合成雙倍寬的 packing surface。
                    surface_width=width,
                    nominal_height=nominal_height,
                    max_weight=max_weight * 2.0,
                )
            )

    return specs


def orientations(item):
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


def _local_to_global_y_edges(spec: SurfaceSpec, local_y: float, item_width: float):
    """
    回傳 cargo 橫向兩側在 aircraft coordinates 的 Y。

    SIDE：
      local y=0 是 aircraft centerline，
      local y 越大越靠機身外側。
      這裡先用右側正值幾何計算；左側最後用鏡射顯示。

    CENTER：
      ULD 寬度維持原始 surface_width。
      local y=0 是 ULD 左緣，
      local y=surface_width/2 是 aircraft centerline，
      local y=surface_width 是 ULD 右緣。
    """
    if spec.loading_mode == "SIDE":
        return local_y, local_y + item_width

    center_offset = spec.surface_width / 2.0
    y0 = local_y - center_offset
    y1 = y0 + item_width
    return y0, y1


def contour_limit_for_placement(
    spec: SurfaceSpec,
    local_y: float,
    item_width: float,
):
    y0, y1 = _local_to_global_y_edges(spec, local_y, item_width)
    outer_half_width = max(abs(y0), abs(y1))

    # 114 前/後專用位置的精細 contour 尚未取得。
    # 目前只套用已確認的固定最高 140 cm。
    if spec.position_family in {"114_SPECIAL", "96_TAIL"}:
        if item_width > spec.surface_width + EPS:
            return None
        return outer_half_width, spec.nominal_height

    if outer_half_width > BM_MAX_HALF_WIDTH_CM + EPS:
        return None

    contour_height = max_height_at_half_width(outer_half_width)
    if contour_height is None:
        return None

    return outer_half_width, min(float(contour_height), spec.nominal_height)


def overlap(a: ContourPlacement, b: ContourPlacement) -> bool:
    return (
        a.x < b.x + b.l - EPS
        and a.x + a.l > b.x + EPS
        and a.y < b.y + b.w - EPS
        and a.y + a.w > b.y + EPS
        and a.z < b.z + b.h - EPS
        and a.z + a.h > b.z + EPS
    )


def xy_overlap(a: ContourPlacement, b: ContourPlacement) -> bool:
    return (
        a.x < b.x + b.l - EPS
        and a.x + a.l > b.x + EPS
        and a.y < b.y + b.w - EPS
        and a.y + a.w > b.y + EPS
    )


def violates_cannot_crush(candidate, placements) -> bool:
    for p in placements:
        if not p.cannot_crush:
            continue
        if xy_overlap(candidate, p) and candidate.z >= p.z + p.h - EPS:
            return True
    return False


def is_supported(candidate, placements) -> bool:
    """
    本版避免浮空：
    - z=0 => 甲板 / pallet base 支撐。
    - z>0 => 必須完整落在某一件下層貨物的頂面。
    """
    if candidate.z <= EPS:
        return True

    for p in placements:
        if abs((p.z + p.h) - candidate.z) > 1e-6:
            continue

        if (
            candidate.x >= p.x - EPS
            and candidate.x + candidate.l <= p.x + p.l + EPS
            and candidate.y >= p.y - EPS
            and candidate.y + candidate.w <= p.y + p.w + EPS
        ):
            return True

    return False


def _candidate_y_positions(space, spec: SurfaceSpec, item_width: float):
    sx, sy, sz, sL, sW, sH = space
    max_y = sy + sW - item_width

    if max_y < sy - EPS:
        return []

    values = [sy, max_y]

    if spec.loading_mode == "SIDE":
        # 單側優先靠中心線，但仍可因其他貨物而往外側移。
        values += [0.0]
    else:
        center = spec.surface_width / 2.0
        values += [
            center - item_width / 2.0,  # 貨物真正置中
            center - item_width,        # 貨物右緣貼飛機中心線
            center,                     # 貨物左緣貼飛機中心線
        ]

    out = []
    for value in values:
        value = max(sy, min(max_y, value))
        if value < sy - EPS or value > max_y + EPS:
            continue
        if not any(abs(value - existing) < 1e-6 for existing in out):
            out.append(value)

    return out


def split_space(space, p: ContourPlacement):
    sx, sy, sz, sL, sW, sH = space
    x2 = sx + sL
    y2 = sy + sW
    z2 = sz + sH

    result = []

    # 前後 / 左右空間。允許重疊，由 placement overlap 再做最後防線。
    if p.x > sx + EPS:
        result.append((sx, sy, sz, p.x - sx, sW, sH))
    if p.x + p.l < x2 - EPS:
        result.append((p.x + p.l, sy, sz, x2 - (p.x + p.l), sW, sH))

    if p.y > sy + EPS:
        result.append((sx, sy, sz, sL, p.y - sy, sH))
    if p.y + p.w < y2 - EPS:
        result.append((sx, p.y + p.w, sz, sL, y2 - (p.y + p.w), sH))

    # 不能疊貨物不建立它上方的 free space。
    if not p.cannot_crush and p.z + p.h < z2 - EPS:
        result.append((sx, sy, p.z + p.h, sL, sW, z2 - (p.z + p.h)))

    return [s for s in result if min(s[3:]) > EPS]


def prune_spaces(spaces):
    unique = []
    seen = set()

    for s in spaces:
        key = tuple(round(v, 6) for v in s)
        if key not in seen:
            seen.add(key)
            unique.append(s)

    filtered = []

    for i, s in enumerate(unique):
        sx, sy, sz, sL, sW, sH = s
        contained = False

        for j, t in enumerate(unique):
            if i == j:
                continue

            tx, ty, tz, tL, tW, tH = t

            if (
                sx >= tx - EPS
                and sy >= ty - EPS
                and sz >= tz - EPS
                and sx + sL <= tx + tL + EPS
                and sy + sW <= ty + tW + EPS
                and sz + sH <= tz + tH + EPS
            ):
                contained = True
                break

        if not contained:
            filtered.append(s)

    return filtered


def _sort_units(units, order):
    if order == "height":
        secondary = lambda a: float(a.h)
    elif order == "maxside":
        secondary = lambda a: max(float(a.l), float(a.w), float(a.h))
    elif order == "weight":
        secondary = lambda a: float(a.weight)
    else:
        secondary = lambda a: float(a.l) * float(a.w) * float(a.h)

    return sorted(
        units,
        key=lambda a: (
            bool(a.cannot_crush),  # 一般貨物先、不能疊最後
            -secondary(a),
        ),
    )


def pack_surface(spec: SurfaceSpec, units, order="volume"):
    ordered = _sort_units(units, order)

    spaces = [
        (
            0.0,
            0.0,
            0.0,
            spec.base_length,
            spec.surface_width,
            spec.nominal_height,
        )
    ]

    placements = []
    current_weight = 0.0

    for index, item in enumerate(ordered):
        if current_weight + float(item.weight) > spec.max_weight + EPS:
            continue

        best = None
        best_score = None

        for si, space in enumerate(spaces):
            sx, sy, sz, sL, sW, sH = space

            for dims, rotation in orientations(item):
                l, w, h = dims

                if l > sL + EPS or w > sW + EPS or h > sH + EPS:
                    continue

                for py in _candidate_y_positions(space, spec, w):
                    px = sx
                    pz = sz

                    contour_info = contour_limit_for_placement(spec, py, w)
                    if contour_info is None:
                        continue

                    outer_half_width, contour_limit = contour_info

                    if pz + h > contour_limit + EPS:
                        continue

                    p = ContourPlacement(
                        item_id=item.item_id,
                        name=item.name,
                        x=px,
                        y=py,
                        z=pz,
                        l=l,
                        w=w,
                        h=h,
                        weight=float(item.weight),
                        rotation=rotation,
                        cannot_crush=bool(item.cannot_crush),
                        outer_half_width=outer_half_width,
                        contour_limit_height=contour_limit,
                    )

                    if any(overlap(p, q) for q in placements):
                        continue

                    if violates_cannot_crush(p, placements):
                        continue

                    if not is_supported(p, placements):
                        continue

                    nx = int((sL + EPS) // l)
                    ny = int((sW + EPS) // w)
                    nz = int((sH + EPS) // h)

                    if p.cannot_crush:
                        nz = min(nz, 1)

                    same_left = sum(
                        1
                        for u in ordered[index:]
                        if (
                            float(u.l), float(u.w), float(u.h),
                            bool(u.horizontal_rotate),
                            bool(u.vertical_rotate),
                            bool(u.cannot_crush),
                        )
                        == (
                            float(item.l), float(item.w), float(item.h),
                            bool(item.horizontal_rotate),
                            bool(item.vertical_rotate),
                            bool(item.cannot_crush),
                        )
                    )

                    orientation_capacity = min(nx * ny * nz, same_left)
                    residual = sL * sW * sH - l * w * h

                    # 同樣能裝時：
                    # 1. 低 Z
                    # 2. 優先較靠中心 / 較高 contour 的位置
                    # 3. 減少殘餘空間
                    score = (
                        -orientation_capacity,
                        pz,
                        outer_half_width,
                        residual,
                        px,
                        py,
                    )

                    if best_score is None or score < best_score:
                        best_score = score
                        best = (si, p)

        if best is None:
            continue

        si, p = best
        old_space = spaces.pop(si)

        placements.append(p)
        current_weight += p.weight

        spaces.extend(split_space(old_space, p))
        spaces = prune_spaces(spaces)

    return placements


def best_pack_surface(spec: SurfaceSpec, units):
    candidates = []

    for order in ("volume", "height", "maxside", "weight"):
        placements = pack_surface(spec, units, order=order)
        packed_volume = sum(p.l * p.w * p.h for p in placements)
        packed_weight = sum(p.weight for p in placements)

        candidates.append(
            (
                len(placements),
                packed_volume,
                packed_weight,
                placements,
            )
        )

    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return candidates[0][3]


def local_to_aircraft_y(spec: SurfaceSpec, placement: ContourPlacement, side=None):
    """
    回傳實際 aircraft Y 範圍。

    SIDE 的 packing geometry 永遠使用正側。
    若最後分配到 L，才鏡射。
    """
    if spec.position_family in {"114_SPECIAL", "96_TAIL"}:
        y0 = placement.y - spec.surface_width / 2.0
        return y0, y0 + placement.w

    if spec.loading_mode == "CENTER":
        y0 = placement.y - spec.surface_width / 2.0
        return y0, y0 + placement.w

    if side == "L":
        return -(placement.y + placement.w), -placement.y

    return placement.y, placement.y + placement.w


def placement_extents(placements):
    if not placements:
        return 0.0, 0.0, 0.0

    return (
        max(p.x + p.l for p in placements),
        max(p.y + p.w for p in placements),
        max(p.z + p.h for p in placements),
    )
