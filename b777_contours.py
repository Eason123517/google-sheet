"""
B777-200F 96-inch pallet upper-deck contour data.

目前已知資料：
B 至 M 位「半側」橫向位置 x 與可用高度 h（cm）。

x = 0 代表機身中央線。
x 增加代表往左/右機身外側。
左右側視為對稱。

後上艙 contour 尚未取得，因此目前只建立 B-M 區域。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContourPoint:
    x: float
    height: float


BM_HALF_CONTOUR = (
    ContourPoint(0.0, 300.0),
    ContourPoint(122.0, 300.0),
    ContourPoint(142.0, 282.0),
    ContourPoint(162.0, 264.0),
    ContourPoint(182.0, 246.0),
    ContourPoint(202.0, 228.0),
    ContourPoint(222.0, 209.0),
    ContourPoint(242.0, 190.0),
)

BM_MAX_HEIGHT_CM = 300.0
BM_MAX_HALF_WIDTH_CM = 242.0

# 後上艙資料尚未取得。
REAR_UPPER_HALF_CONTOUR = None


def max_height_at_half_width(x_cm: float) -> float | None:
    """
    回傳 B-M contour 在距中心線 x_cm 處的最大可用高度。
    兩資料點之間使用線性內插。
    超出 0~242 cm 則回傳 None。
    """
    x = float(x_cm)

    if x < 0 or x > BM_MAX_HALF_WIDTH_CM:
        return None

    points = BM_HALF_CONTOUR

    if x <= points[0].x:
        return points[0].height

    for left, right in zip(points, points[1:]):
        if left.x <= x <= right.x:
            if right.x == left.x:
                return min(left.height, right.height)

            ratio = (x - left.x) / (right.x - left.x)
            return left.height + ratio * (right.height - left.height)

    return points[-1].height


def full_symmetric_contour():
    """
    產生完整左右對稱輪廓，用於可視化。
    回傳 [(x, height), ...]。
    """
    left = [(-p.x, p.height) for p in reversed(BM_HALF_CONTOUR)]
    right = [(p.x, p.height) for p in BM_HALF_CONTOUR[1:]]
    return left + right
