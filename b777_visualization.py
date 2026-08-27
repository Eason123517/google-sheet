"""
B777 B-M visualization.

包含：
- 2D B-M position loading plan
- B-M aircraft contour
- 每個 ULD / loading surface 的 3D cargo packing
"""

from __future__ import annotations

import plotly.graph_objects as go

from b777_contours import full_symmetric_contour
from b777_positions import (
    UPPER_118_BAYS,
    UPPER_114_FRONT_POSITIONS,
    UPPER_114_REAR_POSITIONS,
    UPPER_114_SPECIAL_POSITIONS,
    UPPER_96_TAIL_POSITION,
)
from b777_uld_packing import local_to_aircraft_y, placement_extents


def make_contour_figure():
    points = full_symmetric_contour()
    xs = [x for x, _ in points]
    hs = [h for _, h in points]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=xs,
            y=hs,
            mode="lines+markers",
            name="B-M 可用輪廓",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=[xs[0], xs[-1]],
            y=[0, 0],
            mode="lines",
            name="甲板",
        )
    )

    fig.update_layout(
        title="B777-200F 上艙 B-M 輪廓參考（此圖本身不含貨物）",
        xaxis_title="橫向位置（cm，0=中心線）",
        yaxis_title="可用高度（cm）",
        height=520,
        showlegend=True,
    )

    fig.update_xaxes(range=[-255, 255])
    fig.update_yaxes(range=[0, 315])

    return fig


