"""
B777 upper-deck ULD planner — v1.10.

盤位層：
A) 118 等效盤位：左右各 11，共 22。
   - 一般 ULD 單側通常占 1 個。
   - PGA 單側占 2 個連續位置。
   - PGA 中央裝載占左右各 2，共 4 個。

B) 114 專用位置：前後共 4 個。
   - 只能放 114。
   - 其他 ULD 不會使用這 4 個位置。
   - 114 最大高度目前固定 140 cm。
   - 頭尾精細 contour 待後續資料。

BUP：
- 同 ID BUP 批次獨立規劃。
"""

from __future__ import annotations

from dataclasses import dataclass

from b777_positions import (
    UPPER_118_BAYS,
    UPPER_114_SPECIAL_POSITIONS,
    UPPER_96_TAIL_POSITION,
)
from b777_uld_packing import (
    SurfaceSpec,
    ContourPlacement,
    build_surface_specs,
    best_pack_surface,
)
from bup_rules import partition_bup_units


@dataclass
class B777ULDLoad:
    load_id: str

    spec: SurfaceSpec
    side: str | None

    start_bay: str
    bays: tuple[str, ...]
    occupied_positions: tuple[str, ...]

    placements: list[ContourPlacement]
    bup_group: str | None = None


def _118_slot_positions(
    spec: SurfaceSpec,
    start_index: int,
    side: str | None,
):
    bays = UPPER_118_BAYS[
        start_index:start_index + spec.span_bays
    ]

    if len(bays) != spec.span_bays:
        return None

    if spec.loading_mode == "CENTER":
        positions = tuple(
            f"{bay}{s}"
            for bay in bays
            for s in ("L", "R")
        )
    else:
        if side not in ("L", "R"):
            return None

        positions = tuple(
            f"{bay}{side}"
            for bay in bays
        )

    return tuple(bays), positions


def find_available_slot(
    spec: SurfaceSpec,
    occupied_118: set[str],
    occupied_114: set[str],
    occupied_96: set[str],
):
    # -------------------------------------------------------
    # 114 dedicated positions
    # -------------------------------------------------------
    if spec.position_family == "114_SPECIAL":
        for position in UPPER_114_SPECIAL_POSITIONS:
            if position not in occupied_114:
                return None, (position,), (position,)

        return None

    # -------------------------------------------------------
    # 96 unique tail-center position
    # -------------------------------------------------------
    if spec.position_family == "96_TAIL":
        if UPPER_96_TAIL_POSITION not in occupied_96:
            return (
                None,
                (UPPER_96_TAIL_POSITION,),
                (UPPER_96_TAIL_POSITION,),
            )
        return None

    # -------------------------------------------------------
    # 118-equivalent positions
    # -------------------------------------------------------
    if spec.loading_mode == "CENTER":
        for start_index in range(len(UPPER_118_BAYS)):
            result = _118_slot_positions(
                spec,
                start_index,
                None,
            )
            if result is None:
                continue

            bays, positions = result

            if all(
                p not in occupied_118
                for p in positions
            ):
                return None, bays, positions

        return None

    # SIDE:
    # PGA 會因 span_bays=2 自動要求同側 2 個連續位置。
    for start_index in range(len(UPPER_118_BAYS)):
        for side in ("L", "R"):
            result = _118_slot_positions(
                spec,
                start_index,
                side,
            )
            if result is None:
                continue

            bays, positions = result

            if all(
                p not in occupied_118
                for p in positions
            ):
                return side, bays, positions

    return None


def _candidate_score(
    spec: SurfaceSpec,
    placements,
):
    if not placements:
        return None

    packed_volume = sum(
        p.l * p.w * p.h
        for p in placements
    )
    packed_count = len(placements)

    return (
        packed_volume / spec.positions_used,
        packed_count / spec.positions_used,
        packed_count,
        packed_volume,
        -spec.positions_used,
    )


def _plan_segment(
    segment_units,
    specs,
    occupied_118,
    occupied_114,
    occupied_96,
    loads,
    bup_group=None,
):
    remaining = list(segment_units)
    safety_limit = (
        len(remaining)
        + len(UPPER_118_BAYS) * 2
        + len(UPPER_114_SPECIAL_POSITIONS)
    )

    while remaining and len(loads) < safety_limit * 2:
        candidates = []

        for spec in specs:
            slot = find_available_slot(
                spec,
                occupied_118,
                occupied_114,
                occupied_96,
            )
            if slot is None:
                continue

            placements = best_pack_surface(
                spec,
                remaining,
            )
            if not placements:
                continue

            score = _candidate_score(
                spec,
                placements,
            )
            if score is None:
                continue

            candidates.append(
                (score, spec, slot, placements)
            )

        if not candidates:
            break

        candidates.sort(
            key=lambda x: x[0],
            reverse=True,
        )
        _, spec, slot, placements = candidates[0]

        side, bays, positions = slot

        load = B777ULDLoad(
            load_id=f"LOAD-{len(loads)+1:02d}",
            spec=spec,
            side=side,
            start_bay=bays[0],
            bays=bays,
            occupied_positions=positions,
            placements=placements,
            bup_group=bup_group,
        )
        loads.append(load)

        if spec.position_family == "114_SPECIAL":
            target_occupied = occupied_114
        elif spec.position_family == "96_TAIL":
            target_occupied = occupied_96
        else:
            target_occupied = occupied_118

        for position in positions:
            target_occupied.add(position)

        used_ids = {
            p.item_id
            for p in placements
        }

        new_remaining = [
            u for u in remaining
            if u.item_id not in used_ids
        ]

        if len(new_remaining) >= len(remaining):
            break

        remaining = new_remaining

    return remaining


def plan_upper_deck_uld(
    units,
    ulds,
    allow_center=True,
):
    occupied_118 = set()
    occupied_114 = set()
    occupied_96 = set()

    loads = []
    all_remaining = []

    specs = build_surface_specs(
        ulds,
        allow_center=allow_center,
    )

    for batch_id_value, segment_units, is_bup in partition_bup_units(units):
        segment_remaining = _plan_segment(
            segment_units,
            specs,
            occupied_118,
            occupied_114,
            occupied_96,
            loads,
            bup_group=(
                batch_id_value
                if is_bup
                else None
            ),
        )
        all_remaining.extend(segment_remaining)

    return loads, all_remaining


def total_positions_used(loads) -> int:
    return sum(
        len(load.occupied_positions)
        for load in loads
    )


def total_118_positions_used(loads) -> int:
    return sum(
        len(load.occupied_positions)
        for load in loads
        if load.spec.position_family == "118_EQUIV"
    )


def total_114_positions_used(loads) -> int:
    return sum(
        len(load.occupied_positions)
        for load in loads
        if load.spec.position_family == "114_SPECIAL"
    )


def total_96_tail_positions_used(loads) -> int:
    return sum(
        len(load.occupied_positions)
        for load in loads
        if load.spec.position_family == "96_TAIL"
    )


def total_uld_units_used(loads) -> int:
    return sum(
        int(load.spec.uld_units_required)
        for load in loads
    )


def total_pieces_loaded(loads) -> int:
    return sum(
        len(load.placements)
        for load in loads
    )


def position_map(loads):
    result = {
        f"{bay}{side}": None
        for bay in UPPER_118_BAYS
        for side in ("L", "R")
    }

    result.update({
        position: None
        for position in UPPER_114_SPECIAL_POSITIONS
    })
    result[UPPER_96_TAIL_POSITION] = None

    for load in loads:
        for position in load.occupied_positions:
            result[position] = load.load_id

    return result
