import json
import sys
import io
import hashlib
from dataclasses import dataclass
from pathlib import Path

# 確保不論從本地、VS Code、Codespaces 或其他工作目錄啟動，
# 都能找到與 app.py 放在同一資料夾的機型模組。
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
from collections import Counter, defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from box_store import (
    load_boxes,
    save_boxes,
    storage_backend_name,
    storage_connection_info,
    storage_healthcheck,
    seed_missing_default_boxes,
)
from aircraft_registry import (
    aircraft_codes,
    aircraft_label,
    get_aircraft_module,
    get_aircraft_profile,
)
from uld_service import (
    get_compatible_ulds,
    boxes_to_editor_dataframe,
    editor_dataframe_to_boxes,
    validate_uld_records,
)
from b777_contours import BM_HALF_CONTOUR, REAR_UPPER_HALF_CONTOUR
from b777_positions import POSITION_RULE_NOTE
from b777_planner import (
    plan_upper_deck_uld,
    total_positions_used,
    total_118_positions_used,
    total_114_positions_used,
    total_96_tail_positions_used,
    total_uld_units_used,
    total_pieces_loaded,
)
from b777_visualization import (
    make_contour_figure,
    make_position_plan_figure,
    make_load_3d_figure,
    make_load_cross_section_figure,
    load_extents,
)
from b777_uld_packing import local_to_aircraft_y
from bup_rules import partition_bup_units
from b777_uld_rules import (
    config_warnings as b777_uld_config_warnings,
)

APP_DIR = Path(__file__).resolve().parent

st.set_page_config(page_title="3D貨物排列系統v1.13.2", layout="wide", initial_sidebar_state="expanded")

# =========================================================
# Data models
# =========================================================
@dataclass(frozen=True)
class BoxType:
    box_id: str
    name: str
    l: float
    w: float
    h: float
    max_weight: float


@dataclass
class Item:
    item_id: str
    name: str
    l: float
    w: float
    h: float
    qty: int
    weight: float
    horizontal_rotate: bool
    vertical_rotate: bool
    cannot_crush: bool
    agt: str = ""
    bup: bool = False
    batch_id: str = ""


@dataclass
class Placement:
    item_id: str
    name: str
    x: float
    y: float
    z: float
    l: float
    w: float
    h: float
    weight: float
    rotation: tuple
    cannot_crush: bool


@dataclass
class PackedBox:
    box_type: BoxType
    placements: list
    bup_group: str | None = None


# =========================================================
# Box library
# =========================================================
# 箱型資料存取已抽離至 box_store.py。
# app.py 只呼叫 load_boxes() / save_boxes()，
# 本地 JSON 與未來 Google Sheets 可在不修改演算法/UI 的情況下切換。


# =========================================================
# Rotation
# =========================================================
def orientations(item):
    """
    水平旋轉：
      只在 XY 平面旋轉，L/W 互換，H 不變。
    垂直旋轉：
      允許改變哪一個尺寸作為高度。
    兩者皆開：
      最多 6 種軸向。
    """
    L, W, H = item.l, item.w, item.h
    out = []

    def add(dims, rot):
        if dims not in [d for d, _ in out]:
            out.append((dims, rot))

    add((L, W, H), (0, 0, 0))

    if item.horizontal_rotate:
        add((W, L, H), (0, 0, 90))

    if item.vertical_rotate:
        add((H, W, L), (0, 90, 0))
        add((L, H, W), (90, 0, 0))

        if item.horizontal_rotate:
            add((H, L, W), (0, 90, 90))
            add((W, H, L), (90, 0, 90))

    return out


# =========================================================
# Item helpers
# =========================================================
def expand_items(items):
    """
    展開數量為單件 unit。

    v1.9：
    - item.item_id 是原始「批次 ID」。
    - 相同 ID 可能出現在多列、尺寸也可能不同。
    - unit item_id 必須保持唯一，因此同一批 ID 的流水號會跨列延續。
    - batch_id 永遠保留原始 ID，供 BUP 判斷。
    """
    units = []
    batch_counters = {}

    for item in items:
        batch = str(item.item_id or "").strip()
        batch_counters.setdefault(batch, 0)

        for _ in range(item.qty):
            batch_counters[batch] += 1
            unit_seq = batch_counters[batch]

            units.append(
                Item(
                    item_id=f"{batch}-{unit_seq:03d}",
                    name=item.name,
                    l=item.l,
                    w=item.w,
                    h=item.h,
                    qty=1,
                    weight=item.weight,
                    horizontal_rotate=item.horizontal_rotate,
                    vertical_rotate=item.vertical_rotate,
                    cannot_crush=item.cannot_crush,
                    agt=item.agt,
                    bup=item.bup,
                    batch_id=batch,
                )
            )

    return units


def item_signature(item):
    base_id = str(getattr(item, "batch_id", "") or "").strip()
    if not base_id:
        base_id = item.item_id.rsplit("-", 1)[0]

    return (
        base_id,
        item.name,
        round(item.l, 8),
        round(item.w, 8),
        round(item.h, 8),
        round(item.weight, 8),
        item.horizontal_rotate,
        item.vertical_rotate,
        item.cannot_crush,
    )


# =========================================================
# "Cannot crush" rules
# =========================================================
def xy_overlap(a, b):
    return (
        a.x < b.x + b.l and a.x + a.l > b.x
        and a.y < b.y + b.w and a.y + a.w > b.y
    )


def violates_cannot_crush(candidate, placements):
    """
    已經放入「不能疊」貨物後，只要候選貨物的 XY footprint 與它重疊，
    且候選貨物位於其上方，就拒絕。
    """
    for p in placements:
        if not p.cannot_crush:
            continue

        if xy_overlap(candidate, p) and candidate.z >= p.z + p.h - 1e-9:
            return True

    return False


def validate_cannot_crush(placements):
    """
    最後再驗證一次：每個不能疊貨物的上方，不得有其他貨物。
    """
    for protected in placements:
        if not protected.cannot_crush:
            continue

        protected_top = protected.z + protected.h

        for other in placements:
            if other.item_id == protected.item_id:
                continue

            if xy_overlap(protected, other) and other.z >= protected_top - 1e-9:
                return False

    return True


