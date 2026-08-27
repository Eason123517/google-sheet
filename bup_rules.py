"""
BUP grouping rules — v1.9

核心規則：
- BUP 以「貨物 ID」判斷，不以 AGT 判斷。
- 相同 ID = 同一批貨。
- 同一 ID 只要任何一列 BUP=True，該 ID 的所有貨物都視為同一 BUP 批次。
- BUP 批次可以使用 1 個或多個 ULD。
- 任何裝有該 BUP ID 貨物的 ULD，都不可再混入其他 ID 貨物。
- 未開啟 BUP 的貨物全部進一般混裝池，可以跨 AGT / ID 混裝。
- AGT 只作公司／代理資訊，不作 BUP 分組依據。
"""

from __future__ import annotations

from collections import OrderedDict


def batch_id(unit) -> str:
    """
    優先使用 unit.batch_id。
    舊資料沒有 batch_id 時，才從展開後 item_id 回推。
    """
    explicit = str(getattr(unit, "batch_id", "") or "").strip()
    if explicit:
        return explicit

    item_id = str(getattr(unit, "item_id", "") or "").strip()

    # 展開後 ID 慣例：原ID-001 / 原ID-002 ...
    head, sep, tail = item_id.rpartition("-")
    if sep and tail.isdigit():
        return head

    return item_id


def bup_enabled(unit) -> bool:
    return bool(getattr(unit, "bup", False))


def agt_name(unit) -> str:
    return str(getattr(unit, "agt", "") or "").strip()


def partition_bup_units(units):
    """
    回傳：
      [
        (cargo_id, [units...], True),  # 專用 BUP ID 批次
        ...
        ("", [normal units...], False) # 一般混裝池
      ]

    同 ID 任一 unit 開啟 BUP，該 ID 全部 unit 都進專用池。
    """
    units = list(units)

    bup_ids = {
        batch_id(u)
        for u in units
        if bup_enabled(u) and batch_id(u)
    }

    exclusive = OrderedDict()
    normal = []

    for unit in units:
        cargo_id = batch_id(unit)

        if cargo_id and cargo_id in bup_ids:
            exclusive.setdefault(cargo_id, []).append(unit)
        else:
            normal.append(unit)

    result = [
        (cargo_id, cargo_units, True)
        for cargo_id, cargo_units in exclusive.items()
    ]

    if normal:
        result.append(("", normal, False))

    return result


def bup_batch_ids(units):
    return [
        cargo_id
        for cargo_id, _, is_bup in partition_bup_units(units)
        if is_bup
    ]
