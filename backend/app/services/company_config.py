from __future__ import annotations

import json
import os
from pathlib import Path


def default_company_from_env() -> dict[str, str]:
    return {
        "perf_client_id": os.getenv("PERF_CLIENT_ID", ""),
        "perf_client_secret": os.getenv("PERF_CLIENT_SECRET", ""),
        "seller_client_id": os.getenv("SELLER_CLIENT_ID", ""),
        "seller_api_key": os.getenv("SELLER_API_KEY", ""),
    }


def _parse_company_value(value: str) -> dict[str, str]:
    raw = value.strip().strip("\"'").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        if isinstance(data, dict):
            return {str(key).strip().lower(): str(val).strip() for key, val in data.items()}
        return {}

    parts: list[str] = []
    for separator in [";", "|", ","]:
        if separator in raw:
            parts = [part for part in raw.split(separator) if part.strip()]
            break
    if not parts:
        parts = [raw]

    result: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        result[key.strip().lower()] = val.strip().strip("\"'")
    return result


def _normalize_company_fields(data: dict) -> dict[str, str]:
    mapping = {
        "perf_client_id": "perf_client_id",
        "perf_client_secret": "perf_client_secret",
        "seller_client_id": "seller_client_id",
        "seller_api_key": "seller_api_key",
        "perf_clientid": "perf_client_id",
        "perf_clientsecret": "perf_client_secret",
        "seller_clientid": "seller_client_id",
        "seller_apikey": "seller_api_key",
    }
    result = {
        "perf_client_id": "",
        "perf_client_secret": "",
        "seller_client_id": "",
        "seller_api_key": "",
    }
    for key, value in data.items():
        normalized_key = mapping.get(str(key).strip().lower())
        if normalized_key:
            result[normalized_key] = str(value).strip()
    return result


def load_company_configs(env_path: str = ".env") -> dict[str, dict[str, str]]:
    configs: dict[str, dict[str, str]] = {}
    try:
        raw = Path(env_path).read_text(encoding="utf-8")
    except Exception:
        raw = ""

    current_name = ""
    current_data: dict[str, str] = {}
    for line in raw.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.lower().startswith("company:"):
            if current_name and any(current_data.values()):
                configs[current_name] = _normalize_company_fields(current_data)
            current_name = text.split(":", 1)[1].strip()
            current_data = {}
            continue
        if current_name and "=" in text:
            key, value = text.split("=", 1)
            current_data[key.strip()] = value.strip()
    if current_name and any(current_data.values()):
        configs[current_name] = _normalize_company_fields(current_data)

    for line in raw.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if not text.lower().startswith("company"):
            continue
        key, separator, value = text.partition("=")
        if not separator:
            continue
        name = key[len("company") :].lstrip("_- .")
        name = name if name else key
        normalized = _normalize_company_fields(_parse_company_value(value))
        if any(normalized.values()):
            configs[name] = normalized

    for env_key, env_value in os.environ.items():
        key = env_key.strip()
        if not key.lower().startswith("company_"):
            continue
        rest = key[len("company_") :]
        if "_" not in rest:
            continue
        name, _, field = rest.partition("_")
        normalized = _normalize_company_fields({field.lower(): env_value})
        if name:
            current = configs.get(
                name,
                {
                    "perf_client_id": "",
                    "perf_client_secret": "",
                    "seller_client_id": "",
                    "seller_api_key": "",
                },
            )
            for field_key, field_value in normalized.items():
                if field_value:
                    current[field_key] = field_value
            configs[name] = current

    return configs


def resolve_company_config(name: str | None, env_path: str = ".env") -> tuple[str, dict[str, str]]:
    configs = load_company_configs(env_path=env_path)
    if not configs:
        return ("default", default_company_from_env())

    if name and name in configs:
        return (name, configs[name])

    first_name = sorted(configs.keys())[0]
    return (first_name, configs[first_name])
