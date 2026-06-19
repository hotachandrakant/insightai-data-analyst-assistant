"""Module 1 – Data Upload.

Handles CSV/Excel ingestion (with drag-and-drop), dataset preview, shape
display and persistence into session state + audit database.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from database import get_database
from utils import get_logger
from utils.helpers import (
    categorical_columns,
    datetime_columns,
    human_readable_size,
    load_dataframe,
    numeric_columns,
)
from utils.ui import kpi_cards, page_banner, section_header

logger = get_logger(__name__)


def _store_dataset(df: pd.DataFrame, name: str) -> None:
    """Persist the active dataframe in session state and the audit DB."""
    st.session_state["df"] = df
    st.session_state["df_original"] = df.copy()
    st.session_state["dataset_name"] = name
    try:
        get_database().log_dataset(name, df.shape[0], df.shape[1])
    except Exception:  # noqa: BLE001 - DB logging is best-effort
        logger.warning("Could not log dataset to database", exc_info=True)


def _load_sample(path) -> None:
    df = pd.read_csv(path)
    _store_dataset(df, path.name)
    st.success(f"Loaded sample dataset: **{path.name}**")


def render() -> None:
    """Render the Data Upload page."""
    page_banner(
        "📂", "Data Upload",
        "Upload a CSV or Excel file, or start instantly with a realistic sample dataset.",
    )

    from utils.config import load_config

    cfg = load_config()

    col_upload, col_sample = st.columns([2, 1])

    with col_upload:
        uploaded = st.file_uploader(
            "Drag & drop a file here",
            type=list(cfg.allowed_extensions),
            help="Supported formats: CSV, XLSX, XLS. Max size 200MB.",
        )
        if uploaded is not None:
            with st.spinner("Reading and parsing your file…"):
                try:
                    df = load_dataframe(uploaded)
                    _store_dataset(df, uploaded.name)
                    st.success(
                        f"✅ Loaded **{uploaded.name}** "
                        f"({human_readable_size(uploaded.size)})"
                    )
                except ValueError as exc:
                    st.error(f"❌ {exc}")
                    logger.error("Upload failed: %s", exc)

    with col_sample:
        st.markdown("**Or try a sample dataset**")
        samples = sorted(cfg.data_dir.glob("*.csv"))
        if not samples:
            st.caption("Run `python data/generate_samples.py` to create samples.")
        for sample in samples:
            if st.button(f"📄 {sample.stem.replace('_', ' ').title()}", key=sample.name):
                _load_sample(sample)

    df = st.session_state.get("df")
    if df is None:
        st.info("Upload a file or pick a sample to see a preview here.")
        return

    # ── Dataset overview KPIs ──────────────────────────────────────────
    st.divider()
    section_header("Dataset Overview")
    mem = df.memory_usage(deep=True).sum()
    kpi_cards(
        [
            {"label": "Rows", "value": f"{df.shape[0]:,}"},
            {"label": "Columns", "value": f"{df.shape[1]:,}"},
            {"label": "Numeric Cols", "value": str(len(numeric_columns(df)))},
            {"label": "Categorical Cols", "value": str(len(categorical_columns(df)))},
            {"label": "Datetime Cols", "value": str(len(datetime_columns(df)))},
            {"label": "Memory", "value": human_readable_size(int(mem))},
        ]
    )

    # ── Preview ────────────────────────────────────────────────────────
    section_header("Data Preview")
    n_rows = st.slider("Preview rows", 5, min(100, len(df)), 10)
    st.dataframe(df.head(n_rows), use_container_width=True)

    # ── Schema ─────────────────────────────────────────────────────────
    section_header("Column Schema")
    schema = pd.DataFrame(
        {
            "Column": df.columns,
            "Type": [str(t) for t in df.dtypes],
            "Non-Null": df.notna().sum().values,
            "Nulls": df.isna().sum().values,
            "Unique": [df[c].nunique(dropna=True) for c in df.columns],
        }
    )
    st.dataframe(schema, use_container_width=True, hide_index=True)