def make_position_plan_figure(loads):
    """
    B777 上艙橫向盤位圖。

    左 = 機頭
    右 = 機尾

    視覺排列：
      114-F1 | 114-F2 | 118等效盤位 01~11 | 114-R1 | 114-R2 | 96-T

    - 118 等效盤位維持上下兩列：右側 R / 左側 L。
    - 114 為中央專用位置，因此畫在上下兩列中間並跨越兩列高度，
      不再另外畫第三列，也不標示為左/右側。
    - 96-T 為機尾中間唯一專用盤位，畫在最右側並跨越兩列高度。
    """
    fig = go.Figure()

    # Geometry
    row_y = {"L": 0.0, "R": 1.0}
    cell_half_w = 0.46
    cell_half_h = 0.36

    # Longitudinal X layout, left -> right.
    front_x = {
        "114-F1": 0.0,
        "114-F2": 1.15,
    }

    main_start_x = 2.55
    main_x = {
        bay: main_start_x + idx
        for idx, bay in enumerate(UPPER_118_BAYS)
    }

    rear_start_x = main_start_x + len(UPPER_118_BAYS) + 0.55
    rear_x = {
        "114-R1": rear_start_x,
        "114-R2": rear_start_x + 1.15,
    }

    tail_x = rear_start_x + 2.65

    special_center_y = 0.5
    special_y0 = -0.34
    special_y1 = 1.34

    # -------------------------------------------------------
    # Front 114 center positions
    # -------------------------------------------------------
    for position in UPPER_114_FRONT_POSITIONS:
        x = front_x[position]
        fig.add_shape(
            type="rect",
            x0=x - 0.50,
            x1=x + 0.50,
            y0=special_y0,
            y1=special_y1,
            line_width=2,
            fillcolor="rgba(0,0,0,0)",
        )
        fig.add_annotation(
            x=x,
            y=special_center_y,
            text=position,
            showarrow=False,
            font=dict(size=9),
        )

    # -------------------------------------------------------
    # 118-equivalent L/R grid
    # -------------------------------------------------------
    for bay, x in main_x.items():
        for side, y in row_y.items():
            fig.add_shape(
                type="rect",
                x0=x - cell_half_w,
                x1=x + cell_half_w,
                y0=y - cell_half_h,
                y1=y + cell_half_h,
                line_width=1,
                fillcolor="rgba(0,0,0,0)",
            )

    # -------------------------------------------------------
    # Rear 114 center positions
    # -------------------------------------------------------
    for position in UPPER_114_REAR_POSITIONS:
        x = rear_x[position]
        fig.add_shape(
            type="rect",
            x0=x - 0.50,
            x1=x + 0.50,
            y0=special_y0,
            y1=special_y1,
            line_width=2,
            fillcolor="rgba(0,0,0,0)",
        )
        fig.add_annotation(
            x=x,
            y=special_center_y,
            text=position,
            showarrow=False,
            font=dict(size=9),
        )

    # -------------------------------------------------------
    # Unique tail 96 center position
    # -------------------------------------------------------
    fig.add_shape(
        type="rect",
        x0=tail_x - 0.58,
        x1=tail_x + 0.58,
        y0=special_y0,
        y1=special_y1,
        line_width=2,
        fillcolor="rgba(0,0,0,0)",
    )
    fig.add_annotation(
        x=tail_x,
        y=special_center_y,
        text="96-T",
        showarrow=False,
        font=dict(size=9),
    )

    # -------------------------------------------------------
    # Loaded surfaces
    # -------------------------------------------------------
    for load in loads:
        family = load.spec.position_family

        if family == "114_SPECIAL":
            position = load.occupied_positions[0]
            x = (
                front_x[position]
                if position in front_x
                else rear_x[position]
            )

            fig.add_shape(
                type="rect",
                x0=x - 0.46,
                x1=x + 0.46,
                y0=special_y0 + 0.05,
                y1=special_y1 - 0.05,
                opacity=0.35,
                line_width=2,
            )
            fig.add_annotation(
                x=x,
                y=special_center_y,
                text=(
                    f"{load.load_id}<br>"
                    f"114<br>"
                    f"{len(load.placements)}件"
                ),
                showarrow=False,
                font=dict(size=8),
            )
            continue

        if family == "96_TAIL":
            fig.add_shape(
                type="rect",
                x0=tail_x - 0.54,
                x1=tail_x + 0.54,
                y0=special_y0 + 0.05,
                y1=special_y1 - 0.05,
                opacity=0.35,
                line_width=2,
            )
            fig.add_annotation(
                x=tail_x,
                y=special_center_y,
                text=(
                    f"{load.load_id}<br>"
                    f"96<br>"
                    f"{len(load.placements)}件"
                ),
                showarrow=False,
                font=dict(size=8),
            )
            continue

        # Regular 118-equivalent positions.
        for position in load.occupied_positions:
            bay = position[:-1]
            side = position[-1]
            x = main_x[bay]
            y = row_y[side]

            fig.add_shape(
                type="rect",
                x0=x - 0.42,
                x1=x + 0.42,
                y0=y - 0.32,
                y1=y + 0.32,
                opacity=0.35,
                line_width=2,
            )
            fig.add_annotation(
                x=x,
                y=y,
                text=(
                    f"{load.load_id}<br>"
                    f"{load.spec.uld_id}<br>"
                    f"{len(load.placements)}件"
                ),
                showarrow=False,
                font=dict(size=8),
            )

    # -------------------------------------------------------
    # Labels / orientation
    # -------------------------------------------------------
    fig.add_annotation(
        x=front_x["114-F1"] - 0.85,
        y=1.55,
        text="機頭",
        showarrow=False,
        font=dict(size=11),
    )
    fig.add_annotation(
        x=tail_x + 0.85,
        y=1.55,
        text="機尾",
        showarrow=False,
        font=dict(size=11),
    )

    fig.add_annotation(
        x=(front_x["114-F1"] + front_x["114-F2"]) / 2.0,
        y=-0.62,
        text="機頭 114×2",
        showarrow=False,
        font=dict(size=9),
    )
    fig.add_annotation(
        x=(rear_x["114-R1"] + rear_x["114-R2"]) / 2.0,
        y=-0.62,
        text="機尾 114×2",
        showarrow=False,
        font=dict(size=9),
    )
    fig.add_annotation(
        x=tail_x,
        y=-0.62,
        text="尾端唯一96",
        showarrow=False,
        font=dict(size=9),
    )

    fig.update_layout(
        title=(
            "B777 上艙橫向盤位配置｜"
            "左側機頭 → 右側機尾"
        ),
        xaxis=dict(
            tickmode="array",
            tickvals=list(main_x.values()),
            ticktext=list(UPPER_118_BAYS),
            title="縱向位置（118 等效位置暫用 01~11）",
            range=[front_x["114-F1"] - 1.2, tail_x + 1.2],
        ),
        yaxis=dict(
            tickmode="array",
            tickvals=[0, 1],
            ticktext=["左側 L", "右側 R"],
            title="側別",
            range=[-0.85, 1.75],
        ),
        height=420,
        showlegend=False,
        margin=dict(l=30, r=30, t=60, b=40),
    )

    return fig


def _box_vertices(x, y, z, l, w, h):
    return (
        [x, x+l, x+l, x, x, x+l, x+l, x],
        [y, y, y+w, y+w, y, y, y+w, y+w],
        [z, z, z, z, z+h, z+h, z+h, z+h],
    )


