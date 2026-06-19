"""Module 8 – Insight Generator.

Produces business-language insights and recommendations from a dataframe using
rule-based heuristics over detected revenue/category/region/time columns. The
:func:`generate_insights` function is reused by the report generator.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils import get_logger
from utils.helpers import (
    coerce_numeric,
    detect_semantic_column,
    numeric_columns,
    safe_div,
)
from utils.ui import insight, page_banner, require_data, section_header

logger = get_logger(__name__)


def generate_insights(df: pd.DataFrame) -> list[dict]:
    """Generate a list of business insights.

    Returns:
        List of dicts with keys ``text`` and ``kind`` (info/good/warn/bad).
    """
    insights: list[dict] = []
    num_cols = numeric_columns(df)

    revenue_col = detect_semantic_column(df, "revenue")
    profit_col = detect_semantic_column(df, "profit")
    category_col = detect_semantic_column(df, "category")
    region_col = detect_semantic_column(df, "region")
    date_col = detect_semantic_column(df, "date")
    customer_col = detect_semantic_column(df, "customer")

    # ── Category concentration ─────────────────────────────────────────
    if category_col and revenue_col:
        grouped = (
            df.assign(_rev=coerce_numeric(df[revenue_col]))
            .groupby(category_col)["_rev"].sum().sort_values(ascending=False)
        )
        if not grouped.empty:
            top = grouped.index[0]
            share = safe_div(grouped.iloc[0], grouped.sum()) * 100
            insights.append({
                "text": f"Product category <b>{top}</b> contributes "
                        f"<b>{share:.1f}%</b> of total revenue, making it the primary driver.",
                "kind": "info",
            })
            if share > 50:
                insights.append({
                    "text": f"Revenue is heavily concentrated in <b>{top}</b> "
                            f"(>50%), indicating portfolio concentration risk.",
                    "kind": "warn",
                })

    # ── Regional trends ────────────────────────────────────────────────
    if region_col and revenue_col:
        grouped = (
            df.assign(_rev=coerce_numeric(df[revenue_col]))
            .groupby(region_col)["_rev"].sum().sort_values(ascending=False)
        )
        if len(grouped) >= 2:
            best, worst = grouped.index[0], grouped.index[-1]
            insights.append({
                "text": f"The <b>{best}</b> region leads revenue performance, while "
                        f"<b>{worst}</b> lags and may need targeted intervention.",
                "kind": "info",
            })

    # ── Growth trend ───────────────────────────────────────────────────
    if date_col and revenue_col:
        try:
            tmp = df[[date_col, revenue_col]].dropna().copy()
            tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
            tmp["_rev"] = coerce_numeric(tmp[revenue_col])
            tmp = tmp.dropna().sort_values(date_col)
            monthly = tmp.set_index(date_col)["_rev"].resample("ME").sum()
            if len(monthly) >= 3:
                recent = monthly.iloc[-3:]
                if recent.is_monotonic_increasing:
                    insights.append({"text": "Revenue has grown for three consecutive periods — positive momentum.", "kind": "good"})
                elif recent.is_monotonic_decreasing:
                    insights.append({"text": "Revenue has declined for three consecutive periods — investigate demand drivers.", "kind": "bad"})
                overall = safe_div(monthly.iloc[-1] - monthly.iloc[0], abs(monthly.iloc[0])) * 100
                insights.append({
                    "text": f"Over the observed period, revenue changed by "
                            f"<b>{overall:+.1f}%</b> from first to last month.",
                    "kind": "good" if overall >= 0 else "warn",
                })
        except Exception:  # noqa: BLE001
            logger.debug("Growth insight skipped", exc_info=True)

    # ── Profitability ──────────────────────────────────────────────────
    if profit_col and revenue_col:
        margin = safe_div(coerce_numeric(df[profit_col]).sum(),
                          coerce_numeric(df[revenue_col]).sum()) * 100
        tone = "good" if margin >= 15 else ("warn" if margin >= 5 else "bad")
        insights.append({
            "text": f"Overall profit margin is <b>{margin:.1f}%</b>.",
            "kind": tone,
        })

    # ── Customer concentration ─────────────────────────────────────────
    if customer_col and revenue_col:
        grouped = (
            df.assign(_rev=coerce_numeric(df[revenue_col]))
            .groupby(customer_col)["_rev"].sum().sort_values(ascending=False)
        )
        if len(grouped) >= 10:
            top10_share = safe_div(grouped.head(10).sum(), grouped.sum()) * 100
            insights.append({
                "text": f"The top 10 customers account for <b>{top10_share:.1f}%</b> "
                        f"of revenue.",
                "kind": "warn" if top10_share > 60 else "info",
            })

    # ── Data-quality observation ───────────────────────────────────────
    missing_pct = safe_div(df.isna().sum().sum(), df.size) * 100
    if missing_pct > 5:
        insights.append({
            "text": f"Dataset has <b>{missing_pct:.1f}%</b> missing values — "
                    f"consider cleaning before drawing firm conclusions.",
            "kind": "warn",
        })

    # ── Statistical highlight ──────────────────────────────────────────
    if len(num_cols) >= 2:
        corr = df[num_cols].corr(numeric_only=True)
        import numpy as np
        mask = ~np.eye(len(corr), dtype=bool)
        stacked = corr.where(mask).abs().stack()
        if not stacked.empty and stacked.max() > 0.7:
            a, b = stacked.idxmax()
            insights.append({
                "text": f"Strong correlation detected between <b>{a}</b> and "
                        f"<b>{b}</b> (r = {corr.loc[a, b]:.2f}).",
                "kind": "info",
            })

    if not insights:
        insights.append({"text": "Upload richer business data (revenue, dates, categories) to unlock tailored insights.", "kind": "info"})

    return insights


def render() -> None:
    """Render the Insight Generator page."""
    page_banner(
        "💡", "Insight Generator",
        "Automatically generated, board-ready business insights and recommendations.",
    )
    if not require_data():
        return

    df: pd.DataFrame = st.session_state["df"]
    items = generate_insights(df)
    for item in items:
        insight(item["text"], item["kind"])
