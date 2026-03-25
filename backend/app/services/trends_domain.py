from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import re

import pandas as pd

from app.services.trends_external import load_external_suggestion_signals
from app.services.trends_scoring import (
    RUSSIAN_STOPWORDS,
    acceleration_score,
    build_niche_explanation,
    build_product_explanation,
    competition_score,
    confidence_score,
    demand_score,
    pct_change,
    risk_score,
    search_score,
    split_series,
    stability_score,
    trend_score,
)
from app.services.trends_sources import build_date_span, load_catalog, load_query_signals, load_sales_history


QUERY_NOISE_TOKENS = {
    "buy", "benefits", "recipe", "youtube", "ozon", "wb", "wildberries", "price",
    "how", "near", "starbucks", "set", "shop", "kupit", "tsena", "otzyvy",
    "РєСѓРїРёС‚СЊ", "С†РµРЅР°", "С†РµРЅС‹", "РѕС‚Р·С‹РІС‹", "СЋС‚СѓР±", "РІР°Р№Р»РґР±РµСЂСЂРёР·", "РѕР·РѕРЅ", "РїРѕР»СЊР·Р°",
    "РІСЂРµРґ", "СЂРµС†РµРїС‚", "РїРѕС…СѓРґРµРЅРёСЏ", "СЃРІРѕРёРјРё", "СЂСѓРєР°РјРё", "РґР»СЏ",
}


def _safe_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _title_tokens(title: str) -> list[str]:
    raw = re.findall(r"[0-9A-Za-z\u0401\u0451\u0410-\u044f]+", _safe_text(title).lower())
    return [token for token in raw if token not in RUSSIAN_STOPWORDS and len(token) > 2]


def _normalize_niche_tokens(tokens: list[str]) -> list[str]:
    normalized: list[str] = []
    for token in tokens:
        token = str(token or "").strip().lower()
        if not token or token in QUERY_NOISE_TOKENS:
            continue
        if token.endswith(("Р°РјРё", "СЏРјРё")) and len(token) > 5:
            token = token[:-3]
        elif token.endswith(("РѕРІ", "РµРІ", "РѕРј", "РµРј", "Р°С…", "СЏС…", "С‹Р№", "Р°СЏ", "РѕРµ", "РёРµ", "РёР№")) and len(token) > 4:
            token = token[:-2]
        elif token.endswith(("С‹", "Рё", "Р°", "СЏ")) and len(token) > 4:
            token = token[:-1]
        if token and token not in QUERY_NOISE_TOKENS:
            normalized.append(token)
    return normalized


def _canonical_niche_name(tokens: list[str]) -> str:
    normalized = _normalize_niche_tokens(tokens)
    if not normalized:
        return "misc"
    return " ".join(normalized[:2])


def _derive_niche_key(title: str, query_rows: list[dict]) -> str:
    if query_rows:
        query_tokens = _title_tokens(str(query_rows[0].get("query", "")))
        if query_tokens:
            return _canonical_niche_name(query_tokens)
    return _canonical_niche_name(_title_tokens(title))


def _title_uniqueness(title: str) -> float:
    tokens = _title_tokens(title)
    if not tokens:
        return 0.0
    unique_ratio = len(set(tokens)) / len(tokens)
    return unique_ratio * 45.0


def _seed_term(title: str, top_queries: list[str]) -> str:
    if top_queries:
        return _safe_text(top_queries[0])
    tokens = _title_tokens(title)
    if not tokens:
        return _safe_text(title)
    return " ".join(tokens[:2])


def _clean_phrase_list(items: list[str], *, seed_term: str = "") -> list[str]:
    seed_norm = _safe_text(seed_term).lower()
    ranked = sorted(
        [_safe_text(item) for item in items],
        key=lambda text: (
            len(_normalize_niche_tokens(_title_tokens(text))),
            len(text),
        ),
        reverse=True,
    )
    cleaned: list[str] = []
    seen: set[str] = set()
    for text in ranked:
        if not text:
            continue
        key = " ".join(_normalize_niche_tokens(_title_tokens(text)))
        if not key or key in seen:
            continue
        if seed_norm and text.lower() == seed_norm and len(key.split()) < 2:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _clean_query_rows(rows: list[dict]) -> list[dict]:
    ranked = sorted(
        rows,
        key=lambda row: (
            len(_normalize_niche_tokens(_title_tokens(str(row.get("query", ""))))),
            float(row.get("growth", 0.0) or 0.0),
            float(row.get("searches", 0.0) or 0.0),
        ),
        reverse=True,
    )
    out: list[dict] = []
    seen: set[str] = set()
    for row in ranked:
        query = _safe_text(row.get("query", ""))
        key = " ".join(_normalize_niche_tokens(_title_tokens(query)))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "query": query,
                "searches": float(row.get("searches", 0.0) or 0.0),
                "growth": float(row.get("growth", 0.0) or 0.0),
                "revenue": float(row.get("revenue", 0.0) or 0.0),
            }
        )
    return out


