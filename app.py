
import json
import io
import hashlib
from dataclasses import dataclass
from pathlib import Path
from collections import Counter, defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

conn = st.connection("gsheets", type=GSheetsConnection)

try:
    df = conn.read(
        spreadsheet="https://docs.google.com/spreadsheets/d/1KJntRmxBOLyl1lfEo1Sqi8MS59GNXo12z-ETlkfEX-8/edit?usp=sharing",
        worksheet="boxes",
        ttl="0"
    )
except Exception as e:
    # 如果試算表是空的，自動建立一組帶有正確欄位名稱的空表格
    st.warning("⚠️ 無法讀取雲端資料庫，已為您建立空白暫存表。")
    df = pd.DataFrame(columns=["box_name", "length", "width", "height"])



APP_DIR = Path(__file__).resolve().parent

# 建立 Google Sheets 連線
conn = st.connection("gsheets", type=GSheetsConnection)

# 讀取資料表（填入你剛剛複製的試算表網址）
# ttl="0" 代表不快取，每次重新整理網頁都會抓最新資料
df = conn.read(
    spreadsheet="https://docs.google.com/spreadsheets/d/1KJntRmxBOLyl1lfEo1Sqi8MS59GNXo12z-ETlkfEX-8/edit?usp=sharing",
    worksheet="boxes",
    ttl="0"
)

# 1. 確保你的表單輸入元件（例如 text_input, number_input）都在這裡
# 範例：
# input_id = st.text_input("箱型 ID")
# input_name = st.text_input("箱型名稱")

# 2. 只有在按下「新增箱型」按鈕時，才執行裡面的程式碼
if st.button("確認新增箱型"):
    # 在按鈕內部定義 new_box
    new_box = {
        "box_id": input_id,     # 請對應你網頁上的輸入變數名稱
        "name": input_name,
        "L": input_l,
        "W": input_w,
        "H": input_h,
        "max_weight": input_weight
    }
    
    # 轉成 DataFrame
    new_data = pd.DataFrame([new_box])
    
    # 與從 Google Sheets 讀出來的 df 合併
    updated_df = pd.concat([df, new_data], ignore_index=True)
    
    # 更新回 Google Sheets
    conn.update(worksheet="boxes", data=updated_df)
    st.success("✅ 新箱型已成功同步至 Google Sheets！")
    st.rerun() # 重新整理網頁畫面以顯示新資料


# 在網頁上呈現資料
st.set_page_config(page_title="3D貨物排列系統v1.0", layout="wide")


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


# =========================================================
# Box library
# =========================================================
def load_boxes():
    try:
        # 直接使用先前建立的 conn 連線讀取 Google Sheets
        df = conn.read(worksheet="boxes", ttl="0")

        # 將欄位名稱統一調整為你演算法中使用的名稱（確保大小寫一致，例如 L/W/H 或 l/w/h）
        # 如果試算表是小寫 l, w, h，而演算法需要大寫，可以在這裡用 rename 修正：
        # df = df.rename(columns={"l": "L", "w": "W", "h": "H", "weight": "max_weight"})

        # 轉成 dict 格式陣列回傳給你的演算法
        return df.to_dict('records')
    except Exception as e:
        # 如果讀取失敗，回傳預設的空陣列，防止整頁崩潰
        return []


def save_boxes(boxes):
    BOX_DB.write_text(json.dumps(boxes, ensure_ascii=False, indent=2), encoding="utf-8")


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
    units = []
    for item in items:
        for i in range(item.qty):
            units.append(
                Item(
                    item_id=f"{item.item_id}-{i+1:03d}",
                    name=item.name,
                    l=item.l,
                    w=item.w,
                    h=item.h,
                    qty=1,
                    weight=item.weight,
                    horizontal_rotate=item.horizontal_rotate,
                    vertical_rotate=item.vertical_rotate,
                    cannot_crush=item.cannot_crush,
                )
            )
    return units


def item_signature(item):
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
def pack_using_single_box_type(box_type, units):
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


def pack_using_mixed_box_types(box_types, units):
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
    "ID", "名稱", "長(cm)", "寬(cm)", "高(cm)", "數量", "重量(kg)",
    "水平旋轉", "垂直旋轉", "不能疊",
]

REQUIRED_CSV_COLUMNS = ["ID", "名稱", "長(cm)", "寬(cm)", "高(cm)", "數量"]


