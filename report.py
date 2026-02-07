import csv


def parse_money(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def fmt_num(x):
    """
    Формат для CSV под RU Google Sheets, БЕЗ дробной части:
    1234.56 -> '1235'
    '1792,83' -> '1793'
    None -> ''
    """
    if x is None:
        return ""
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        return str(int(round(x)))
    s = str(x).strip()
    if not s:
        return ""
    try:
        val = float(s.replace(" ", "").replace(",", "."))
        return str(int(round(val)))
    except Exception:
        return s


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def campaign_display_fields(camp_title: str, items: list[dict]):
    skus = [str(x.get("sku")) for x in items if x.get("sku") is not None]

    if len(skus) == 0:
        return "—", camp_title, None, skus

    if len(skus) == 1:
        one = items[0]
        out_sku = skus[0]
        out_title = one.get("title", "") or camp_title

        bid_raw = one.get("bid")
        try:
            bid_value = int(bid_raw) / 1_000_000
        except Exception:
            bid_value = None

        return out_sku, out_title, bid_value, skus

    return "several", "several", None, skus


def build_report_rows(
    running_campaigns: list[dict],
    stats_by_campaign_id: dict,
    sales_map: dict,
    products_by_campaign_id: dict,
):
    rows_csv = []

    gt_money_spent = 0.0
    gt_views = 0
    gt_clicks = 0
    gt_to_cart = 0
    gt_orders = 0
    gt_orders_money = 0.0
    gt_revenue = 0.0
    gt_units = 0

    for c in running_campaigns:
        cid = str(c["id"])
        camp_title = c.get("title", "")

        items = products_by_campaign_id.get(cid, [])
        out_sku, out_title, out_bid, skus = campaign_display_fields(camp_title, items)

        sr = stats_by_campaign_id.get(cid, {})
        money_spent = parse_money(sr.get("moneySpent"))
        views = int(parse_money(sr.get("views")))
        clicks = int(parse_money(sr.get("clicks")))
        click_price = parse_money(sr.get("clickPrice"))
        to_cart = int(parse_money(sr.get("toCart")))
        orders = int(parse_money(sr.get("orders")))
        orders_money = parse_money(sr.get("ordersMoney"))

        # CTR считаем САМИ
        total_revenue = 0.0
        total_units = 0
        for sku in skus:
            rv, un = sales_map.get(sku, (0.0, 0))
            total_revenue += rv
            total_units += un
        ctr_pct = (clicks / views * 100.0) if views > 0 else 0.0
        cr_pct = (total_units / clicks * 100.0) if clicks > 0 else 0.0
        vor_pct = (total_units / views * 100.0) if views > 0 else 0.0

        vpo = (views / total_units) if total_units > 0 else 0.0

        total_drr_pct = (money_spent / total_revenue * 100.0) if total_revenue > 0 else 0.0

        # Grand total accumulators
        gt_money_spent += money_spent
        gt_views += views
        gt_clicks += clicks
        gt_to_cart += to_cart
        gt_orders += orders
        gt_orders_money += orders_money
        gt_revenue += total_revenue
        gt_units += total_units

        rows_csv.append(
            {
                "campaign_id": cid,
                "sku": out_sku,
                "title": out_title,
                "money_spent": fmt_num(money_spent),
                "views": fmt_num(views),
                "clicks": fmt_num(clicks),
                "click_price": fmt_num(click_price),
                "orders_money_ads": fmt_num(orders_money),
                "total_revenue": fmt_num(total_revenue),
                "ordered_units": fmt_num(total_units),
                "total_drr_pct": fmt_num(round(total_drr_pct, 2)),
                "ctr": round(ctr_pct, 1),
                "cr": round(cr_pct, 1),
                "vor": round(vor_pct, 1),
                "vpo": round(vpo, 1),
            }
        )

    # GRAND TOTAL
    gt_click_price = (gt_money_spent / gt_clicks) if gt_clicks > 0 else 0.0
    gt_drr_pct = (gt_money_spent / gt_revenue * 100.0) if gt_revenue > 0 else 0.0
    gt_ctr = (gt_clicks / gt_views * 100.0) if gt_views > 0 else 0.0
    gt_cr = (gt_units / gt_clicks * 100.0) if gt_clicks > 0 else 0.0
    gt_vor = (gt_units / gt_views * 100.0) if gt_views > 0 else 0.0
    gt_vpo = (gt_views / gt_units) if gt_units > 0 else 0.0

    grand_total = {
        "campaign_id": "GRAND_TOTAL",
        "sku": "",
        "title": "",
        "money_spent": fmt_num(gt_money_spent),
        "views": fmt_num(gt_views),
        "clicks": fmt_num(gt_clicks),
        "click_price": fmt_num(round(gt_click_price, 2)),
        "orders_money_ads": fmt_num(gt_orders_money),
        "total_revenue": fmt_num(gt_revenue),
        "ordered_units": fmt_num(gt_units),
        "total_drr_pct": fmt_num(round(gt_drr_pct, 2)),
        "ctr": round(gt_ctr, 1),
        "cr": round(gt_cr, 1),
        "vor": round(gt_vor, 1),
        "vpo": round(gt_vpo, 1),
    }

    rows_csv.append(grand_total)
    return rows_csv, grand_total


def write_csv(rows_csv: list[dict], csv_path: str):
    if not rows_csv:
        raise RuntimeError("rows_csv пустой — нечего писать в CSV")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_csv[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows_csv)
