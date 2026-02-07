# -*- coding: utf-8 -*-
from __future__ import annotations

import streamlit as st


def render_tab4() -> None:
    st.subheader("Формулы расчета метрик")
    st.markdown(
        """
**Ads-метрики**
- `CTR = clicks / views * 100`
- `CPC (click_price) = money_spent / clicks`
- `CPM = money_spent / views * 1000`
- `CR = ordered_units / clicks * 100`
- `VOR = ordered_units / views * 100`
- `VPO = views / ordered_units`
- `DRR% (total_drr_pct) = money_spent / total_revenue * 100`
- `RPC = total_revenue / clicks`
- `target_CPC = RPC * target_drr`
- `recommended_bid = min(CPC econ, Bid floor, CPC econ max)`

**Стратегия 1 (DRR)**
- `order_value = revenue_long / orders_long`
- `CR_long = orders_long / clicks_long`
- `drr_min = max(0, target_drr - drr_abs_tolerance)`
- `drr_max = min(1, target_drr + drr_abs_tolerance)`
- `CPC econ = order_value * CR_long * target_drr`
- `CPC econ min = order_value * CR_long * drr_min`
- `CPC econ max = order_value * CR_long * drr_max`

**Seller-метрики**
- `ordered_units` — суммарные продажи (units) по SKU
- `total_revenue` — суммарная выручка по SKU

**Примечания**
- Если знаменатель равен 0, метрика считается 0.0.
"""
    )