def default_item_dataframe():
    return pd.DataFrame(
        [
            {
                "ID": "",
                "名稱": "",
                "長(cm)": 0.0,
                "寬(cm)": 0.0,
                "高(cm)": 0.0,
                "數量": 0,
                "重量(kg)": 0.0,
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
        "重量": "重量(kg)",
        "數量(件)": "數量",
        "不能壓": "不能疊",
    }
    df = df.rename(columns={c: aliases.get(c, c) for c in df.columns})

    missing = [c for c in REQUIRED_CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("CSV 缺少必要欄位：" + "、".join(missing))

    defaults = {
        "重量(kg)": 0.0,
        "水平旋轉": True,
        "垂直旋轉": False,
        "不能疊": False,
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    # 僅保留程式需要的欄位並固定順序。
    df = df[ITEM_COLUMNS]

    numeric_cols = ["長(cm)", "寬(cm)", "高(cm)", "數量", "重量(kg)"]
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
    if (df["重量(kg)"] < 0).any():
        raise ValueError("重量不可小於 0。")

    df["數量"] = df["數量"].fillna(0).astype(int)
    df["重量(kg)"] = df["重量(kg)"].fillna(0.0).astype(float)

    for col, default in [
        ("水平旋轉", True),
        ("垂直旋轉", False),
        ("不能疊", False),
    ]:
        df[col] = [parse_csv_bool(v, default) for v in df[col]]

    df["ID"] = df["ID"].fillna("").astype(str).str.strip()
    df["名稱"] = df["名稱"].fillna("").astype(str).str.strip()

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
        if not str(r["ID"]).strip():
            continue

        qty = int(r["數量"])
        if qty <= 0:
            continue

        items.append(
            Item(
                item_id=str(r["ID"]).strip(),
                name=str(r["名稱"]),
                l=float(r["長(cm)"]),
                w=float(r["寬(cm)"]),
                h=float(r["高(cm)"]),
                qty=qty,
                weight=float(r["重量(kg)"]),
                # 新增列時，水平旋轉預設 True、垂直旋轉預設 False。
                horizontal_rotate=safe_bool(r["水平旋轉"], True),
                vertical_rotate=safe_bool(r["垂直旋轉"], False),
                cannot_crush=safe_bool(r["不能疊"], False),
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
    c1.metric("需要箱數", len(packed_boxes))
    c2.metric("成功裝入", placed_count)
    c3.metric("無法裝入", len(remaining))
    c4.metric("整體空間利用率", f"{utilization:.1f}%")

    if packed_boxes:
        counts = Counter(b.box_type.box_id for b in packed_boxes)
        name_map = {b.box_type.box_id: b.box_type.name for b in packed_boxes}

        st.subheader("📊 建議箱型數量")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "箱型ID": box_id,
                        "箱型名稱": name_map[box_id],
                        "需要數量": qty,
                    }
                    for box_id, qty in counts.items()
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    if remaining:
        st.error("有貨物無法放入目前選定的箱型。")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "貨物ID": x.item_id,
                        "名稱": x.name,
                        "尺寸": f"{x.l}×{x.w}×{x.h}",
                        "重量(kg)": x.weight,
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
                "箱號": idx,
                "箱型": b.box_type.box_id,
                "名稱": b.box_type.name,
                "箱尺寸": f"{b.box_type.l}×{b.box_type.w}×{b.box_type.h}",
                "貨物數": len(b.placements),
                "重量(kg)": round(total_weight, 2),
                "空間利用率": f"{used_volume / box_volume * 100:.1f}%",
            }
        )

    st.subheader("📦 每箱配置")
    st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

    for idx, b in enumerate(packed_boxes, 1):
        with st.expander(
            f"箱 {idx}｜{b.box_type.box_id} {b.box_type.name}｜"
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
                f" 箱體上限：長={b.box_type.l:.2f}、寬={b.box_type.w:.2f}、高={b.box_type.h:.2f}。"
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
                        "重量(kg)": p.weight,
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
            weight = float(r.get("重量(kg)", 0) or 0)
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
st.title("📦 3D貨物排列系統v1.0")
st.caption("操作效能改善版：貨物表格改為批次套用，並只執行目前選擇的功能頁面。")

if "item_data" not in st.session_state:
    st.session_state["item_data"] = default_item_dataframe()
if "item_editor_version" not in st.session_state:
    st.session_state["item_editor_version"] = 0

# 不再使用 st.tabs。
# st.tabs 會執行所有頁籤內容，包含大量 Plotly 3D 圖。
# 改成單頁選擇器後，只會執行目前選擇的頁面。
page = st.radio(
    "功能頁面",
    ["📦 箱子管理", "🧱 貨物資料", "🚀 自動裝箱"],
    horizontal=True,
    label_visibility="collapsed",
    key="main_page",
)

st.divider()


# =========================================================
# Page: 箱子管理
# =========================================================
if page == "📦 箱子管理":
    boxes = load_boxes()

    st.subheader("箱型資料庫")
    st.write("箱型會保存在本機 `boxes.json`。")

    with st.form("add_box"):
        c1, c2, c3 = st.columns(3)
        new_id = c1.text_input("箱型 ID", value=f"BOX-{len(boxes)+1:02d}")
        new_name = c2.text_input("箱型名稱", value="新箱型")
        new_l = c3.number_input("長 (cm)", min_value=1.0, value=50.0)

        c4, c5, c6 = st.columns(3)
        new_w = c4.number_input("寬 (cm)", min_value=1.0, value=40.0)
        new_h = c5.number_input("高 (cm)", min_value=1.0, value=40.0)
        new_weight = c6.number_input("最大載重 (kg)", min_value=0.1, value=20.0)

        submitted_box = st.form_submit_button("新增箱型")

    if submitted_box:
        if any(x["box_id"] == new_id for x in boxes):
            st.error("箱型 ID 已存在。")
        else:
            boxes.append(
                {
                    "box_id": new_id,
                    "name": new_name,
                    "l": new_l,
                    "w": new_w,
                    "h": new_h,
                    "max_weight": new_weight,
                }
            )
            save_boxes(boxes)
            invalidate_packing_result()
            st.success("箱型已儲存。")

    boxes = load_boxes()

    if boxes:
        df_boxes = pd.DataFrame(boxes)
        df_boxes.columns = [
            "箱型ID",
            "名稱",
            "長(cm)",
            "寬(cm)",
            "高(cm)",
            "最大載重(kg)",
        ]

        st.dataframe(df_boxes, use_container_width=True, hide_index=True)

        delete_col, spacer_col = st.columns([1, 3])
        with delete_col:
            delete_id = st.selectbox("刪除箱型", [x["box_id"] for x in boxes])
            if st.button("刪除選定箱型", use_container_width=True):
                boxes = [x for x in boxes if x["box_id"] != delete_id]
                save_boxes(boxes)
                invalidate_packing_result()
                st.success("箱型已刪除。")
                st.rerun()


# =========================================================
# Page: 貨物資料
# =========================================================
elif page == "🧱 貨物資料":
    st.subheader("貨物資料")

    st.markdown("#### CSV 匯入")
    import_col, import_spacer = st.columns([1, 2])

    with import_col:
        uploaded_csv = st.file_uploader(
            "匯入貨物 CSV",
            type=["csv"],
            help=(
                "必要欄位：ID、名稱、長(cm)、寬(cm)、高(cm)、數量。"
                "重量(kg)、水平旋轉、垂直旋轉、不能疊可省略。"
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
            "表格現在採「批次編輯」：可以連續輸入數值、勾選或取消勾選，"
            "完成後再按「套用貨物資料」。編輯途中不會重新執行整支程式。"
        )

    # 關鍵改善：
    # data_editor 放入 form 後，欄位變更只留在瀏覽器端，
    # 不會每改一格就觸發 Streamlit 全程 rerun。
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
        # 僅在使用者按下套用時，才將編輯內容寫入正式資料。
        st.session_state["item_data"] = edited_item_df.copy()
        invalidate_packing_result()
        st.success("貨物資料已套用。現在可以切換至「自動裝箱」進行計算。")

    st.info(
        "規則：水平旋轉預設開啟；垂直旋轉預設關閉。"
        "「不能疊」貨物會在一般貨物之後配置，優先選擇較高 Z，且上方禁止再放其他貨物。"
    )


# =========================================================
# Page: 自動裝箱
# =========================================================
elif page == "🚀 自動裝箱":
    st.subheader("依輸入貨量計算所需箱型與箱數")

    boxes = load_boxes()

    if not boxes:
        st.error("請先新增至少一種箱型。")
        st.stop()

    box_options = {
        f"{b['box_id']}｜{b['name']}｜{b['l']}×{b['w']}×{b['h']} cm｜載重 {b['max_weight']} kg": b
        for b in boxes
    }

    selected_labels = st.multiselect(
        "選擇可使用箱型",
        list(box_options.keys()),
        default=list(box_options.keys()),
    )

    mode = st.radio(
        "計算模式",
        [
            "混合箱型：系統自動判斷箱型組合",
            "單一箱型：逐一比較每種箱型需要幾箱",
        ],
        horizontal=True,
    )

    if st.button("🚀 計算", type="primary", use_container_width=True):
        if not selected_labels:
            st.error("請至少選擇一種箱型。")
            st.stop()

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

        if not units:
            st.error("目前沒有有效貨物資料。請先到「貨物資料」輸入資料並按「套用貨物資料」。")
            st.stop()

        st.write(f"輸入貨物總量：**{len(units)} 件**")

        if mode.startswith("混合箱型"):
            with st.spinner("正在依貨量搜尋箱型組合..."):
                packed_boxes, remaining = pack_using_mixed_box_types(
                    selected_boxes,
                    units,
                )

            st.session_state["mode"] = "mixed"
            st.session_state["result"] = [(packed_boxes, remaining)]

        else:
            results = []

            with st.spinner("正在逐一比較各箱型..."):
                for box_type in selected_boxes:
                    packed_boxes, remaining = pack_using_single_box_type(
                        box_type,
                        units,
                    )
                    results.append((box_type, packed_boxes, remaining))

            st.session_state["mode"] = "single"
            st.session_state["result"] = results

    # 只有在「自動裝箱」頁面才會產生表格與 Plotly 3D 圖。
    if st.session_state.get("mode") == "mixed":
        packed_boxes, remaining = st.session_state["result"][0]
        st.markdown("### 混合箱型建議")
        display_packing_result(packed_boxes, remaining)

    elif st.session_state.get("mode") == "single":
        st.markdown("### 各箱型比較")

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
                    "箱型ID": box_type.box_id,
                    "箱型名稱": box_type.name,
                    "需要箱數": (
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

        selected_detail = st.selectbox("查看某一箱型詳細排列", options)
        selected_index = options.index(selected_detail)

        box_type, packed_boxes, remaining = st.session_state["result"][selected_index]
        display_packing_result(packed_boxes, remaining)
