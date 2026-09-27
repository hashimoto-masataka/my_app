# -*- coding: utf-8 -*-
"""注文の株数の決め方。上限金額（config.BUDGET_PER_ORDER）に収まる最大の単元数。

高額銘柄で発注額が膨らまないための仕組み。1単元が上限金額を超える銘柄は 0 株（＝見送り）になる。
"""
import config


def lot_size(code: str) -> int:
    return int(config.LOT_SIZES.get(code, config.LOT_SIZE))


def order_qty(code: str, price: float) -> int:
    """price（直近の終値など、1株の目安）で、上限金額に収まる株数。買えないなら 0。"""
    budget = getattr(config, "BUDGET_PER_ORDER", None)
    if budget is None:
        return int(config.QTY)              # 従来どおりの固定株数
    lot = lot_size(code)
    if not price or price <= 0 or lot <= 0:
        return 0
    return int(budget // (price * lot)) * lot
