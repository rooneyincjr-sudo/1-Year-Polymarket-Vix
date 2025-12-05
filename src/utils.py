"""Shared utilities for the MUI pipeline."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from . import config


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger with stream handler."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def ensure_directories(paths: Iterable[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def to_unix_ts(dt: datetime) -> int:
    return int(dt.timestamp())


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    ensure_directories([path.parent])
    df.to_csv(path)


LOGGER = get_logger("mui")

