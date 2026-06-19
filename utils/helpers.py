"""Shared helper functions used across InsightAI modules.

Includes data loading, column-type introspection, semantic column detection
(useful for KPI / dashboard heuristics), and small UI helpers.
"""
from __future__ import annotations

import io
from typing import Iterable

import numpy as np
import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)

# Keywords used to heuristically map columns to business concepts.
_SEMANTIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "sales_amount", "amount", "total", "turnover", "gmv"),
    "profit": ("profit", "margin", "net_income", "earnings"),
    "sales": ("sales", "quantity", "units", "qty", "volume"),
    "customer": ("customer", "client", "user", "account", "buyer"),
    "date": ("date", "time", "timestamp", "day", "month", "year", "period"),
    "category": ("category", "segment", "type", "product", "class", "group"),
    "region": ("region", "country", "state", "city", "location", "territory", "zone"),
    "price": ("price", "cost", "rate", "unit_price"),
}


def load_dataframe(uploaded_file) -> pd.DataFrame:
    """Read a Streamlit ``UploadedFile`` (CSV or Excel) into a DataFrame.

    Args:
        uploaded_file: Streamlit uploaded file object with ``name`` and bytes.

    Returns:
        Parsed :class:`pandas.DataFrame`.

    Raises:
        ValueError: If the file extension is unsupported or parsing fails.
    """
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            # Robust CSV read: fall back to python engine + latin-1 if needed.
            raw = uploaded_file.getvalue()
            try:
                df = pd.read_csv(io.BytesIO(raw))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(raw), encoding="latin-1")
        elif name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file, engine="openpyxl")
        else:
            raise ValueError(f"Unsupported file type: {uploaded_file.name}")
    except Exception as exc:  # noqa: BLE001 - surface a clean message to UI
        logger.exception("Failed to read uploaded file %s", uploaded_file.name)
        raise ValueError(f"Could not read file: {exc}") from exc

    df = _normalise_columns(df)
    logger.info("Loaded dataframe shape=%s from %s", df.shape, uploaded_file.name)
    return df


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from column names and de-duplicate them."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    # Attempt to coerce object columns that look like dates.
    for col in df.select_dtypes(include="object").columns:
        if _looks_like_date(col):
            df[col] = pd.to_datetime(df[col], errors="ignore")
    return df


def _looks_like_date(col_name: str) -> bool:
    name = col_name.lower()
    return any(k in name for k in _SEMANTIC_KEYWORDS["date"])


def numeric_columns(df: pd.DataFrame) -> list[str]:
    """Return numeric column names."""
    return df.select_dtypes(include=np.number).columns.tolist()


def categorical_columns(df: pd.DataFrame, max_unique: int = 50) -> list[str]:
    """Return low-cardinality object/categorical columns suitable for grouping."""
    cols: list[str] = []
    for col in df.select_dtypes(include=["object", "category"]).columns:
        if df[col].nunique(dropna=True) <= max_unique:
            cols.append(col)
    return cols


def datetime_columns(df: pd.DataFrame) -> list[str]:
    """Return datetime-typed column names."""
    return df.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()


def detect_semantic_column(df: pd.DataFrame, concept: str) -> str | None:
    """Best-effort mapping of a business concept to an actual column name.

    Args:
        df: Source dataframe.
        concept: One of the keys in :data:`_SEMANTIC_KEYWORDS`.

    Returns:
        The matching column name, or ``None`` if nothing matches.
    """
    keywords = _SEMANTIC_KEYWORDS.get(concept, ())
    for col in df.columns:
        lowered = col.lower().replace(" ", "_")
        if any(k in lowered for k in keywords):
            return col
    return None


def human_readable_size(num_bytes: int) -> str:
    """Convert a byte count to a human readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} GB"


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division guarding against zero denominators."""
    return numerator / denominator if denominator else default


def coerce_numeric(series: pd.Series) -> pd.Series:
    """Attempt to convert a series to numeric, stripping currency symbols."""
    if pd.api.types.is_numeric_dtype(series):
        return series
    cleaned = (
        series.astype(str)
        .str.replace(r"[^\d.\-]", "", regex=True)
        .replace("", np.nan)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def format_number(value: float) -> str:
    """Format large numbers with K/M/B suffixes for KPI cards."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    abs_v = abs(value)
    if abs_v >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.2f}B"
    if abs_v >= 1_000_000:
        return f"{value / 1_000_000:,.2f}M"
    if abs_v >= 1_000:
        return f"{value / 1_000:,.1f}K"
    return f"{value:,.2f}"


def chunked(iterable: Iterable, size: int):
    """Yield successive ``size``-length chunks from ``iterable``."""
    bucket: list = []
    for item in iterable:
        bucket.append(item)
        if len(bucket) == size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket
