"""Module 4 – Business Intelligence Dashboard.

Builds an executive-level dashboard with auto-detected KPIs (revenue, sales,
profit, growth, customers), trend charts, category & regional analysis and a
correlation heatmap.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import get_logger
from utils.helpers import (
    categorical_columns,
    coerce_numeric,
    datetime_columns,
    detect_semantic_column,
    format_number,
    numeric_columns,
    safe_div,
)
from utils.ui import insight, kpi_cards, page_banner, require_data, section_header

logger = get_logger(__name__)


def _compute_kpis(df: pd.DataFrame) -> list[dict]:
    """Auto-detect business KPIs from semantic column matching."""
    kpis: list[dict] = []

    revenue_col = detect_semantic_column(df, "revenue")
    profit_col = detect_semantic_column(df, "profit")
    sales_col = detect_semantic_column(df, "sales")
    customer_col = detect_semantic_column(df, "customer")
    date_col = detect_semantic_column(df, "date")

    if revenue_col:
        total_rev = coerce_numeric(df[revenue_col]).sum()
        kpis.append({"label": "Total Revenue", "value": f"${format_number(total_rev)}"})
    if profit_col:
        total_profit = coerce_numeric(df[profit_col]).sum()
        kpis.append({"label": "Total Profit", "value": f"${format_number(total_profit)}"})
        if revenue_col:
            margin = safe_div(total_profit, coerce_numeric(df[revenue_col]).sum()) * 100
            kpis.append({"label": "Profit Margin", "value": f"{margin:.1f}%"})
    if sales_col and sales_col != revenue_col:
        kpis.append({"label": "Total Units", "value": format_number(coerce_numeric(df[sales_col]).sum())})
    if customer_col:
        kpis.append({"label": "Customers", "value": f"{df[customer_col].nunique():,}"})

    # Growth rate from a time-ordered revenue series.
    if revenue_col and date_col:
        try:
            tmp = df[[date_col, revenue_col]].dropna().copy()
            tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
            tmp = tmp.dropna().sort_values(date_col)
            tmp[revenue_col] = coerce_numeric(tmp[revenue_col])
            monthly = tmp.set_index(date_col)[revenue_col].resample("ME").sum()
            if len(monthly) >= 2 and monthly.iloc[-2] != 0:
                growth = (monthly.iloc[-1] - monthly.iloc[-2]) / abs(monthly.iloc[-2]) * 100
                kpis.append({
                    "label": "MoM Growth", "value": f"{growth:.1f}%",
                    "delta": f"{growth:.1f}%", "direction": "up" if growth >= 0 else "down",
                })
        except Exception:  # noqa: BLE001
            logger.debug("Growth-rate computation skipped", exc_info=True)

    # Fallback: if nothing semantic matched, show top numeric aggregates.
    if not kpis:
        for col in numeric_columns(df)[:4]:
            kpis.append({"label": f"Σ {col}", "value": format_number(df[col].sum())})
    return kpis


def render() -> None:
    """Render the BI Dashboard page."""
    page_banner(
        "📈", "Business Intelligence Dashboard",
        "Executive KPIs, trends and segment analysis — auto-generated from your data.",
    )
    if not require_data():
        return

    df: pd.DataFrame = st.session_state["df"]

    kpi_cards(_compute_kpis(df))

    num_cols = numeric_columns(df)
    cat_cols = categorical_columns(df)
    date_cols = datetime_columns(df) or (
        [detect_semantic_column(df, "date")] if detect_semantic_column(df, "date") else []
    )
    date_cols = [c for c in date_cols if c]

    revenue_col = detect_semantic_column(df, "revenue") or (num_cols[0] if num_cols else None)

    col_left, col_right = st.columns(2)

    # ── Trend chart ────────────────────────────────────────────────────
    with col_left:
        section_header("Trend Over Time")
        if date_cols and revenue_col:
            date_col = st.selectbox("Date column", date_cols, key="dash_date")
            metric = st.selectbox("Metric", num_cols, key="dash_metric",
                                  index=num_cols.index(revenue_col) if revenue_col in num_cols else 0)
            tmp = df[[date_col, metric]].dropna().copy()
            tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
            tmp[metric] = coerce_numeric(tmp[metric])
            tmp = tmp.dropna().sort_values(date_col)
            trend = tmp.set_index(date_col)[metric].resample("ME").sum().reset_index()
            fig = px.area(trend, x=date_col, y=metric, title=f"{metric} over time")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No date column detected for trend analysis.")

    # ── Category analysis ──────────────────────────────────────────────
    with col_right:
        section_header("Category Analysis")
        cat_choices = [detect_semantic_column(df, "category")] + cat_cols
        cat_choices = list(dict.fromkeys([c for c in cat_choices if c]))
        if cat_choices and revenue_col:
            cat_col = st.selectbox("Category column", cat_choices, key="dash_cat")
            metric = st.selectbox("Metric", num_cols, key="dash_cat_metric")
            grouped = (
                df.assign(**{metric: coerce_numeric(df[metric])})
                .groupby(cat_col)[metric].sum().sort_values(ascending=False).head(10)
                .reset_index()
            )
            fig = px.bar(grouped, x=metric, y=cat_col, orientation="h",
                         title=f"Top {cat_col} by {metric}")
            fig.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

            top = grouped.iloc[0]
            share = safe_div(top[metric], grouped[metric].sum()) * 100
            insight(f"<b>{top[cat_col]}</b> leads with {share:.1f}% of the top-10 {metric}.", "info")
        else:
            st.info("No categorical column detected for segment analysis.")

    # ── Regional analysis ──────────────────────────────────────────────
    region_col = detect_semantic_column(df, "region")
    if region_col and revenue_col:
        st.divider()
        section_header("Regional Analysis")
        metric = revenue_col if revenue_col in num_cols else num_cols[0]
        grouped = (
            df.assign(**{metric: coerce_numeric(df[metric])})
            .groupby(region_col)[metric].sum().sort_values(ascending=False).reset_index()
        )
        c1, c2 = st.columns([2, 1])
        with c1:
            fig = px.bar(grouped, x=region_col, y=metric, color=metric,
                         color_continuous_scale="Blues", title=f"{metric} by {region_col}")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.pie(grouped, names=region_col, values=metric, hole=0.5,
                         title="Share by region")
            st.plotly_chart(fig, use_container_width=True)

    # ── Heatmap ────────────────────────────────────────────────────────
    if len(num_cols) >= 2:
        st.divider()
        section_header("Metric Correlation Heatmap")
        corr = df[num_cols].corr(numeric_only=True).round(2)
        fig = px.imshow(corr, text_auto=True, color_continuous_scale="Blues", aspect="auto")
        st.plotly_chart(fig, use_container_width=True)
