"""
Cargo metrics shared by A333 / B777.

C.F. 計算：
每件貨物 長 × 寬 × 高 × 件數 / 6000 / 4.72

Packing engine 內的 placements 已經展開為單件，
所以每個 placement 的件數視為 1，再將同 ULD 內所有貨物加總。
"""


def calculate_cf(placements) -> float:
    total = 0.0

    for p in placements:
        total += (
            float(p.l)
            * float(p.w)
            * float(p.h)
            / 6000.0
            / 4.72
        )

    return total
