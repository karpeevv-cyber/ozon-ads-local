from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
BACKEND_DATA_DIR = BACKEND_ROOT / "data"


def ensure_backend_data_dir() -> Path:
    BACKEND_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return BACKEND_DATA_DIR


def backend_data_path(filename: str) -> Path:
    return ensure_backend_data_dir() / filename


def legacy_root_path(filename: str) -> Path:
    return REPO_ROOT / filename
