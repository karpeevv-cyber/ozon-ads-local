from __future__ import annotations

from statistics import pstdev


RUSSIAN_STOPWORDS = {
    "РґР»СЏ", "Рё", "РІ", "СЃ", "РїРѕ", "РЅР°", "РёР·", "РѕС‚", "РґРѕ", "РїРѕРґ", "РїСЂРё", "Р±РµР·",
    "С‡Р°Р№", "С‡Р°СЏ", "С‚РѕРІР°СЂ", "ozon", "РЅР°Р±РѕСЂ", "С€С‚СѓРє", "С€С‚", "Рі", "РєРі", "РјР»",
}


def clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, float(value)))


def pct_change(previous: float, current: float) -> float:
    previous = float(previous or 0.0)
    current = float(current or 0.0)
    if previous <= 0 and current <= 0:
        return 0.0
    if previous <= 0:
        return 100.0
    return (current - previous) / previous * 100.0


def split_series(values: list[float]) -> tuple[list[float], list[float]]:
    if not values:
        return [], []
    midpoint = max(1, len(values) // 2)
    return values[:midpoint], values[midpoint:]


def acceleration_score(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    midpoint = len(values) // 2
    left = values[:midpoint]
    right = values[midpoint:]
    return pct_change(sum(left), sum(right))


def stability_score(values: list[float]) -> float:
    clean = [float(v or 0.0) for v in values]
    non_zero = [v for v in clean if v > 0]
    if len(non_zero) < 3:
        return 25.0 if non_zero else 0.0
    mean_value = sum(non_zero) / len(non_zero)
    if mean_value <= 0:
        return 0.0
    volatility = pstdev(non_zero) / mean_value
    return clamp(100.0 - volatility * 100.0, 0.0, 100.0)


def confidence_score(days_with_sales: int, total_days: int, has_query_signal: bool) -> float:
    if total_days <= 0:
        return 0.0
    coverage = clamp(days_with_sales / total_days * 100.0)
    query_bonus = 15.0 if has_query_signal else 0.0
    return clamp(coverage * 0.7 + query_bonus + 15.0)


def demand_score(revenue_growth: float, units_growth: float, accel: float, stability: float, horizon: str) -> float:
    if horizon == "2-4 weeks":
        weights = (0.4, 0.2, 0.3, 0.1)
    elif horizon == "3-6 months":
        weights = (0.2, 0.2, 0.15, 0.45)
    else:
        weights = (0.3, 0.25, 0.2, 0.25)
    growth_component = clamp((revenue_growth + 100.0) / 2.0, 0.0, 100.0)
    units_component = clamp((units_growth + 100.0) / 2.0, 0.0, 100.0)
    accel_component = clamp((accel + 100.0) / 2.0, 0.0, 100.0)
    return clamp(
        growth_component * weights[0]
        + units_component * weights[1]
        + accel_component * weights[2]
        + stability * weights[3]
    )


def search_score(query_count: int, query_growth: float) -> float:
    volume_component = clamp(query_count * 8.0, 0.0, 55.0)
    growth_component = clamp((query_growth + 100.0) / 2.0, 0.0, 45.0)
    return clamp(volume_component + growth_component)


def competition_score(query_count: int, title_uniqueness: float) -> float:
    query_penalty = clamp(query_count * 6.0, 0.0, 55.0)
    uniqueness_bonus = clamp(title_uniqueness, 0.0, 45.0)
    return clamp(100.0 - query_penalty + uniqueness_bonus)


def risk_score(confidence: float, stability: float, competition: float) -> float:
    return clamp(100.0 - (confidence * 0.45 + stability * 0.25 + competition * 0.30))


def trend_score(demand: float, search: float, competition: float, confidence: float) -> float:
    return clamp(demand * 0.4 + search * 0.2 + competition * 0.2 + confidence * 0.2)


def build_product_explanation(
    *,
    revenue_growth: float,
    units_growth: float,
    accel: float,
    top_queries: list[str],
    competition: float,
) -> str:
    parts: list[str] = []
    if revenue_growth > 10:
        parts.append(f"revenue +{revenue_growth:.0f}%")
    if units_growth > 10:
        parts.append(f"units +{units_growth:.0f}%")
    if accel > 10:
        parts.append("growth accelerated in the recent half of the period")
    if competition > 60:
        parts.append("competition pressure still looks manageable")
    if top_queries:
        parts.append("query signal: " + ", ".join(top_queries[:3]))
    return "; ".join(parts) if parts else "signal is weak, requires manual validation"


def build_niche_explanation(
    *,
    product_count: int,
    avg_growth: float,
    avg_confidence: float,
    sample_titles: list[str],
) -> str:
    parts = [
        f"{product_count} product hypotheses in cluster",
        f"avg growth {avg_growth:.0f}%",
        f"confidence {avg_confidence:.0f}/100",
    ]
    if sample_titles:
        parts.append("examples: " + ", ".join(sample_titles[:2]))
    return "; ".join(parts)
