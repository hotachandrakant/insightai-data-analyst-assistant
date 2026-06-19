"""Module 2 – Data Cleaning Assistant.

Detects data-quality issues (missing values, duplicates, outliers, type
problems, empty columns) and offers one-click remediation with a transparent
before/after comparison.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from utils import get_logger
from utils.helpers import numeric_columns
from utils.ui import insight, kpi_cards, page_banner, require_data, section_header

logger = get_logger(__name__)


# ── Detection ──────────────────────────────────────────────────────────
def detect_issues(df: pd.DataFrame) -> dict:
    """Run a full data-quality scan.

    Returns:
        Dict summarising detected issues per category.
    """
    num_cols = numeric_columns(df)
    outliers: dict[str, int] = {}
    for col in num_cols:
        series = df[col].dropna()
        if series.empty:
            continue
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        count = int(((series < lower) | (series > upper)).sum())
        if count:
            outliers[col] = count

    return {
        "missing": df.isna().sum().to_dict(),
        "missing_total": int(df.isna().sum().sum()),
        "duplicates": int(df.duplicated().sum()),
        "empty_columns": [c for c in df.columns if df[c].isna().all()],
        "outliers": outliers,
        "outliers_total": int(sum(outliers.values())),
    }


# ── Remediation ────────────────────────────────────────────────────────
def treat_outliers_iqr(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Cap outliers to the IQR fence (winsorisation)."""
    out = df.copy()
    for col in columns:
        series = out[col]
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out[col] = series.clip(lower=lower, upper=upper)
    return out


def fill_missing(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    """Impute missing values using the chosen strategy."""
    out = df.copy()
    for col in out.columns:
        if out[col].isna().sum() == 0:
            continue
        if pd.api.types.is_numeric_dtype(out[col]):
            if strategy == "mean":
                out[col] = out[col].fillna(out[col].mean())
            elif strategy == "median":
                out[col] = out[col].fillna(out[col].median())
            elif strategy == "zero":
                out[col] = out[col].fillna(0)
            else:  # mode fallback
                out[col] = out[col].fillna(out[col].mode().iloc[0] if not out[col].mode().empty else 0)
        else:
            mode = out[col].mode()
            out[col] = out[col].fillna(mode.iloc[0] if not mode.empty else "Unknown")
    return out


def render() -> None:
    """Render the Data Cleaning page."""
    page_banner(
        "🧹", "Data Cleaning Assistant",
        "Automatically detect quality issues and remediate them with one click.",
    )
    if not require_data():
        return

    df: pd.DataFrame = st.session_state["df"]
    issues = detect_issues(df)

    kpi_cards(
        [
            {"label": "Missing Values", "value": f"{issues['missing_total']:,}"},
            {"label": "Duplicate Rows", "value": f"{issues['duplicates']:,}"},
            {"label": "Outliers (IQR)", "value": f"{issues['outliers_total']:,}"},
            {"label": "Empty Columns", "value": str(len(issues["empty_columns"]))},
        ]
    )

    # ── Issue detail ───────────────────────────────────────────────────
    with st.expander("🔍 Detected Issues – details", expanded=True):
        missing_df = pd.DataFrame(
            {
                "Column": list(issues["missing"].keys()),
                "Missing": list(issues["missing"].values()),
            }
        )
        missing_df = missing_df[missing_df["Missing"] > 0]
        missing_df["% Missing"] = (missing_df["Missing"] / len(df) * 100).round(2)
        if not missing_df.empty:
            insight("Columns with missing data detected — consider imputation or removal.", "warn")
            st.dataframe(missing_df, use_container_width=True, hide_index=True)
        else:
            insight("No missing values found. ✅", "good")

        if issues["outliers"]:
            insight("Outliers detected in numeric columns (IQR method).", "warn")
            st.dataframe(
                pd.DataFrame(
                    {"Column": list(issues["outliers"].keys()),
                     "Outliers": list(issues["outliers"].values())}
                ),
                use_container_width=True, hide_index=True,
            )
        if issues["empty_columns"]:
            insight(f"Empty columns: {', '.join(issues['empty_columns'])}", "bad")

    # ── Cleaning actions ───────────────────────────────────────────────
    st.divider()
    section_header("Cleaning Actions")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Missing values**")
        miss_action = st.radio(
            "Strategy",
            ["Do nothing", "Drop rows with missing", "Fill: mean", "Fill: median",
             "Fill: mode", "Fill: zero"],
            key="miss_action",
        )
        st.markdown("**Duplicates & empty columns**")
        drop_dupes = st.checkbox("Remove duplicate rows", value=issues["duplicates"] > 0)
        drop_empty = st.checkbox("Drop empty columns", value=bool(issues["empty_columns"]))

    with col2:
        st.markdown("**Outlier treatment (IQR capping)**")
        out_cols = st.multiselect(
            "Columns to winsorise",
            list(issues["outliers"].keys()),
            default=list(issues["outliers"].keys()),
        )

    if st.button("🚀 Apply Cleaning", type="primary"):
        cleaned = df.copy()
        before_shape = cleaned.shape

        if drop_empty and issues["empty_columns"]:
            cleaned = cleaned.drop(columns=issues["empty_columns"])
        if miss_action == "Drop rows with missing":
            cleaned = cleaned.dropna()
        elif miss_action.startswith("Fill:"):
            cleaned = fill_missing(cleaned, miss_action.split(":")[1].strip())
        if drop_dupes:
            cleaned = cleaned.drop_duplicates()
        if out_cols:
            cleaned = treat_outliers_iqr(cleaned, out_cols)

        st.session_state["df"] = cleaned
        logger.info("Cleaning applied: %s -> %s", before_shape, cleaned.shape)

        st.success("✅ Cleaning applied successfully.")
        _before_after(df, cleaned)


def _before_after(before: pd.DataFrame, after: pd.DataFrame) -> None:
    """Render a before/after comparison."""
    st.divider()
    section_header("Before vs After")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Before**")
        st.metric("Rows", f"{before.shape[0]:,}")
        st.metric("Missing", f"{int(before.isna().sum().sum()):,}")
        st.metric("Duplicates", f"{int(before.duplicated().sum()):,}")
    with c2:
        st.markdown("**After**")
        st.metric("Rows", f"{after.shape[0]:,}", delta=after.shape[0] - before.shape[0])
        st.metric("Missing", f"{int(after.isna().sum().sum()):,}",
                  delta=int(after.isna().sum().sum() - before.isna().sum().sum()))
        st.metric("Duplicates", f"{int(after.duplicated().sum()):,}",
                  delta=int(after.duplicated().sum() - before.duplicated().sum()))