# =========================================================
# Exact grid pattern for same-size goods
# =========================================================
def best_grid_orientation(box_type, sample_item, available_count):
    """
    對規則長方體箱 + 同尺寸貨物比較所有允許方向。

    「不能疊」貨物不允許垂直堆疊：
      nz 強制最多 1 層。
    """
    best = None

    for dims, rot in orientations(sample_item):
        l, w, h = dims

        nx = int((box_type.l + 1e-9) // l)
        ny = int((box_type.w + 1e-9) // w)
        nz = int((box_type.h + 1e-9) // h)

        if sample_item.cannot_crush:
            nz = min(nz, 1)

        geometric_capacity = nx * ny * nz
        if geometric_capacity <= 0:
            continue

        if sample_item.weight > 0:
            weight_capacity = int((box_type.max_weight + 1e-9) // sample_item.weight)
        else:
            weight_capacity = geometric_capacity

        capacity = min(geometric_capacity, weight_capacity, available_count)
        if capacity <= 0:
            continue

        packed_volume = capacity * l * w * h
        box_volume = box_type.l * box_type.w * box_type.h

        waste_x = box_type.l - nx * l
        waste_y = box_type.w - ny * w
        waste_z = box_type.h - nz * h

        score = (
            capacity,
            packed_volume / box_volume,
            -(waste_x + waste_y + waste_z),
        )

        candidate = {
            "score": score,
            "dims": dims,
            "rotation": rot,
            "nx": nx,
            "ny": ny,
            "nz": nz,
            "capacity": capacity,
        }

        if best is None or candidate["score"] > best["score"]:
            best = candidate

    return best


def pack_grid(box_type, units):
    if not units:
        return []

    sig = item_signature(units[0])
    if any(item_signature(x) != sig for x in units):
        return []

    sample = units[0]
    grid = best_grid_orientation(box_type, sample, len(units))
    if grid is None:
        return []

    l, w, h = grid["dims"]
    nx, ny, nz = grid["nx"], grid["ny"], grid["nz"]
    capacity = grid["capacity"]
    rot = grid["rotation"]

    placements = []
    idx = 0

    for iz in range(nz):
        for iy in range(ny):
            for ix in range(nx):
                if idx >= capacity:
                    return placements

                item = units[idx]
                placements.append(
                    Placement(
                        item_id=item.item_id,
                        name=item.name,
                        x=ix * l,
                        y=iy * w,
                        z=iz * h,
                        l=l,
                        w=w,
                        h=h,
                        weight=item.weight,
                        rotation=rot,
                        cannot_crush=item.cannot_crush,
                    )
                )
                idx += 1

    return placements


# =========================================================
# General heuristic packing for mixed goods
# =========================================================
def fits(space, dims):
    _, _, _, L, W, H = space
    l, w, h = dims
    return l <= L + 1e-9 and w <= W + 1e-9 and h <= H + 1e-9


def overlap(a, b):
    return (
        a.x < b.x + b.l and a.x + a.l > b.x
        and a.y < b.y + b.w and a.y + a.w > b.y
        and a.z < b.z + b.h and a.z + a.h > b.z
    )


def split_space(space, placed):
    x, y, z, L, W, H = space
    p = placed
    new_spaces = []

    if p.x + p.l < x + L - 1e-9:
        new_spaces.append((p.x + p.l, y, z, x + L - (p.x + p.l), W, H))

    if p.y + p.w < y + W - 1e-9:
        new_spaces.append((x, p.y + p.w, z, L, y + W - (p.y + p.w), H))

    # 不能疊貨物上方不建立可用空間。
    if not p.cannot_crush and p.z + p.h < z + H - 1e-9:
        new_spaces.append((x, y, p.z + p.h, L, W, z + H - (p.z + p.h)))

    return [s for s in new_spaces if min(s[3:]) > 1e-9]


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
                sx >= tx and sy >= ty and sz >= tz
                and sx + sL <= tx + tL + 1e-9
                and sy + sW <= ty + tW + 1e-9
                and sz + sH <= tz + tH + 1e-9
            ):
                contained = True
                break

        if not contained:
            filtered.append(s)

    return filtered


def sort_units(units, order):
    """
    無論排序方式為何：
    可承壓貨物先放，不能疊貨物最後放。
    """
    if order == "volume":
        secondary = lambda a: a.l * a.w * a.h
    elif order == "maxside":
        secondary = lambda a: max(a.l, a.w, a.h)
    elif order == "weight":
        secondary = lambda a: a.weight
    else:
        secondary = lambda a: a.l * a.w * a.h

    return sorted(
        units,
        key=lambda a: (
            a.cannot_crush,  # False 先，True 後
            -secondary(a),
        )
    )


def heuristic_pack_one_box(box_type, units, order="volume"):
    ordered = sort_units(units, order)
    spaces = [(0.0, 0.0, 0.0, box_type.l, box_type.w, box_type.h)]
    placements = []
    current_weight = 0.0

    for index, item in enumerate(ordered):
        if current_weight + item.weight > box_type.max_weight + 1e-9:
            continue

        best = None
        best_score = None

        for si, space in enumerate(spaces):
            for dims, rot in orientations(item):
                if not fits(space, dims):
                    continue

                l, w, h = dims
                x, y, z, sL, sW, sH = space

                p = Placement(
                    item_id=item.item_id,
                    name=item.name,
                    x=x, y=y, z=z,
                    l=l, w=w, h=h,
                    weight=item.weight,
                    rotation=rot,
                    cannot_crush=item.cannot_crush,
                )

                if any(overlap(p, q) for q in placements):
                    continue

                if violates_cannot_crush(p, placements):
                    continue

                same_left = sum(
                    1
                    for u in ordered[index:]
                    if item_signature(u) == item_signature(item)
                )

                nx = int((sL + 1e-9) // l)
                ny = int((sW + 1e-9) // w)
                nz = int((sH + 1e-9) // h)

                # 不能疊貨物不允許在自身上方形成第二層同類堆疊。
                if item.cannot_crush:
                    nz = min(nz, 1)

                orientation_capacity = min(nx * ny * nz, same_left)
                residual_volume = sL * sW * sH - l * w * h

                if item.cannot_crush:
                    # 不能疊貨物：
                    # 1. 仍優先較好的方向
                    # 2. 優先較高 Z，盡量放在整箱上方
                    # 3. 再減少零碎空間
                    score = (
                        -orientation_capacity,
                        -z,
                        residual_volume,
                        y,
                        x,
                    )
                else:
                    # 一般貨物：
                    # 優先低 Z，作為底層。
                    score = (
                        -orientation_capacity,
                        z,
                        residual_volume,
                        y,
                        x,
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

    if not validate_cannot_crush(placements):
        return []

    return placements


def candidate_one_box_results(box_type, units):
    candidates = []

    # 各 SKU 規則網格 Pattern
    groups = defaultdict(list)
    for u in units:
        groups[item_signature(u)].append(u)

    for group_units in groups.values():
        placements = pack_grid(box_type, group_units)
        if placements and validate_cannot_crush(placements):
            packed_volume = sum(p.l * p.w * p.h for p in placements)
            candidates.append(
                (len(placements), packed_volume, "grid", placements)
            )

    # 混裝 heuristic
    for order in ("volume", "maxside", "weight"):
        placements = heuristic_pack_one_box(box_type, units, order)
        if placements and validate_cannot_crush(placements):
            packed_volume = sum(p.l * p.w * p.h for p in placements)
            candidates.append(
                (len(placements), packed_volume, f"heuristic-{order}", placements)
            )

    if not candidates:
        return []

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][3]


# =========================================================
# Multi-box packing
# =========================================================
def _pack_using_single_box_type_core(box_type, units):
    remaining = list(units)
    packed_boxes = []
    safety_limit = len(remaining)

    while remaining and len(packed_boxes) < safety_limit:
        placements = candidate_one_box_results(box_type, remaining)
        if not placements:
            break

        packed_boxes.append(PackedBox(box_type, placements))

        used_ids = {p.item_id for p in placements}
        new_remaining = [u for u in remaining if u.item_id not in used_ids]

        if len(new_remaining) >= len(remaining):
            break

        remaining = new_remaining

    return packed_boxes, remaining


def _pack_using_mixed_box_types_core(box_types, units):
    remaining = list(units)
    packed_boxes = []
    safety_limit = len(remaining)

    while remaining and len(packed_boxes) < safety_limit:
        choices = []

        for box_type in box_types:
            placements = candidate_one_box_results(box_type, remaining)
            if not placements:
                continue

            box_volume = box_type.l * box_type.w * box_type.h
            packed_volume = sum(p.l * p.w * p.h for p in placements)

            score = (
                len(placements),
                -box_volume,
                packed_volume,
            )
            choices.append((score, box_type, placements))

        if not choices:
            break

        choices.sort(key=lambda x: x[0], reverse=True)
        _, selected_box, placements = choices[0]

        packed_boxes.append(PackedBox(selected_box, placements))

        used_ids = {p.item_id for p in placements}
        new_remaining = [u for u in remaining if u.item_id not in used_ids]

        if len(new_remaining) >= len(remaining):
            break

        remaining = new_remaining

    return packed_boxes, remaining



def pack_using_single_box_type(box_type, units):
    """
    A333 / 通用 ULD 的 BUP 包裝器。
    BUP 群組個別裝箱；一般貨物最後才混裝。
    """
    all_boxes = []
    all_remaining = []

    for group_name, segment_units, is_bup in partition_bup_units(units):
        boxes, remaining = _pack_using_single_box_type_core(
            box_type,
            segment_units,
        )

        if is_bup:
            for packed in boxes:
                packed.bup_group = group_name

        all_boxes.extend(boxes)
        all_remaining.extend(remaining)

    return all_boxes, all_remaining


def pack_using_mixed_box_types(box_types, units):
    """
    混合 ULD 模式同樣遵守 BUP：
    BUP 群組可以使用多個不同尺寸 ULD，
    但任何裝有該群組貨物的 ULD 都不混入其他群組。
    """
    all_boxes = []
    all_remaining = []

    for group_name, segment_units, is_bup in partition_bup_units(units):
        boxes, remaining = _pack_using_mixed_box_types_core(
            box_types,
            segment_units,
        )

        if is_bup:
            for packed in boxes:
                packed.bup_group = group_name

        all_boxes.extend(boxes)
        all_remaining.extend(remaining)

    return all_boxes, all_remaining


# =========================================================
# 3D visualization
# =========================================================
def cuboid_edges(x, y, z, l, w, h):
    pts = [
        (x, y, z),
        (x+l, y, z),
        (x+l, y+w, z),
        (x, y+w, z),
        (x, y, z+h),
        (x+l, y, z+h),
        (x+l, y+w, z+h),
        (x, y+w, z+h),
    ]

    edges = [
        (0,1),(1,2),(2,3),(3,0),
        (4,5),(5,6),(6,7),(7,4),
        (0,4),(1,5),(2,6),(3,7),
    ]

    return [(pts[a], pts[b]) for a, b in edges]


def make_figure(box_type, placements):
    fig = go.Figure()

    for a, b in cuboid_edges(0, 0, 0, box_type.l, box_type.w, box_type.h):
        fig.add_trace(
            go.Scatter3d(
                x=[a[0], b[0]],
                y=[a[1], b[1]],
                z=[a[2], b[2]],
                mode="lines",
                line=dict(color="black", width=3),
                showlegend=False,
                hoverinfo="skip",
            )
        )

    for p in placements:
        label = "不能疊" if p.cannot_crush else "一般"

        fig.add_trace(
            go.Mesh3d(
                x=[p.x,p.x+p.l,p.x+p.l,p.x,p.x,p.x+p.l,p.x+p.l,p.x],
                y=[p.y,p.y,p.y+p.w,p.y+p.w,p.y,p.y,p.y+p.w,p.y+p.w],
                z=[p.z,p.z,p.z,p.z,p.z+p.h,p.z+p.h,p.z+p.h,p.z+p.h],
                i=[0,0,0,1,1,2,4,4,5,5,6,6],
                j=[1,2,3,2,6,3,5,1,6,2,7,3],
                k=[2,3,1,6,5,7,1,5,2,6,3,7],
                opacity=0.62,
                hovertext=(
                    f"{p.item_id}<br>{p.name}<br>"
                    f"類型={label}<br>"
                    f"XYZ=({p.x:.1f},{p.y:.1f},{p.z:.1f})<br>"
                    f"尺寸={p.l:.1f}×{p.w:.1f}×{p.h:.1f}<br>"
                    f"旋轉={p.rotation}"
                ),
                hoverinfo="text",
                showlegend=False,
            )
        )

    fig.update_layout(
        scene=dict(
            xaxis_title="X",
            yaxis_title="Y",
            zaxis_title="Z",
            aspectmode="data",
        ),
        margin=dict(l=0, r=0, t=20, b=0),
        height=620,
        showlegend=False,
    )

    return fig


# =========================================================
# UI helpers
# =========================================================
def safe_bool(value, default=False):
    if pd.isna(value):
        return default
    return bool(value)


ITEM_COLUMNS = [
    "ID", "名稱", "AGT", "BUP",
    "長(cm)", "寬(cm)", "高(cm)", "數量", "總重量(kg)",
    "水平旋轉", "垂直旋轉", "不能疊",
]

REQUIRED_CSV_COLUMNS = ["ID", "名稱", "長(cm)", "寬(cm)", "高(cm)", "數量"]


def default_item_dataframe():
    return pd.DataFrame(
        [
            {
                "ID": "",
                "名稱": "",
                "AGT": "",
                "BUP": False,
                "長(cm)": 0.0,
                "寬(cm)": 0.0,
                "高(cm)": 0.0,
                "數量": 0,
                "總重量(kg)": 0.0,
                "水平旋轉": True,
                "垂直旋轉": False,
                "不能疊": False,
            }
        ],
        columns=ITEM_COLUMNS,
    )


def parse_csv_bool(value, default=False):
    """CSV 常見布林值轉換：TRUE/FALSE、1/0、是/否、Y/N、勾選/不勾選。"""
    if pd.isna(value) or str(value).strip() == "":
        return default

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    true_values = {"true", "1", "yes", "y", "是", "勾選", "有", "on"}
    false_values = {"false", "0", "no", "n", "否", "不勾選", "無", "off"}

    if normalized in true_values:
        return True
    if normalized in false_values:
        return False

    raise ValueError(f"無法判斷布林值：{value}")


def normalize_item_csv(df):
    """整理匯入 CSV，補上選填欄位與預設值，並驗證資料型態。"""
    df = df.copy()
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    # 接受幾個較直覺的欄名別名。
    aliases = {
        "名稱/品名": "名稱",
        "品名": "名稱",
        "長": "長(cm)",
        "長度": "長(cm)",
        "寬": "寬(cm)",
        "寬度": "寬(cm)",
        "高": "高(cm)",
        "高度": "高(cm)",
        "重量": "總重量(kg)",
        "重量(kg)": "總重量(kg)",
        "總重": "總重量(kg)",
        "總重量": "總重量(kg)",
        "數量(件)": "數量",
        "公司": "AGT",
        "客戶": "AGT",
        "群組": "AGT",
        "代理": "AGT",
        "Agent": "AGT",
        "agent": "AGT",
        "不能壓": "不能疊",
    }
    df = df.rename(columns={c: aliases.get(c, c) for c in df.columns})

    missing = [c for c in REQUIRED_CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("CSV 缺少必要欄位：" + "、".join(missing))

    defaults = {
        "AGT": "",
        "BUP": False,
        "總重量(kg)": 0.0,
        "水平旋轉": True,
        "垂直旋轉": False,
        "不能疊": False,
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    # 僅保留程式需要的欄位並固定順序。
    df = df[ITEM_COLUMNS]

    numeric_cols = ["長(cm)", "寬(cm)", "高(cm)", "數量", "總重量(kg)"]
    for col in numeric_cols:
        converted = pd.to_numeric(df[col], errors="coerce")
        bad_rows = converted.isna() & df[col].notna()
        if bad_rows.any():
            row_numbers = [str(i + 2) for i in df.index[bad_rows].tolist()[:5]]
            raise ValueError(f"欄位「{col}」含有非數字資料，CSV 列：{', '.join(row_numbers)}")
        df[col] = converted

    if (df[["長(cm)", "寬(cm)", "高(cm)"]] <= 0).any().any():
        raise ValueError("長、寬、高必須大於 0。")
    if (df["數量"] < 0).any():
        raise ValueError("數量不可小於 0。")
    if (df["總重量(kg)"] < 0).any():
        raise ValueError("重量不可小於 0。")

    df["數量"] = df["數量"].fillna(0).astype(int)
    df["總重量(kg)"] = df["總重量(kg)"].fillna(0.0).astype(float)

    for col, default in [
        ("BUP", False),
        ("水平旋轉", True),
        ("垂直旋轉", False),
        ("不能疊", False),
    ]:
        df[col] = [parse_csv_bool(v, default) for v in df[col]]

    df["ID"] = df["ID"].fillna("").astype(str).str.strip()
    df["名稱"] = df["名稱"].fillna("").astype(str).str.strip()
    df["AGT"] = df["AGT"].fillna("").astype(str).str.strip()

    return df.reset_index(drop=True)


def read_item_csv(csv_bytes):
    """支援 UTF-8/UTF-8-SIG/Big5/CP950 CSV。"""
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            decoded = csv_bytes.decode(encoding)
            raw_df = pd.read_csv(io.StringIO(decoded))
            return normalize_item_csv(raw_df)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except Exception:
            raise

    raise ValueError(f"無法辨識 CSV 編碼：{last_error}")


def packing_extents(placements):
    """取得目前貨物實際占用的最大外緣：max(X+L), max(Y+W), max(Z+H)。"""
    if not placements:
        return 0.0, 0.0, 0.0

    return (
        max(p.x + p.l for p in placements),
        max(p.y + p.w for p in placements),
        max(p.z + p.h for p in placements),
    )


def dataframe_to_items(df):
    items = []

    for _, r in df.iterrows():
        item_id = str(r["ID"]).strip()
        if not item_id:
            continue

        qty = int(r["數量"])
        if qty <= 0:
            continue

        # 「總重量(kg)」代表該列全部數量的合計重量。
        # Packing Engine 內部仍以單件貨物運算，因此在這裡換算成單件重量。
        total_weight = float(r["總重量(kg)"])
        unit_weight = total_weight / qty if qty > 0 else 0.0

        items.append(
            Item(
                item_id=item_id,
                name=str(r["名稱"]),
                l=float(r["長(cm)"]),
                w=float(r["寬(cm)"]),
                h=float(r["高(cm)"]),
                qty=qty,
                weight=unit_weight,
                # 新增列時，水平旋轉預設 True、垂直旋轉預設 False。
                horizontal_rotate=safe_bool(r["水平旋轉"], True),
                vertical_rotate=safe_bool(r["垂直旋轉"], False),
                cannot_crush=safe_bool(r["不能疊"], False),
                agt=str(r.get("AGT", "") or "").strip(),
                bup=safe_bool(r.get("BUP", False), False),
                batch_id=item_id,
            )
        )

    return items


def display_packing_result(packed_boxes, remaining):
    placed_count = sum(len(b.placements) for b in packed_boxes)

    total_box_volume = sum(
        b.box_type.l * b.box_type.w * b.box_type.h
        for b in packed_boxes
    )

    packed_volume = sum(
        p.l * p.w * p.h
        for b in packed_boxes
        for p in b.placements
    )

    utilization = packed_volume / total_box_volume * 100 if total_box_volume else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("需要 ULD 數", len(packed_boxes))
    c2.metric("成功裝入", placed_count)
    c3.metric("無法裝入", len(remaining))
    c4.metric("整體空間利用率", f"{utilization:.1f}%")

    if packed_boxes:
        counts = Counter(b.box_type.box_id for b in packed_boxes)
        name_map = {b.box_type.box_id: b.box_type.name for b in packed_boxes}

        st.subheader("📊 建議 ULD 數量")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ULD ID": box_id,
                        "ULD 名稱": name_map[box_id],
                        "需要數量": qty,
                    }
                    for box_id, qty in counts.items()
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    if remaining:
        st.error("有貨物無法放入目前選定的 ULD。")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "貨物ID": x.item_id,
                        "名稱": x.name,
                        "AGT": x.agt,
                        "批次ID": x.batch_id,
                        "BUP": x.bup,
                        "尺寸": f"{x.l}×{x.w}×{x.h}",
                        "單件重量(kg)": round(x.weight, 3),
                        "不能疊": x.cannot_crush,
                    }
                    for x in remaining
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("全部輸入貨物已成功分配完成。")

    if not packed_boxes:
        return

    summary = []

    for idx, b in enumerate(packed_boxes, 1):
        box_volume = b.box_type.l * b.box_type.w * b.box_type.h
        used_volume = sum(p.l * p.w * p.h for p in b.placements)
        total_weight = sum(p.weight for p in b.placements)

        summary.append(
            {
                "ULD序號": idx,
                "ULD ID": b.box_type.box_id,
                "名稱": b.box_type.name,
                "BUP ID": b.bup_group or "-",
                "ULD尺寸": f"{b.box_type.l}×{b.box_type.w}×{b.box_type.h}",
                "貨物數": len(b.placements),
                "ULD內總重量(kg)": round(total_weight, 2),
                "空間利用率": f"{used_volume / box_volume * 100:.1f}%",
            }
        )

    st.subheader("📦 每 ULD 配置")
    st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

    for idx, b in enumerate(packed_boxes, 1):
        with st.expander(
            f"ULD {idx}｜{b.box_type.box_id} {b.box_type.name}｜"
            f"{len(b.placements)} 件貨物"
        ):
            st.plotly_chart(
                make_figure(b.box_type, b.placements),
                use_container_width=True,
                key=f"plot_{idx}_{b.box_type.box_id}",
            )

            max_x, max_y, max_z = packing_extents(b.placements)
            # 三個指標緊密集中在最左側。
            mx, my, mz, metric_spacer = st.columns([0.72, 0.72, 0.72, 7.84], gap="small")
            mx.metric("目前貨物最大 長", f"{max_x:.2f}")
            my.metric("目前貨物最大 寬", f"{max_y:.2f}")
            mz.metric("目前貨物最大 高", f"{max_z:.2f}")
            st.caption(
                "最大值以貨物外緣計算：長=max(X+L)、寬=max(Y+W)、高=max(Z+H)。"
                f" ULD上限：長={b.box_type.l:.2f}、寬={b.box_type.w:.2f}、高={b.box_type.h:.2f}。"
            )

            result_df = pd.DataFrame(
                [
                    {
                        "貨物ID": p.item_id,
                        "名稱": p.name,
                        "不能疊": p.cannot_crush,
                        "X": round(p.x, 2),
                        "Y": round(p.y, 2),
                        "Z": round(p.z, 2),
                        "L": round(p.l, 2),
                        "W": round(p.w, 2),
                        "H": round(p.h, 2),
                        "單件重量(kg)": round(p.weight, 3),
                        "RX": p.rotation[0],
                        "RY": p.rotation[1],
                        "RZ": p.rotation[2],
                    }
                    for p in b.placements
                ]
            )

            st.dataframe(result_df, use_container_width=True, hide_index=True)



def invalidate_packing_result():
    """貨物或箱型資料變更後，舊裝箱結果不再顯示。"""
    st.session_state.pop("mode", None)
    st.session_state.pop("result", None)


def validate_item_data_for_packing(df):
    """
    計算前驗證有效貨物列。
    空白 ID 或數量 <= 0 的列視為未使用，不報錯。
    """
    errors = []

    for index, r in df.iterrows():
        item_id = str(r.get("ID", "")).strip()

        try:
            qty = int(r.get("數量", 0) or 0)
        except Exception:
            errors.append(f"第 {index + 1} 列：數量必須是整數。")
            continue

        if not item_id or qty <= 0:
            continue

        try:
            l = float(r.get("長(cm)", 0) or 0)
            w = float(r.get("寬(cm)", 0) or 0)
            h = float(r.get("高(cm)", 0) or 0)
            weight = float(r.get("總重量(kg)", 0) or 0)
        except Exception:
            errors.append(f"第 {index + 1} 列（{item_id}）：長、寬、高、重量必須是數字。")
            continue

        if l <= 0 or w <= 0 or h <= 0:
            errors.append(f"第 {index + 1} 列（{item_id}）：數量大於 0 時，長、寬、高必須大於 0。")
        if weight < 0:
            errors.append(f"第 {index + 1} 列（{item_id}）：重量不可小於 0。")

    return errors




# =========================================================
# App UI
# =========================================================
st.title("✈️ 3D貨物排列系統 v1.13.2")
st.caption(
    "可上線版：ULD／貨箱資料改由 Google Sheets 即時讀寫；保留目前 A333、B777、BUP 與盤位規則。"
)

if "item_data" not in st.session_state:
    st.session_state["item_data"] = default_item_dataframe()
if "item_editor_version" not in st.session_state:
    st.session_state["item_editor_version"] = 0
if "uld_editor_version" not in st.session_state:
    st.session_state["uld_editor_version"] = 0
if "selected_aircraft" not in st.session_state:
    st.session_state["selected_aircraft"] = "A333"
if "_last_selected_aircraft" not in st.session_state:
    st.session_state["_last_selected_aircraft"] = st.session_state["selected_aircraft"]


# =========================================================
# Collapsible sidebar
# =========================================================
with st.sidebar:
    st.header("✈️ 功能選單")

    page = st.radio(
        "頁面",
        [
            "🏠 起始頁",
            "🧱 貨物資料",
            "🚀 自動裝載",
            "🧰 ULD／箱子管理",
        ],
        label_visibility="collapsed",
        key="sidebar_page",
    )

    st.divider()

    current_profile = get_aircraft_profile(st.session_state["selected_aircraft"])
    st.caption("目前選擇機型")
    st.markdown(f"**{current_profile.display_name}**")
    st.caption(f"狀態：{current_profile.status_text}")

    st.divider()
    st.caption(f"ULD 資料來源：{storage_backend_name()}")

    st.caption("側邊欄可使用 Streamlit 左上方箭頭收合。")


# =========================================================
# Page: 起始頁
# =========================================================
if page == "🏠 起始頁":
    st.subheader("選擇飛機機型")

    codes = aircraft_codes()
    current_index = (
        codes.index(st.session_state["selected_aircraft"])
        if st.session_state["selected_aircraft"] in codes
        else 0
    )

    selected_aircraft = st.selectbox(
        "飛機機型",
        codes,
        index=current_index,
        format_func=aircraft_label,
        key="home_aircraft_selector",
    )

    if selected_aircraft != st.session_state["selected_aircraft"]:
        st.session_state["selected_aircraft"] = selected_aircraft
        st.session_state["_last_selected_aircraft"] = selected_aircraft
        invalidate_packing_result()
        st.rerun()

    profile = get_aircraft_profile(st.session_state["selected_aircraft"])
    aircraft_module = get_aircraft_module(profile.code)

    c1, c2, c3 = st.columns(3)
    c1.metric("機型", profile.code)
    c2.metric("類型", profile.aircraft_type)
    c3.metric("裝載計算", "可測試" if profile.allow_packing else "待設定")

    st.markdown(f"### {profile.display_name}")
    st.write(profile.description)

    if profile.notes:
        with st.expander("此機型目前設定", expanded=True):
            for note in profile.notes:
                st.write(f"- {note}")

    boxes = load_boxes()
    compatible_ulds = get_compatible_ulds(
        boxes,
        profile.code,
        enabled_only=True,
    )

    st.markdown("### 此機型目前可用 ULD")

    if compatible_ulds:
        uld_df = pd.DataFrame(
            [
                {
                    "ULD ID": b["box_id"],
                    "名稱": b["name"],
                    "長(cm)": b["l"],
                    "寬(cm)": b["w"],
                    "高(cm)": b["h"],
                    "最大載重(kg)": b["max_weight"],
                }
                for b in compatible_ulds
            ]
        )
        st.dataframe(uld_df, use_container_width=True, hide_index=True)
        st.success(
            f"已自動帶入 {len(compatible_ulds)} 種適用於 {profile.code} 的 ULD。"
        )
    else:
        st.warning(
            f"{profile.code} 目前尚未設定可用 ULD。"
            "請從左側選單進入「ULD／箱子管理」新增或指定適用機型。"
        )

    if profile.code == "A333":
        st.info(
            "A333 目前為測試階段：裝載限制先以 boxes.json 中所設定的 ULD "
            "長／寬／高與最大載重為基礎。尚未加入艙門、貨艙輪廓、位置、重心等航空專用限制。"
        )
    elif profile.code == "B777":
        st.info(
            "B777-200F 目前已啟用 B~M 上艙第一階段測試。"
            "後上艙 contour 尚未取得，因此只計算 B~M 區域。"
        )

        contour_df = pd.DataFrame(
            [
                {"半寬位置(cm)": p.x, "最大可用高度(cm)": p.height}
                for p in BM_HALF_CONTOUR
            ]
        )
        st.dataframe(contour_df, use_container_width=True, hide_index=True)

        st.plotly_chart(
            make_contour_figure(),
            use_container_width=True,
            key="b777_home_contour",
        )

        st.caption(POSITION_RULE_NOTE)

        if REAR_UPPER_HALF_CONTOUR is None:
            st.warning("後上艙 contour：尚未設定，取得資料後再加入。")


# =========================================================
# Page: 貨物資料
# =========================================================
elif page == "🧱 貨物資料":
    profile = get_aircraft_profile(st.session_state["selected_aircraft"])
    st.subheader(f"貨物資料｜{profile.code}")

    st.markdown("#### CSV 匯入")
    import_col, import_spacer = st.columns([1, 2])

    with import_col:
        uploaded_csv = st.file_uploader(
            "匯入貨物 CSV",
            type=["csv"],
            help=(
                "必要欄位：ID、名稱、長(cm)、寬(cm)、高(cm)、數量。"
                "AGT、BUP、總重量(kg)、水平旋轉、垂直旋轉、不能疊可省略。"
                "舊 CSV 的「重量(kg)」也可匯入，並視為該列總重量。"
            ),
            key="item_csv_upload",
        )

    if uploaded_csv is not None:
        csv_bytes = uploaded_csv.getvalue()
        upload_hash = hashlib.sha256(csv_bytes).hexdigest()

        if st.session_state.get("last_item_csv_hash") != upload_hash:
            try:
                imported_df = read_item_csv(csv_bytes)
                st.session_state["item_data"] = imported_df
                st.session_state["last_item_csv_hash"] = upload_hash
                st.session_state["item_editor_version"] += 1
                invalidate_packing_result()
                st.success(f"CSV 匯入成功，共 {len(imported_df)} 筆貨物資料。")
            except Exception as exc:
                st.error(f"CSV 匯入失敗：{exc}")

    reset_col, info_col = st.columns([1, 3])
    with reset_col:
        if st.button("重設貨物資料", use_container_width=True):
            st.session_state["item_data"] = default_item_dataframe()
            st.session_state["item_editor_version"] += 1
            st.session_state.pop("last_item_csv_hash", None)
            invalidate_packing_result()
            st.rerun()

    with info_col:
        st.caption(
            "表格採批次編輯：可連續輸入數值、勾選或取消勾選，"
            "完成後再按「套用貨物資料」。"
        )

    with st.form(
        f"item_edit_form_{st.session_state['item_editor_version']}",
        clear_on_submit=False,
    ):
        edited_item_df = st.data_editor(
            st.session_state["item_data"],
            num_rows="dynamic",
            use_container_width=True,
            key=f"item_editor_{st.session_state['item_editor_version']}",
            column_config={
                "BUP": st.column_config.CheckboxColumn(
                    "BUP",
                    help=(
                        "同一「ID」只要任一列開啟 BUP，該 ID 的所有貨物都會視為同一批專用裝箱；"
                        "可以跨多列、不同尺寸，且該 ULD 不會再混入其他 ID 貨物。"
                        "AGT 只作公司／代理資訊，不作 BUP 分組依據。"
                    ),
                    default=False,
                ),
                "水平旋轉": st.column_config.CheckboxColumn(
                    "水平旋轉",
                    help="允許 L/W 在水平面互換",
                    default=True,
                ),
                "垂直旋轉": st.column_config.CheckboxColumn(
                    "垂直旋轉",
                    help="允許改變哪一個尺寸作為高度",
                    default=False,
                ),
                "不能疊": st.column_config.CheckboxColumn(
                    "不能疊",
                    help="勾選後此類貨物會優先放在上方，且其上方不得再放其他貨物",
                    default=False,
                ),
            },
        )

        apply_items = st.form_submit_button(
            "✅ 套用貨物資料",
            type="primary",
            use_container_width=True,
        )

    if apply_items:
        st.session_state["item_data"] = edited_item_df.copy()
        invalidate_packing_result()
        st.success("貨物資料已套用。")

    st.info(
        "規則：水平旋轉預設開啟；垂直旋轉預設關閉。"
        "「不能疊」貨物上方不得再放其他貨物。"
        "BUP：以「ID」為批次判斷。同一 ID 只要任一列勾選 BUP，該 ID 全部貨物會使用專用 ULD；"
        "可自動分成多個 ULD，但不會與其他 ID 混裝。未啟用 BUP 的貨物可互相混裝。"
        "AGT 僅供標示公司／代理。"
    )
    st.caption(
        "重量輸入規則：「總重量(kg)」是該列全部貨物的合計重量。"
        "例如數量 5、總重量 500 kg，系統會以每件 100 kg 進行 ULD 載重與排列計算。"
    )


# =========================================================
# Page: ULD / 箱子管理
# =========================================================
elif page == "🧰 ULD／箱子管理":
    st.subheader("ULD／箱子管理")
    st.write(
        "此頁直接管理 Google Sheets 的 ULD／貨箱資料。"
        "新增、修改、刪除並儲存後會同步寫回線上 `boxes` worksheet。"
    )

    status_col, seed_col = st.columns([2, 1])

    with status_col:
        if st.button(
            "🔄 測試 Google Sheets 連線",
            use_container_width=True,
        ):
            try:
                ok, message = storage_healthcheck()
                if ok:
                    st.success(message)
                else:
                    st.error(message)
            except Exception as exc:
                st.error(f"Google Sheets 連線失敗：{exc}")

    with seed_col:
        if st.button(
            "☁️ 補入缺少的預設 ULD",
            use_container_width=True,
        ):
            try:
                added_count, added_ids = seed_missing_default_boxes()
                if added_count:
                    st.success(
                        f"已補入 {added_count} 筆：{', '.join(added_ids)}"
                    )
                    st.session_state["uld_editor_version"] += 1
                    invalidate_packing_result()
                    st.rerun()
                else:
                    st.info("Google Sheets 已包含所有目前預設 ULD。")
            except Exception as exc:
                st.error(f"無法補入預設 ULD：{exc}")

    st.caption(
        "上線預設資料來源為 Google Sheets。"
        "若要在本機暫時改用 boxes.json，可設定環境變數 BOX_STORE_BACKEND=json。"
    )

    st.caption(
        "「適用機型」請用逗號分隔，例如：A333 或 A333,B777。"
        "「適用區域」例如：A333_GENERIC、B777_UPPER_BM。"
        "B777 中央裝載時必須使用兩個同尺寸 ULD。"
        "PGA 單側固定占 2 個 118 盤位、中央固定占 4 個；"
        "118/PGA/114 只能用於上貨艙。"
        "114 規格：310×236、最高 140 cm、只能使用機頭2位＋機尾2位中央專用位置；"
        "96 為機尾最後方唯一中央專用盤位，尺寸 317×243×234。"
        "因 114 最大載重尚未提供，本版不自行加入 114 到 boxes.json。"
        "新增 114 後會自動套用專用規則。"
    )

    boxes = load_boxes()
    editor_df = boxes_to_editor_dataframe(boxes)

    with st.form(
        f"uld_edit_form_{st.session_state['uld_editor_version']}",
        clear_on_submit=False,
    ):
        edited_uld_df = st.data_editor(
            editor_df,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"uld_editor_{st.session_state['uld_editor_version']}",
            column_config={
                "可中央裝載": st.column_config.CheckboxColumn(
                    "可中央裝載",
                    help=(
                        "只有勾選此欄的 B777 ULD，才可以在本次計算開啟中央裝載時使用。"
                    ),
                    default=False,
                ),
                "中央裝載盤位數": st.column_config.NumberColumn(
                    "中央裝載盤位數",
                    help=(
                        "僅 B777 中央裝載使用。中央裝載固定使用兩個同尺寸 ULD；"
                        "請設定此配對總共占用的 aircraft 盤位數，例如 2 或 4。"
                    ),
                    min_value=2,
                    max_value=22,
                    step=2,
                    default=2,
                ),
                "啟用": st.column_config.CheckboxColumn(
                    "啟用",
                    default=True,
                ),
            },
        )

        save_uld = st.form_submit_button(
            "💾 儲存 ULD 資料",
            type="primary",
            use_container_width=True,
        )

    if save_uld:
        try:
            new_boxes = editor_dataframe_to_boxes(
                edited_uld_df,
                valid_aircraft_codes=aircraft_codes(),
            )
            errors = validate_uld_records(
                new_boxes,
                valid_aircraft_codes=aircraft_codes(),
            )

            if errors:
                st.error("ULD 資料有需要修正的欄位：")
                for error in errors:
                    st.write(f"- {error}")
            else:
                save_boxes(new_boxes)
                st.session_state["uld_editor_version"] += 1
                invalidate_packing_result()
                st.success("ULD 資料已同步儲存至 Google Sheets。")
                st.rerun()
        except Exception as exc:
            st.error(f"無法儲存 ULD 資料：{exc}")

    st.markdown("#### 機型程式模組")
    module_rows = []
    for code in aircraft_codes():
        p = get_aircraft_profile(code)
        module_rows.append(
            {
                "機型": p.code,
                "名稱": p.display_name,
                "類型": p.aircraft_type,
                "狀態": p.status_text,
                "裝載計算": "啟用" if p.allow_packing else "暫停",
                "程式檔": p.module_file,
            }
        )
    st.dataframe(pd.DataFrame(module_rows), use_container_width=True, hide_index=True)




# =========================================================
# Page: 自動裝載
# =========================================================
elif page == "🚀 自動裝載":
    profile = get_aircraft_profile(st.session_state["selected_aircraft"])
    aircraft_module = get_aircraft_module(profile.code)

    st.subheader(f"自動裝載｜{profile.display_name}")

    current_item_df = st.session_state["item_data"]
    validation_errors = validate_item_data_for_packing(current_item_df)

    if validation_errors:
        st.error("貨物資料有需要修正的欄位：")
        for error in validation_errors[:10]:
            st.write(f"- {error}")
        if len(validation_errors) > 10:
            st.write(f"- 另有 {len(validation_errors) - 10} 筆錯誤。")
        st.stop()

    items = dataframe_to_items(current_item_df)
    units = expand_items(items)

    if not units:
        st.error("目前沒有有效貨物資料。請先到「貨物資料」輸入資料並按「套用貨物資料」。")
        st.stop()

    # ---------------------------------------------------------
    # B777 dedicated ULD + contour-aware 3D packing
    # ---------------------------------------------------------
    if profile.code == "B777":
        st.info(
            "B777 B~M 上艙現在會先依 ULD 的長／寬／高度／載重建立 packing surface，"
            "再依每件貨物在 surface 內的實際橫向 Y 位置套用 aircraft contour 高度。"
        )
        st.caption(
            "SIDE / 中央裝載代表『盤位／ULD surface 占用方式』，"
            "不是把每件貨物鎖死在側邊或中央。貨物可在 surface 內偏左、偏右或置中。"
        )
        st.caption(POSITION_RULE_NOTE)
        st.info(
            "已套用 B777 上艙盤位規則：118 等效盤位最多 22（左右各 11）；"
            "PGA 單側占 2、中央占 4；盤位圖採左側機頭、右側機尾。"
            "114 以前方2個＋後方2個中央專用位置直接嵌入盤位圖；"
            "最右側為唯一1個96機尾中央專用盤位。"
        )

        all_boxes = load_boxes()
        compatible_boxes = get_compatible_ulds(
            all_boxes,
            "B777",
            enabled_only=True,
            zone="B777_UPPER_BM",
        )

        if not compatible_boxes:
            st.error(
                "B777_UPPER_BM 目前沒有可使用 ULD。"
                "請至「ULD／箱子管理」新增 B777 ULD，"
                "並將適用區域設為 B777_UPPER_BM。"
            )
            st.stop()

        box_options = {
            (
                f"{b['box_id']}｜{b['name']}｜"
                f"{b['l']}×{b['w']}×{b['h']} cm｜"
                f"載重 {b['max_weight']} kg"
            ): b
            for b in compatible_boxes
        }

        selected_labels = st.multiselect(
            "本次可使用 B777 上艙 ULD",
            list(box_options.keys()),
            default=list(box_options.keys()),
        )

        selected_ulds = [
            box_options[label]
            for label in selected_labels
        ]

        allow_center_this_run = st.checkbox(
            "本次允許中央裝載",
            value=False,
            help=(
                "關閉：本次只計算單側 ULD。"
                "開啟：只有在 ULD／箱子管理中勾選「可中央裝載」的 ULD "
                "才會加入中央裝載候選。"
            ),
            key="b777_allow_center_this_run",
        )

        if allow_center_this_run:
            center_capable = [
                b for b in selected_ulds
                if bool(b.get("allow_center_load", False))
            ]
            if not center_capable:
                st.warning(
                    "本次雖已開啟中央裝載，但目前選取的 ULD 都沒有勾選「可中央裝載」，"
                    "因此實際仍只會計算單側裝載。"
                )
        else:
            st.caption(
                "中央裝載目前為關閉狀態；即使某 ULD 支援中央裝載，本次也不會自動選用。"
            )

        if selected_ulds:
            selected_df = pd.DataFrame(
                [
                    {
                        "ULD ID": b["box_id"],
                        "名稱": b["name"],
                        "長(cm)": b["l"],
                        "寬(cm)": b["w"],
                        "設定高(cm)": b["h"],
                        "最大載重(kg)": b["max_weight"],
                        "可中央裝載": b.get("allow_center_load", False),
                        "中央裝載盤位數": (
                            b.get("center_positions", 2)
                            if b.get("allow_center_load", False)
                            else "-"
                        ),
                        "B-M已知contour半寬上限(cm)": min(float(b["w"]), 242.0),
                        "盤位規則": (
                            "PGA：單側2 / 中央4個118盤位"
                            if str(b["box_id"]).upper() == "PGA"
                            else (
                                "114：機頭2＋機尾2中央專用 / 高140"
                                if str(b["box_id"]).upper() == "114"
                                else (
                                    "96：機尾唯一中央專用 / 317×243×234"
                                    if str(b["box_id"]).upper() == "96"
                                    else "一般118等效盤位"
                                )
                            )
                        ),
                    }
                    for b in selected_ulds
                ]
            )
            st.dataframe(
                selected_df,
                use_container_width=True,
                hide_index=True,
            )

            for b in selected_ulds:
                for warning in b777_uld_config_warnings(b):
                    st.warning(f"{b['box_id']}：{warning}")

        with st.expander(
            "查看 B-M 輪廓參考圖（僅顯示機艙可用輪廓，不代表目前貨物）",
            expanded=False,
        ):
            st.caption(
                "這張圖的用途是提供 B-M 艙體『寬度－最大高度』基準。"
                "真正的貨物形狀會在計算完成後，於下方的『貨物剖面圖』與『3D 貨物裝載圖』顯示。"
            )
            st.plotly_chart(
                make_contour_figure(),
                use_container_width=True,
                key="b777_contour_reference",
            )

        if st.button(
            "🚀 計算 B777 B-M ULD 3D 裝載",
            type="primary",
            use_container_width=True,
        ):
            if not selected_ulds:
                st.error("請至少選擇一種 B777 ULD。")
                st.stop()

            with st.spinner(
                "正在比較不同 ULD 尺寸、可用裝載模式、"
                "貨物旋轉與 B-M contour..."
            ):
                loads, remaining = plan_upper_deck_uld(
                    units,
                    selected_ulds,
                    allow_center=allow_center_this_run,
                )

            st.session_state["b777_uld_loads"] = loads
            st.session_state["b777_uld_remaining"] = remaining
            st.session_state["result_aircraft"] = "B777"

        loads = st.session_state.get("b777_uld_loads", [])
        remaining = st.session_state.get("b777_uld_remaining", [])

        if loads or remaining:
            st.markdown("### B777 上艙整體盤位")

            c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
            c1.metric("Loading Surface 數", len(loads))
            c2.metric("實際使用 ULD 數", total_uld_units_used(loads))
            c3.metric(
                "118盤位",
                f"{total_118_positions_used(loads)}/22",
            )
            c4.metric(
                "114專用位置",
                f"{total_114_positions_used(loads)}/4",
            )
            c5.metric(
                "尾端96",
                f"{total_96_tail_positions_used(loads)}/1",
            )
            c6.metric("成功裝入", total_pieces_loaded(loads))
            c7.metric("未裝入", len(remaining))

            st.caption(
                "Loading Surface 是一次裝載組合；實際 ULD 數會依組合計算。"
                "例如中央裝載 1 個 Loading Surface = 2 個同尺寸 ULD。"
                "PGA 單側會占 2 個 118 盤位；PGA 中央會占 4 個。"
            )

            st.plotly_chart(
                make_position_plan_figure(loads),
                use_container_width=True,
                key="b777_uld_position_plan",
            )

            if loads:
                summary_rows = []

                for load in loads:
                    max_l, used_w, max_h = load_extents(load)
                    total_weight = sum(
                        p.weight
                        for p in load.placements
                    )

                    summary_rows.append(
                        {
                            "Load ID": load.load_id,
                            "ULD": load.spec.uld_id,
                            "ULD名稱": load.spec.uld_name,
                            "BUP ID": load.bup_group or "-",
                            "Surface": (
                                "中央裝載"
                                if load.spec.loading_mode == "CENTER"
                                else (
                                    (
                                        "114專用位置"
                                        if load.spec.position_family == "114_SPECIAL"
                                        else "尾端96專用位置"
                                    )
                                    if load.spec.position_family in {"114_SPECIAL", "96_TAIL"}
                                    else f"{load.side}側"
                                )
                            ),
                            "盤位家族": (
                                (
                                    "114專用"
                                    if load.spec.position_family == "114_SPECIAL"
                                    else "96尾端專用"
                                )
                                if load.spec.position_family in {"114_SPECIAL", "96_TAIL"}
                                else "118等效"
                            ),
                            "118等效盤位數": (
                                len(load.occupied_positions)
                                if load.spec.position_family == "118_EQUIV"
                                else 0
                            ),
                            "需要同尺寸ULD數": load.spec.uld_units_required,
                            "中央裝載盤位數": (
                                load.spec.positions_used
                                if load.spec.loading_mode == "CENTER"
                                else "-"
                            ),
                            "Bay": "-".join(load.bays),
                            "占用盤位": ",".join(load.occupied_positions),
                            "貨物數": len(load.placements),
                            "總重量(kg)": round(total_weight, 2),
                            "Surface長(cm)": round(load.spec.base_length, 2),
                            "Surface寬(cm)": round(load.spec.surface_width, 2),
                            "設定最大高(cm)": round(load.spec.nominal_height, 2),
                            "目前貨物最大長(cm)": round(max_l, 2),
                            "目前貨物最大寬(cm)": round(used_w, 2),
                            "目前貨物最大高(cm)": round(max_h, 2),
                        }
                    )

                st.dataframe(
                    pd.DataFrame(summary_rows),
                    use_container_width=True,
                    hide_index=True,
                )

                st.markdown("### 3D 貨物裝載圖")

                load_map = {
                    (
                        f"{load.load_id}｜{load.spec.uld_id}｜"
                        f"{'-'.join(load.bays)}｜{len(load.placements)}件"
                    ): load
                    for load in loads
                }

                selected_load_label = st.selectbox(
                    "選擇要查看的 ULD / Loading Surface",
                    list(load_map.keys()),
                    key="b777_3d_load_selector",
                )

                selected_load = load_map[selected_load_label]

                st.markdown("#### 貨物剖面圖")

                st.caption(
                    "這張剖面圖會把目前 ULD 內的『實際貨物矩形』畫在 B-M 輪廓中。"
                    "使用 X 滑桿可以沿飛機前後方向切換剖面；"
                    "只有被該 X 平面切到的貨物會顯示。"
                )

                slice_max = max(
                    [p.x + p.l for p in selected_load.placements],
                    default=selected_load.spec.base_length,
                )
                slice_max = max(float(slice_max), 1.0)

                slice_x = st.slider(
                    "剖面 X 位置 (cm)",
                    min_value=0.0,
                    max_value=float(slice_max),
                    value=float(slice_max) / 2.0,
                    step=max(float(slice_max) / 100.0, 1.0),
                    key=f"b777_slice_{selected_load.load_id}",
                )

                st.plotly_chart(
                    make_load_cross_section_figure(
                        selected_load,
                        slice_x,
                    ),
                    use_container_width=True,
                    key=f"b777_cross_section_{selected_load.load_id}_{slice_x:.2f}",
                )

                st.markdown("#### 3D 貨物裝載圖")

                st.plotly_chart(
                    make_load_3d_figure(selected_load),
                    use_container_width=True,
                    key=f"b777_3d_{selected_load.load_id}",
                )

                current_max_l, current_max_w, current_max_h = load_extents(
                    selected_load
                )

                # 與 A333 相同：三個尺寸指標緊密排列在 3D 圖下方。
                mx, my, mz, metric_spacer = st.columns(
                    [0.72, 0.72, 0.72, 7.84],
                    gap="small",
                )
                mx.metric("目前貨物最大 長", f"{current_max_l:.2f}")
                my.metric("目前貨物最大 寬", f"{current_max_w:.2f}")
                mz.metric("目前貨物最大 高", f"{current_max_h:.2f}")

                st.caption(
                    "最大值以貨物外緣計算："
                    "長=max(X+L)、"
                    "寬=貨物實際橫向最左至最右外緣範圍、"
                    "高=max(Z+H)。"
                    f" ULD/Surface上限："
                    f"長={selected_load.spec.base_length:.2f}、"
                    f"寬={selected_load.spec.surface_width:.2f}、"
                    f"高={selected_load.spec.nominal_height:.2f} cm。"
                )

                placement_rows = []

                for p in selected_load.placements:
                    aircraft_y0, aircraft_y1 = local_to_aircraft_y(
                        selected_load.spec,
                        p,
                        side=selected_load.side,
                    )

                    placement_rows.append(
                        {
                            "貨物ID": p.item_id,
                            "名稱": p.name,
                            "X": round(p.x, 2),
                            "Local Y": round(p.y, 2),
                            "Aircraft Y起": round(aircraft_y0, 2),
                            "Aircraft Y迄": round(aircraft_y1, 2),
                            "Z": round(p.z, 2),
                            "L": round(p.l, 2),
                            "W": round(p.w, 2),
                            "H": round(p.h, 2),
                            "單件重量(kg)": round(p.weight, 2),
                            "最外側半寬(cm)": round(p.outer_half_width, 2),
                            "該位置Contour限制高(cm)": round(p.contour_limit_height, 2),
                            "貨物頂高(cm)": round(p.z + p.h, 2),
                            "RX": p.rotation[0],
                            "RY": p.rotation[1],
                            "RZ": p.rotation[2],
                            "不能疊": p.cannot_crush,
                        }
                    )

                st.dataframe(
                    pd.DataFrame(placement_rows),
                    use_container_width=True,
                    hide_index=True,
                )

            if remaining:
                st.error(
                    f"尚有 {len(remaining)} 件貨物無法放入目前 B-M 可用 ULD / 盤位。"
                )

                remaining_df = pd.DataFrame(
                    [
                        {
                            "貨物ID": unit.item_id,
                            "名稱": unit.name,
                            "原始尺寸": f"{unit.l}×{unit.w}×{unit.h}",
                            "單件重量(kg)": round(unit.weight, 2),
                        }
                        for unit in remaining
                    ]
                )

                st.dataframe(
                    remaining_df,
                    use_container_width=True,
                    hide_index=True,
                )

        st.warning(
            "B777 v1.5 仍屬 B-M 上艙工程測試："
            "目前已計算 ULD 基底尺寸與 aircraft contour，"
            "但尚未加入後上艙、下腹艙、正式 position max weight、"
            "floor loading、CG、door clearance 等航空作業限制。"
        )

    # ---------------------------------------------------------
    # A333 existing generic ULD packing
    # ---------------------------------------------------------
    else:
        all_boxes = load_boxes()
        compatible_boxes = get_compatible_ulds(
            all_boxes,
            profile.code,
            enabled_only=True,
        )

        if not compatible_boxes:
            st.error(
                f"{profile.code} 目前沒有可使用的 ULD。"
                "請先至「ULD／箱子管理」設定適用機型。"
            )
            st.stop()

        st.success(
            f"已依 {profile.code} 自動載入 {len(compatible_boxes)} 種可用 ULD。"
        )

        box_options = {
            (
                f"{b['box_id']}｜{b['name']}｜"
                f"{b['l']}×{b['w']}×{b['h']} cm｜"
                f"載重 {b['max_weight']} kg"
            ): b
            for b in compatible_boxes
        }

        selected_labels = st.multiselect(
            "本次可使用 ULD",
            list(box_options.keys()),
            default=list(box_options.keys()),
        )

        mode = st.radio(
            "計算模式",
            [
                "混合 ULD：系統自動判斷 ULD 組合",
                "單一 ULD：逐一比較每種 ULD 需要幾個",
            ],
            horizontal=True,
        )

        if st.button("🚀 計算", type="primary", use_container_width=True):
            if not selected_labels:
                st.error("請至少選擇一種 ULD。")
                st.stop()

            selected_boxes = [
                BoxType(
                    b["box_id"],
                    b["name"],
                    float(b["l"]),
                    float(b["w"]),
                    float(b["h"]),
                    float(b["max_weight"]),
                )
                for b in [box_options[label] for label in selected_labels]
            ]

            aircraft_errors = aircraft_module.validate_loading(
                items=items,
                units=units,
                ulds=[box_options[label] for label in selected_labels],
            )

            if aircraft_errors:
                st.error(f"{profile.code} 機型規則檢查未通過：")
                for error in aircraft_errors:
                    st.write(f"- {error}")
                st.stop()

            st.write(f"輸入貨物總量：**{len(units)} 件**")

            if mode.startswith("混合 ULD"):
                with st.spinner("正在依貨量搜尋 ULD 組合..."):
                    packed_boxes, remaining = pack_using_mixed_box_types(
                        selected_boxes,
                        units,
                    )

                st.session_state["mode"] = "mixed"
                st.session_state["result"] = [(packed_boxes, remaining)]
                st.session_state["result_aircraft"] = profile.code

            else:
                results = []

                with st.spinner("正在逐一比較各 ULD..."):
                    for box_type in selected_boxes:
                        packed_boxes, remaining = pack_using_single_box_type(
                            box_type,
                            units,
                        )
                        results.append((box_type, packed_boxes, remaining))

                st.session_state["mode"] = "single"
                st.session_state["result"] = results
                st.session_state["result_aircraft"] = profile.code

        if (
            st.session_state.get("result_aircraft")
            and st.session_state.get("result_aircraft") != profile.code
        ):
            invalidate_packing_result()

        if st.session_state.get("mode") == "mixed":
            packed_boxes, remaining = st.session_state["result"][0]
            st.markdown("### 混合 ULD 建議")
            display_packing_result(packed_boxes, remaining)

        elif st.session_state.get("mode") == "single":
            st.markdown("### 各 ULD 比較")

            compare_rows = []

            for box_type, packed_boxes, remaining in st.session_state["result"]:
                total_box_volume = sum(
                    b.box_type.l * b.box_type.w * b.box_type.h
                    for b in packed_boxes
                )

                used_volume = sum(
                    p.l * p.w * p.h
                    for b in packed_boxes
                    for p in b.placements
                )

                utilization = (
                    used_volume / total_box_volume * 100
                    if total_box_volume
                    else 0
                )

                compare_rows.append(
                    {
                        "ULD ID": box_type.box_id,
                        "ULD 名稱": box_type.name,
                        "需要 ULD 數": (
                            len(packed_boxes)
                            if not remaining
                            else "無法完整裝入"
                        ),
                        "未裝入件數": len(remaining),
                        "整體利用率": f"{utilization:.1f}%",
                    }
                )

            st.dataframe(
                pd.DataFrame(compare_rows),
                use_container_width=True,
                hide_index=True,
            )

            options = [
                f"{box_type.box_id}｜{box_type.name}"
                for box_type, _, _ in st.session_state["result"]
            ]

            selected_detail = st.selectbox("查看某一 ULD 詳細排列", options)
            selected_index = options.index(selected_detail)

            box_type, packed_boxes, remaining = st.session_state["result"][selected_index]
            display_packing_result(packed_boxes, remaining)