def _collect_history(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    daily = df.groupby("day", as_index=False)[["revenue", "ordered_units"]].sum().sort_values("day")
    out: list[dict] = []
    for _, row in daily.iterrows():
        out.append(
            {
                "day": row["day"].date().isoformat(),
                "revenue": float(row["revenue"] or 0.0),
                "ordered_units": int(row["ordered_units"] or 0),
            }
        )
    return out


def _pick_best_niche_label(members: list[dict], fallback: str) -> str:
    candidate_phrases: Counter[str] = Counter()
    for item in members:
        for query in item.get("related_queries", [])[:3]:
            text = _safe_text(query.get("query", ""))
            key = " ".join(_normalize_niche_tokens(_title_tokens(text)))
            if key:
                candidate_phrases[text] += 3
        title = _safe_text(item.get("title", ""))
        title_tokens = _normalize_niche_tokens(_title_tokens(title))
        if title_tokens:
            candidate_phrases[" ".join(title_tokens[:2]).title()] += 1
    if candidate_phrases:
        return candidate_phrases.most_common(1)[0][0]
    if fallback and fallback != "misc":
        return fallback.title()
    return "Miscellaneous cluster"


def _build_reason_tags(
    *,
    revenue_growth: float,
    units_growth: float,
    avg_query_growth: float,
    confidence: float,
    risk: float,
    external_count: int,
) -> list[str]:
    tags: list[str] = []
    if revenue_growth > 15:
        tags.append("revenue_up")
    if units_growth > 15:
        tags.append("units_up")
    if avg_query_growth > 10:
        tags.append("query_up")
    if external_count >= 5:
        tags.append("external_buzz")
    if confidence >= 65:
        tags.append("high_conf")
    if risk <= 40:
        tags.append("lower_risk")
    return tags[:4]


def build_trend_snapshot(
    *,
    date_from: date,
    date_to: date,
    seller_client_id: str | None,
    seller_api_key: str | None,
    horizon: str,
    company_name: str | None = None,
    search_filter: str = "",
) -> dict:
    sales_df = load_sales_history(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    catalog_df = load_catalog(
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )
    total_days = build_date_span(date_from, date_to)

    if sales_df.empty:
        return {
            "niches": [],
            "products": [],
            "external_sources": _external_source_status(),
            "errors": ["No seller sales data for the selected period."],
            "meta": {"company_name": company_name or "", "horizon": horizon, "period_days": total_days},
        }

    merged = sales_df.merge(catalog_df, on="sku", how="left")
    merged["title"] = merged["title"].fillna(merged["sku"])
    product_totals = (
        merged.groupby(["sku", "title"], as_index=False)[["revenue", "ordered_units"]]
        .sum()
        .sort_values(["revenue", "ordered_units"], ascending=False)
    )
    top_skus = tuple(product_totals.head(40)["sku"].astype(str).tolist())
    query_df = load_query_signals(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        skus=top_skus,
        seller_client_id=seller_client_id,
        seller_api_key=seller_api_key,
    )

    query_by_sku: dict[str, list[dict]] = defaultdict(list)
    if not query_df.empty:
        for _, row in query_df.sort_values(["sku", "searches"], ascending=[True, False]).iterrows():
            query_by_sku[str(row["sku"])].append(
                {
                    "query": _safe_text(row["query"]),
                    "searches": float(row["searches"] or 0.0),
                    "growth": float(row["growth"] or 0.0),
                    "revenue": float(row["revenue"] or 0.0),
                }
            )
    for sku, rows in list(query_by_sku.items()):
        query_by_sku[sku] = _clean_query_rows(rows)[:5]

    external_terms: list[str] = []
    for _, prod in product_totals.head(12).iterrows():
        sku = str(prod["sku"])
        title = _safe_text(prod["title"])
        query_rows = query_by_sku.get(sku, [])
        top_queries = [str(item["query"]) for item in query_rows[:2]]
        seed = _seed_term(title, top_queries)
        if seed:
            external_terms.append(seed)
    external_signal_map = load_external_suggestion_signals(terms=tuple(dict.fromkeys(external_terms)))

    products: list[dict] = []
    niche_buckets: dict[str, list[dict]] = defaultdict(list)
    search_filter_norm = _safe_text(search_filter).lower()

    for _, prod in product_totals.iterrows():
        sku = str(prod["sku"])
        title = _safe_text(prod["title"])
        if search_filter_norm and search_filter_norm not in title.lower():
            continue
        product_days = merged[merged["sku"] == sku].sort_values("day")
        revenue_series = [float(v or 0.0) for v in product_days["revenue"].tolist()]
        units_series = [float(v or 0.0) for v in product_days["ordered_units"].tolist()]
        revenue_prev, revenue_recent = split_series(revenue_series)
        units_prev, units_recent = split_series(units_series)
        revenue_growth = pct_change(sum(revenue_prev), sum(revenue_recent))
        units_growth = pct_change(sum(units_prev), sum(units_recent))
        accel = acceleration_score(revenue_series)
        stability = stability_score(revenue_series)

        query_rows = query_by_sku.get(sku, [])
        query_count = len(query_rows)
        avg_query_growth = (
            sum(float(item["growth"]) for item in query_rows) / query_count if query_count else 0.0
        )
        top_queries = [str(item["query"]) for item in query_rows[:3]]
        niche_id = _derive_niche_key(title, query_rows)
        seed_term = _seed_term(title, top_queries)
        external_entry = external_signal_map.get(seed_term, {})
        web_suggestions = _clean_phrase_list(external_entry.get("web", []), seed_term=seed_term)
        youtube_suggestions = _clean_phrase_list(external_entry.get("youtube", []), seed_term=seed_term)
        shopping_suggestions = _clean_phrase_list(external_entry.get("shopping", []), seed_term=seed_term)
        transliterated_seed = (external_entry.get("transliterated", []) or [""])[0]
        external_count = len(web_suggestions) + len(youtube_suggestions) + len(shopping_suggestions)

        confidence = confidence_score(product_days["day"].nunique(), total_days, bool(query_rows))
        demand = demand_score(revenue_growth, units_growth, accel, stability, horizon)
        search = search_score(query_count + external_count, avg_query_growth)
        competition = competition_score(query_count + max(0, len(shopping_suggestions) - 1), _title_uniqueness(title))
        risk = risk_score(confidence, stability, competition)
        score = trend_score(demand, search, competition, confidence)
        reason_tags = _build_reason_tags(
            revenue_growth=revenue_growth,
            units_growth=units_growth,
            avg_query_growth=avg_query_growth,
            confidence=confidence,
            risk=risk,
            external_count=external_count,
        )

        candidate = {
            "id": sku,
            "title": title,
            "niche_id": niche_id,
            "price_band": "unknown",
            "horizon": horizon,
            "trend_score": round(score, 1),
            "competition_score": round(competition, 1),
            "confidence_score": round(confidence, 1),
            "risk_score": round(risk, 1),
            "demand_signal": round(demand, 1),
            "search_signal": round(search, 1),
            "reason_tags": ", ".join(reason_tags),
            "revenue": round(float(prod["revenue"] or 0.0), 1),
            "ordered_units": int(prod["ordered_units"] or 0),
            "explanation": build_product_explanation(
                revenue_growth=revenue_growth,
                units_growth=units_growth,
                accel=accel,
                top_queries=top_queries,
                competition=competition,
            ),
            "validation_checks": _build_validation_checks(query_rows, confidence, risk),
            "history_points": _collect_history(product_days[["day", "revenue", "ordered_units"]].copy()),
            "drivers": _build_drivers(
                revenue_growth,
                units_growth,
                avg_query_growth,
                query_rows,
                web_suggestions,
                youtube_suggestions,
                shopping_suggestions,
            ),
            "risks": _build_risks(risk, confidence, query_rows),
            "related_queries": query_rows[:5],
            "external_signals": {
                "seed_term": seed_term,
                "transliterated_seed": transliterated_seed,
                "web_suggestions": web_suggestions,
                "youtube_suggestions": youtube_suggestions,
                "shopping_suggestions": shopping_suggestions,
            },
            "summary": f"{title}: trend {score:.0f}, confidence {confidence:.0f}, risk {risk:.0f}",
        }
        products.append(candidate)
        niche_buckets[niche_id].append(candidate)

    products.sort(key=lambda item: (item["trend_score"], item["confidence_score"], item["revenue"]), reverse=True)
    products = products[:30]

    niches: list[dict] = []
    for niche_id, members in niche_buckets.items():
        if not members:
            continue
        members = sorted(members, key=lambda item: item["trend_score"], reverse=True)
        avg_trend = sum(item["trend_score"] for item in members) / len(members)
        avg_conf = sum(item["confidence_score"] for item in members) / len(members)
        avg_comp = sum(item["competition_score"] for item in members) / len(members)
        avg_risk = sum(item["risk_score"] for item in members) / len(members)
        avg_demand = sum(item["demand_signal"] for item in members) / len(members)
        titles = [item["title"] for item in members[:3]]
        title_tokens = Counter()
        for title in titles:
            title_tokens.update(_normalize_niche_tokens(_title_tokens(title)))
        title = niche_id if niche_id != "misc" else "Miscellaneous cluster"
        if title_tokens:
            title = " ".join([token for token, _ in title_tokens.most_common(2)]) or title
        niches.append(
            {
                "id": niche_id,
                "title": _pick_best_niche_label(members, title),
                "category": "Derived from current assortment",
                "horizon": horizon,
                "trend_score": round(avg_trend, 1),
                "competition_score": round(avg_comp, 1),
                "confidence_score": round(avg_conf, 1),
                "risk_score": round(avg_risk, 1),
                "demand_signal": round(avg_demand, 1),
                "seasonality_signal": 50.0,
                "reason_tags": ", ".join(_merge_reason_tags(members)),
                "products_count": len(members),
                "top_product_revenue": round(max(float(item.get("revenue", 0.0) or 0.0) for item in members), 1),
                "niche_rank_score": round(avg_trend + min(len(members) * 3.0, 18.0) + avg_conf * 0.08, 1),
                "explanation": build_niche_explanation(
                    product_count=len(members),
                    avg_growth=avg_demand,
                    avg_confidence=avg_conf,
                    sample_titles=titles,
                ),
                "example_products": [item["title"] for item in members[:3]],
                "drivers": _merge_member_lists(members, "drivers"),
                "risks": _merge_member_lists(members, "risks"),
                "related_products": [item["title"] for item in members[:5]],
                "summary": f"{title}: {len(members)} product hypotheses, trend {avg_trend:.0f}",
            }
        )

    niches.sort(key=lambda item: (item["trend_score"], item["confidence_score"]), reverse=True)
    niches = niches[:15]

    return {
        "niches": niches,
        "products": products,
        "external_sources": _external_source_status(),
        "errors": [],
        "meta": {
            "company_name": company_name or "",
            "horizon": horizon,
            "period_days": total_days,
            "products_scanned": len(product_totals),
            "query_signal_products": len(query_by_sku),
            "external_seed_terms": len(dict.fromkeys(external_terms)),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
    }


def _build_validation_checks(query_rows: list[dict], confidence: float, risk: float) -> list[str]:
    checks = [
        "Check real category saturation manually before launch.",
        "Validate unit economics and logistics separately.",
    ]
    if not query_rows:
        checks.append("No query signal found in current data window.")
    if confidence < 45:
        checks.append("Confidence is low because the sales history is sparse.")
    if risk > 55:
        checks.append("Risk is elevated; verify whether growth is only a short spike.")
    return checks[:4]


def _build_drivers(
    revenue_growth: float,
    units_growth: float,
    avg_query_growth: float,
    query_rows: list[dict],
    web_suggestions: list[str],
    youtube_suggestions: list[str],
    shopping_suggestions: list[str],
) -> list[str]:
    drivers: list[str] = []
    if revenue_growth > 0:
        drivers.append(f"Revenue trend improved by {revenue_growth:.0f}%")
    if units_growth > 0:
        drivers.append(f"Unit sales improved by {units_growth:.0f}%")
    if avg_query_growth > 0:
        drivers.append(f"Search demand improved by {avg_query_growth:.0f}%")
    if query_rows:
        drivers.append("Query coverage exists for this product")
    if web_suggestions:
        drivers.append(f"External web suggestions: {len(web_suggestions)}")
    if youtube_suggestions:
        drivers.append(f"YouTube/content suggestions: {len(youtube_suggestions)}")
    if shopping_suggestions:
        drivers.append(f"Shopping intent suggestions: {len(shopping_suggestions)}")
    return drivers[:4] or ["No strong positive drivers detected yet"]


def _build_risks(risk: float, confidence: float, query_rows: list[dict]) -> list[str]:
    risks: list[str] = []
    if risk > 60:
        risks.append("Overall trend quality is fragile for this product")
    if confidence < 50:
        risks.append("Sales history coverage is limited")
    if not query_rows:
        risks.append("No supporting query signal found")
    return risks[:4] or ["No major risk flag from the current dataset"]


def _merge_member_lists(items: list[dict], key: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        for value in item.get(key, []):
            if value not in seen:
                seen.add(value)
                out.append(value)
    return out[:5]


def _merge_reason_tags(items: list[dict]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        for value in str(item.get("reason_tags", "") or "").split(","):
            tag = value.strip()
            if tag and tag not in seen:
                seen.add(tag)
                out.append(tag)
    return out[:4]


def _external_source_status() -> list[dict]:
    return [
        {"source": "Google web suggestions", "status": "active"},
        {"source": "YouTube suggestions", "status": "active"},
        {"source": "Google shopping suggestions", "status": "active"},
    ]
