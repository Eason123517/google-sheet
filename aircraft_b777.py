"""
B777-200F 全貨機設定。

v1.5：
B-M 上艙改為「ULD 尺寸 + cargo 3D packing + aircraft contour」共同計算。

不是把 cargo 只分成 side / center：
- cargo 在 ULD / loading surface 內可有不同 X/Y/Z。
- 每個 Y 位置都重新查 contour 高度。
- CENTER 只是代表該 loading surface 跨左右兩側，cargo 本身可偏左、偏右或置中。
"""

from aircraft_base import AircraftProfile


PROFILE = AircraftProfile(
    code="B777",
    display_name="B777 全貨機",
    aircraft_type="全貨機",
    status_text="B-M ULD 輪廓 3D 測試",
    description=(
        "B777-200F B~M 上艙目前使用 ULD 長／寬／最大高度，"
        "並依貨物在 ULD 內的實際橫向位置套用 aircraft contour。"
    ),
    allow_packing=True,
    module_file="aircraft_b777.py",
    notes=(
        "不同 ULD 的長、寬、高、最大載重會先限制 packing surface。",
        "B-M contour 再依每件貨物實際 Y 位置限制可用高度。",
        "單側 surface 與中央裝載 surface 都允許貨物在 surface 內自由排列。",
        "支援 3D cargo loading view。",
        "後上艙、下腹艙、CG、position weight、floor loading 等仍待後續資料。",
    ),
)


def validate_loading(items, units, ulds):
    return []
