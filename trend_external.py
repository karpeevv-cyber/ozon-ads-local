from __future__ import annotations

import re

import requests
import streamlit as st


SUGGEST_ENDPOINT = "https://suggestqueries.google.com/complete/search"
TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
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


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_google_suggestions(
    *,
    term: str,
    hl: str = "ru",
    ds: str = "",
) -> list[str]:
    params = {
        "client": "firefox",
        "hl": hl,
        "q": _normalize_text(term),
    }
    if ds:
        params["ds"] = ds
    resp = requests.get(SUGGEST_ENDPOINT, params=params, timeout=20)
    resp.raise_for_status()
    return _parse_suggest_payload(resp.json())


@st.cache_data(show_spinner=False, ttl=3600)
def load_external_suggestion_signals(
    *,
    terms: tuple[str, ...],
    hl: str = "ru",
) -> dict[str, dict[str, list[str]]]:
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
                web_suggestions = web_suggestions
        if transliterated and transliterated != norm_term and not youtube_suggestions:
            try:
                youtube_suggestions = fetch_google_suggestions(term=transliterated, hl="en", ds="yt")
            except Exception:
                youtube_suggestions = youtube_suggestions
        if transliterated and transliterated != norm_term and not shopping_suggestions:
            try:
                shopping_suggestions = fetch_google_suggestions(term=transliterated, hl="en", ds="sh")
            except Exception:
                shopping_suggestions = shopping_suggestions
        out[norm_term] = {
            "web": web_suggestions[:8],
            "youtube": youtube_suggestions[:8],
            "shopping": shopping_suggestions[:8],
            "transliterated": [transliterated] if transliterated and transliterated != norm_term else [],
        }
    return out
