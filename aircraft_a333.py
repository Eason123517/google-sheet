"""
A333 客機測試設定。

未來 A333 的專屬規則集中放在這個檔案。
目前只使用一般 ULD 長/寬/高、最大載重與既有 3D Packing Engine。
"""

from aircraft_base import AircraftProfile


PROFILE = AircraftProfile(
    code="A333",
    display_name="A333 客機",
    aircraft_type="客機",
    status_text="A333 測試中",
    description=(
        "目前先以 A333 客機進行系統測試。"
        "本階段由 ULD 資料中的長、寬、高與最大載重限制裝載。"
    ),
    allow_packing=True,
    module_file="aircraft_a333.py",
    notes=(
        "目前使用通用 3D ULD 排列演算法。",
        "ULD 相容性由 ULD／箱子管理中的「適用機型」控制。",
        "尚未加入 A333 艙門、貨艙輪廓、位置、重心等專屬限制。",
    ),
)


def validate_loading(items, units, ulds):
    # A333 專屬規則擴充入口。
    return []
