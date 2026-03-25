from __future__ import annotations

from functools import lru_cache
import re

import requests


SUGGEST_ENDPOINT = "https://suggestqueries.google.com/complete/search"
TRANSLIT_MAP = {
    "Р°": "a", "Р±": "b", "РІ": "v", "Рі": "g", "Рґ": "d", "Рµ": "e", "С‘": "e",
    "Р¶": "zh", "Р·": "z", "Рё": "i", "Р№": "y", "Рє": "k", "Р»": "l", "Рј": "m",
    "РЅ": "n", "Рѕ": "o", "Рї": "p", "СЂ": "r", "СЃ": "s", "С‚": "t", "Сѓ": "u",
    "С„": "f", "С…": "h", "С†": "ts", "С‡": "ch", "С€": "sh", "С‰": "sch", "СЉ": "",
    "С‹": "y", "СЊ": "", "СЌ": "e", "СЋ": "yu", "СЏ": "ya",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _parse_suggest_payload(payload) -> list[str]:
    if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
        return [_normalize_text(item) for item in payload[1] if _normalize_text(item)]
    return []


def _transliterate(value: str) -> str:
    out: list[str] = []
    for ch in _normalize_text(value).lower():
        out.append(TRANSLIT_MAP.get(ch, ch))
    return "".join(out)


@lru_cache(maxsize=256)
def _fetch_google_suggestions(term: str, hl: str, ds: str) -> tuple[str, ...]:
    params = {"client": "firefox", "hl": hl, "q": _normalize_text(term)}
    if ds:
        params["ds"] = ds
    resp = requests.get(SUGGEST_ENDPOINT, params=params, timeout=20)
    resp.raise_for_status()
    return tuple(_parse_suggest_payload(resp.json()))


def fetch_google_suggestions(*, term: str, hl: str = "ru", ds: str = "") -> list[str]:
    return list(_fetch_google_suggestions(_normalize_text(term), hl, ds))


@lru_cache(maxsize=64)
def _load_external_suggestion_signals_cached(terms: tuple[str, ...], hl: str) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for term in terms:
        norm_term = _normalize_text(term)
        if not norm_term:
            continue
        try:
            web_suggestions = fetch_google_suggestions(term=norm_term, hl=hl, ds="")
        except Exception:
            web_suggestions = []
        try:
            youtube_suggestions = fetch_google_suggestions(term=norm_term, hl=hl, ds="yt")
        except Exception:
            youtube_suggestions = []
        try:
            shopping_suggestions = fetch_google_suggestions(term=norm_term, hl=hl, ds="sh")
        except Exception:
            shopping_suggestions = []
        transliterated = _transliterate(norm_term)
        if transliterated and transliterated != norm_term and not web_suggestions:
            try:
                web_suggestions = fetch_google_suggestions(term=transliterated, hl="en", ds="")
            except Exception:
                pass
        if transliterated and transliterated != norm_term and not youtube_suggestions:
            try:
                youtube_suggestions = fetch_google_suggestions(term=transliterated, hl="en", ds="yt")
            except Exception:
                pass
        if transliterated and transliterated != norm_term and not shopping_suggestions:
            try:
                shopping_suggestions = fetch_google_suggestions(term=transliterated, hl="en", ds="sh")
            except Exception:
                pass
        out[norm_term] = {
            "web": web_suggestions[:8],
            "youtube": youtube_suggestions[:8],
            "shopping": shopping_suggestions[:8],
            "transliterated": [transliterated] if transliterated and transliterated != norm_term else [],
        }
    return out


def load_external_suggestion_signals(
    *,
    terms: tuple[str, ...],
    hl: str = "ru",
) -> dict[str, dict[str, list[str]]]:
    normalized_terms = tuple(term for term in (_normalize_text(item) for item in terms) if term)
    return _load_external_suggestion_signals_cached(normalized_terms, hl)
