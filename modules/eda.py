"""Module 3 – Automated Exploratory Data Analysis.

Generates summary statistics, correlation analysis and a suite of interactive
Plotly visualisations (histograms, boxplots, scatter, distribution, pairplot).
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
import streamlit as st

from utils import get_logger
from utils.helpers import categorical_columns, numeric_columns
from utils.ui import insight, page_banner, require_data, section_header

logger = get_logger(__name__)


def render() -> None:
    """Render the EDA page."""
    page_banner(
        "📊", "Automated EDA",
        "Interactive exploratory analysis generated automatically from your data.",
    )
    if not require_data():
        return

    df: pd.DataFrame = st.session_state["df"]
    num_cols = numeric_columns(df)
    cat_cols = categorical_columns(df)

    tabs = st.tabs(
        ["📈 Summary", "🔗 Correlation", "📊 Distributions",
         "📦 Boxplots", "🎯 Scatter", "🧩 Pairplot"]
    )

    # ── Summary statistics ─────────────────────────────────────────────
    with tabs[0]:
        section_header("Summary Statistics")
        if num_cols:
            st.dataframe(df[num_cols].describe().T, use_container_width=True)
        if cat_cols:
            section_header("Categorical Overview")
            cat_summary = pd.DataFrame(
                {
                    "Column": cat_cols,
                    "Unique": [df[c].nunique() for c in cat_cols],
                    "Top": [df[c].mode().iloc[0] if not df[c].mode().empty else "—"
                            for c in cat_cols],
                    "Top Freq": [int(df[c].value_counts().iloc[0]) if df[c].notna().any() else 0
                                 for c in cat_cols],
                }
            )
            st.dataframe(cat_summary, use_container_width=True, hide_index=True)

    # ── Correlation ────────────────────────────────────────────────────
    with tabs[1]:
        section_header("Correlation Matrix")
        if len(num_cols) >= 2:
            corr = df[num_cols].corr(numeric_only=True).round(2)
            fig = px.imshow(
                corr, text_auto=True, aspect="auto",
                color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                title="Pearson Correlation",
            )
            st.plotly_chart(fig, use_container_width=True)

            # Highlight strongest relationship
            stacked = corr.where(~_eye_mask(corr)).abs().stack()
            if not stacked.empty:
                a, b = stacked.idxmax()
                insight(
                    f"Strongest relationship: <b>{a}</b> ↔ <b>{b}</b> "
                    f"(r = {corr.loc[a, b]:.2f}).",
                    "info",
                )
        else:
            st.info("Need at least two numeric columns for correlation analysis.")

    # ── Distributions ──────────────────────────────────────────────────
    with tabs[2]:
        section_header("Distribution Analysis")
        if num_cols:
            col = st.selectbox("Numeric column", num_cols, key="dist_col")
            color = st.selectbox("Group by (optional)", ["None"] + cat_cols, key="dist_color")
            fig = px.histogram(
                df, x=col, nbins=40, marginal="box",
                color=None if color == "None" else color,
                title=f"Distribution of {col}",
            )
            st.plotly_chart(fig, use_container_width=True)
            skew = df[col].skew()
            tone = "good" if abs(skew) < 0.5 else "warn"
            insight(f"Skewness of <b>{col}</b> = {skew:.2f} "
                    f"({'approximately symmetric' if abs(skew) < 0.5 else 'skewed'}).", tone)
        else:
            st.info("No numeric columns available.")

    # ── Boxplots ───────────────────────────────────────────────────────
    with tabs[3]:
        section_header("Boxplots")
        if num_cols:
            col = st.selectbox("Numeric column", num_cols, key="box_col")
            group = st.selectbox("Group by (optional)", ["None"] + cat_cols, key="box_group")
            fig = px.box(
                df, y=col, x=None if group == "None" else group,
                color=None if group == "None" else group,
                title=f"Boxplot of {col}",
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── Scatter ────────────────────────────────────────────────────────
    with tabs[4]:
        section_header("Scatter Analysis")
        if len(num_cols) >= 2:
            x = st.selectbox("X axis", num_cols, key="sc_x")
            y = st.selectbox("Y axis", [c for c in num_cols if c != x], key="sc_y")
            color = st.selectbox("Color by (optional)", ["None"] + cat_cols, key="sc_color")
            fig = px.scatter(
                df, x=x, y=y, color=None if color == "None" else color,
                trendline="ols", opacity=0.7, title=f"{y} vs {x}",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Need at least two numeric columns for a scatter plot.")

    # ── Pairplot ───────────────────────────────────────────────────────
    with tabs[5]:
        section_header("Pairplot (Scatter Matrix)")
        if len(num_cols) >= 2:
            selected = st.multiselect(
                "Select up to 5 numeric columns", num_cols, default=num_cols[:4]
            )[:5]
            if len(selected) >= 2:
                color = st.selectbox("Color by (optional)", ["None"] + cat_cols, key="pp_color")
                fig = px.scatter_matrix(
                    df, dimensions=selected,
                    color=None if color == "None" else color,
                    title="Scatter Matrix",
                )
                fig.update_traces(diagonal_visible=False, showupperhalf=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Select at least two columns.")
        else:
            st.info("Need at least two numeric columns.")


def _eye_mask(corr: pd.DataFrame):
    """Boolean identity mask without relying on deprecated pandas.np."""
    import numpy as np

    return pd.DataFrame(
        np.eye(len(corr), dtype=bool), index=corr.index, columns=corr.columns
    )
