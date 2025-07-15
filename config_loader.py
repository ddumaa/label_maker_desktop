
"""Utility module for loading application configuration files."""
from __future__ import annotations

import json
from pathlib import Path


def load_settings(path: str | Path = "settings.json") -> dict:
    """Load label generation settings from JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Settings file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_db_config(path: str | Path = "db_config.json") -> dict:
    """Load database connection parameters from JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DB config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