def make_load_3d_figure(load):
    spec = load.spec
    fig = go.Figure()

    # -------------------------------------------------------
    # Aircraft contour: draw at front / rear of this load.
    # -------------------------------------------------------
    if spec.position_family in {"114_SPECIAL", "96_TAIL"}:
        # 114 頭尾精細 contour 尚未取得。
        # 先畫固定 140cm 上限平面邊界，不誤用 B-M contour。
        limit = spec.nominal_height
        for longitudinal_x in (0.0, spec.base_length):
            fig.add_trace(
                go.Scatter3d(
                    x=[longitudinal_x, longitudinal_x],
                    y=[-spec.half_width, spec.half_width],
                    z=[limit, limit],
                    mode="lines",
                    name="114 目前固定高度上限",
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
    else:
        contour = full_symmetric_contour()
        contour_y = [x for x, _ in contour]
        contour_z = [h for _, h in contour]

        for longitudinal_x in (0.0, spec.base_length):
            fig.add_trace(
                go.Scatter3d(
                    x=[longitudinal_x] * len(contour_y),
                    y=contour_y,
                    z=contour_z,
                    mode="lines",
                    name="B-M contour",
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

        for y, z in contour:
            fig.add_trace(
                go.Scatter3d(
                    x=[0.0, spec.base_length],
                    y=[y, y],
                    z=[z, z],
                    mode="lines",
                    showlegend=False,
                    hoverinfo="skip",
                    opacity=0.18,
                )
            )

    # -------------------------------------------------------
    # Loading base / ULD footprint.
    # -------------------------------------------------------
    if spec.loading_mode == "CENTER":
        base_y0 = -spec.half_width
        base_y1 = spec.half_width
    elif load.side == "L":
        base_y0 = -spec.half_width
        base_y1 = 0.0
    else:
        base_y0 = 0.0
        base_y1 = spec.half_width

    base_edges = [
        ([0, spec.base_length], [base_y0, base_y0], [0, 0]),
        ([0, spec.base_length], [base_y1, base_y1], [0, 0]),
        ([0, 0], [base_y0, base_y1], [0, 0]),
        ([spec.base_length, spec.base_length], [base_y0, base_y1], [0, 0]),
    ]

    for xs, ys, zs in base_edges:
        fig.add_trace(
            go.Scatter3d(
                x=xs,
                y=ys,
                z=zs,
                mode="lines",
                showlegend=False,
                hoverinfo="skip",
            )
        )

    # -------------------------------------------------------
    # Cargo cuboids.
    # -------------------------------------------------------
    for p in load.placements:
        y0, y1 = local_to_aircraft_y(spec, p, side=load.side)
        actual_w = y1 - y0

        xs, ys, zs = _box_vertices(
            p.x,
            y0,
            p.z,
            p.l,
            actual_w,
            p.h,
        )

        fig.add_trace(
            go.Mesh3d(
                x=xs,
                y=ys,
                z=zs,
                i=[0,0,0,1,1,2,4,4,5,5,6,6],
                j=[1,2,3,2,6,3,5,1,6,2,7,3],
                k=[2,3,1,6,5,7,1,5,2,6,3,7],
                opacity=0.62,
                hovertext=(
                    f"{p.item_id}<br>{p.name}<br>"
                    f"X={p.x:.1f}<br>"
                    f"Aircraft Y={y0:.1f}~{y1:.1f}<br>"
                    f"Z={p.z:.1f}<br>"
                    f"尺寸={p.l:.1f}×{p.w:.1f}×{p.h:.1f}<br>"
                    f"Contour限制高={p.contour_limit_height:.1f}<br>"
                    f"旋轉={p.rotation}"
                ),
                hoverinfo="text",
                showlegend=False,
            )
        )

    title_mode = (
        "114專用位置"
        if spec.position_family == "114_SPECIAL"
        else (
            "機尾中間96專用位置"
            if spec.position_family == "96_TAIL"
            else (
                "中央裝載"
                if spec.loading_mode == "CENTER"
                else f"{load.side}側"
            )
        )
    )

    fig.update_layout(
        title=(
            f"{load.load_id}｜{spec.uld_id} {spec.uld_name}｜"
            f"{title_mode}｜{len(load.placements)} 件"
        ),
        scene=dict(
            xaxis_title="前後 X (cm)",
            yaxis_title="飛機橫向 Y (cm)",
            zaxis_title="高度 Z (cm)",
            aspectmode="data",
        ),
        height=680,
        margin=dict(l=0, r=0, t=50, b=0),
        showlegend=False,
    )

    return fig



def make_load_cross_section_figure(load, slice_x: float):
    """
    在指定 longitudinal X 位置切剖面，
    顯示 aircraft contour + 該 X 位置實際被切到的 cargo 矩形。
    """
    spec = load.spec
    fig = go.Figure()

    if spec.position_family in {"114_SPECIAL", "96_TAIL"}:
        contour_y = [-spec.half_width, spec.half_width]
        contour_z = [spec.nominal_height, spec.nominal_height]

        fig.add_trace(
            go.Scatter(
                x=contour_y,
                y=contour_z,
                mode="lines",
                name=(
                    "114目前固定140cm上限"
                    if spec.position_family == "114_SPECIAL"
                    else f"96盤位高度上限 {spec.nominal_height:.0f}cm"
                ),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=contour_y,
                y=[0, 0],
                mode="lines",
                name="甲板",
            )
        )
    else:
        contour = full_symmetric_contour()
        contour_y = [x for x, _ in contour]
        contour_z = [h for _, h in contour]

        fig.add_trace(
            go.Scatter(
                x=contour_y,
                y=contour_z,
                mode="lines+markers",
                name="B-M 可用輪廓",
            )
        )

        fig.add_trace(
            go.Scatter(
                x=[contour_y[0], contour_y[-1]],
                y=[0, 0],
                mode="lines",
                name="甲板",
            )
        )

    if spec.position_family in {"114_SPECIAL", "96_TAIL"}:
        base_y0 = -spec.surface_width / 2.0
        base_y1 = spec.surface_width / 2.0
        surface_label = (
            "114專用位置（頭尾精細輪廓待補）"
            if spec.position_family == "114_SPECIAL"
            else "機尾中間96專用位置"
        )
    elif spec.loading_mode == "CENTER":
        base_y0 = -spec.half_width
        base_y1 = spec.half_width
        surface_label = "中央裝載（2 個同尺寸 ULD）"
    elif load.side == "L":
        base_y0 = -spec.half_width
        base_y1 = 0.0
        surface_label = "左側 ULD"
    else:
        base_y0 = 0.0
        base_y1 = spec.half_width
        surface_label = "右側 ULD"

    fig.add_shape(
        type="line",
        x0=base_y0,
        x1=base_y1,
        y0=0,
        y1=0,
        line=dict(width=5),
    )

    visible_count = 0

    for p in load.placements:
        if not (p.x - 1e-9 <= slice_x <= p.x + p.l + 1e-9):
            continue

        y0, y1 = local_to_aircraft_y(spec, p, side=load.side)

        fig.add_shape(
            type="rect",
            x0=y0,
            x1=y1,
            y0=p.z,
            y1=p.z + p.h,
            opacity=0.38,
            line=dict(width=2),
        )

        fig.add_annotation(
            x=(y0 + y1) / 2.0,
            y=p.z + p.h / 2.0,
            text=(
                f"{p.item_id}<br>"
                f"W={p.w:.0f}<br>"
                f"H={p.h:.0f}"
            ),
            showarrow=False,
            font=dict(size=10),
        )

        visible_count += 1

    if visible_count == 0:
        fig.add_annotation(
            x=0,
            y=140,
            text="此 X 剖面位置沒有貨物",
            showarrow=False,
            font=dict(size=16),
        )

    fig.update_layout(
        title=(
            f"{load.load_id}｜X={slice_x:.1f} cm 剖面｜"
            f"{surface_label}"
        ),
        xaxis_title="飛機橫向 Y（cm，0=中心線）",
        yaxis_title="高度 Z（cm）",
        height=560,
        showlegend=True,
    )

    if spec.position_family in {"114_SPECIAL", "96_TAIL"}:
        fig.update_xaxes(
            range=[
                -spec.surface_width / 2.0 - 10,
                spec.surface_width / 2.0 + 10,
            ]
        )
        fig.update_yaxes(range=[0, 150])
    else:
        fig.update_xaxes(range=[-255, 255])
        fig.update_yaxes(range=[0, 315])

    return fig

def load_extents(load):
    """
    顯示目前 cargo 在該 surface 中的實際使用範圍。
    """
    if not load.placements:
        return 0.0, 0.0, 0.0

    max_x = max(p.x + p.l for p in load.placements)
    min_y = None
    max_y = None
    max_z = max(p.z + p.h for p in load.placements)

    for p in load.placements:
        y0, y1 = local_to_aircraft_y(load.spec, p, side=load.side)

        if min_y is None or y0 < min_y:
            min_y = y0
        if max_y is None or y1 > max_y:
            max_y = y1

    used_width = (max_y - min_y) if min_y is not None else 0.0

    return max_x, used_width, max_z
