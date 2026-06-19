"""Module 5 – AI Data Analyst Chatbot.

A natural-language query interface over the active dataframe. By design it works
fully offline using a rule-based intent engine (top-N, aggregation, trends,
anomalies, correlation, counts). When an LLM provider key is configured it can
additionally route free-form questions to the LLM for richer answers.
"""
from __future__ import annotations

import re

import pandas as pd
import plotly.express as px
import streamlit as st

from database import get_database
from utils import get_logger, load_config
from utils.helpers import (
    categorical_columns,
    coerce_numeric,
    detect_semantic_column,
    numeric_columns,
)
from utils.ui import insight, page_banner, require_data, section_header

logger = get_logger(__name__)
cfg = load_config()


# ── Rule-based intent engine ────────────────────────────────────────────
def answer_question(df: pd.DataFrame, question: str) -> dict:
    """Interpret a natural-language question and produce an answer.

    Returns:
        Dict with ``text`` (str) and optional ``figure`` (Plotly fig) /
        ``table`` (DataFrame).
    """
    q = question.lower().strip()
    num_cols = numeric_columns(df)
    cat_cols = categorical_columns(df)
    revenue_col = detect_semantic_column(df, "revenue") or (num_cols[0] if num_cols else None)

    # ── Top-N / highest ─────────────────────────────────────────────
    if any(w in q for w in ("top", "highest", "best", "most", "largest")):
        n = _extract_int(q, default=10)
        group_col = _match_column(q, cat_cols) or detect_semantic_column(df, "customer") \
            or detect_semantic_column(df, "category") or (cat_cols[0] if cat_cols else None)
        metric = _match_column(q, num_cols) or revenue_col
        if group_col and metric:
            grouped = (
                df.assign(_m=coerce_numeric(df[metric]))
                .groupby(group_col)["_m"].sum().sort_values(ascending=False).head(n)
            )
            table = grouped.rename(metric).reset_index()
            fig = px.bar(table, x=group_col, y=metric, title=f"Top {n} {group_col} by {metric}")
            return {
                "text": f"Here are the top {n} **{group_col}** values ranked by **{metric}**. "
                        f"The leader is **{grouped.index[0]}** with "
                        f"{grouped.iloc[0]:,.2f}.",
                "table": table, "figure": fig,
            }

    # ── Lowest / worst ──────────────────────────────────────────────
    if any(w in q for w in ("lowest", "worst", "least", "bottom")):
        n = _extract_int(q, default=10)
        group_col = _match_column(q, cat_cols) or (cat_cols[0] if cat_cols else None)
        metric = _match_column(q, num_cols) or revenue_col
        if group_col and metric:
            grouped = (
                df.assign(_m=coerce_numeric(df[metric]))
                .groupby(group_col)["_m"].sum().sort_values().head(n)
            )
            table = grouped.rename(metric).reset_index()
            fig = px.bar(table, x=group_col, y=metric, title=f"Bottom {n} {group_col} by {metric}")
            return {"text": f"Bottom {n} **{group_col}** by **{metric}**.",
                    "table": table, "figure": fig}

    # ── Trends ──────────────────────────────────────────────────────
    if any(w in q for w in ("trend", "over time", "growth", "forecast", "monthly")):
        date_col = detect_semantic_column(df, "date")
        metric = _match_column(q, num_cols) or revenue_col
        if date_col and metric:
            tmp = df[[date_col, metric]].dropna().copy()
            tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
            tmp["_m"] = coerce_numeric(tmp[metric])
            tmp = tmp.dropna().sort_values(date_col)
            trend = tmp.set_index(date_col)["_m"].resample("ME").sum().reset_index()
            trend.columns = [date_col, metric]
            fig = px.line(trend, x=date_col, y=metric, markers=True,
                          title=f"{metric} trend over time")
            direction = "increasing" if trend[metric].iloc[-1] >= trend[metric].iloc[0] else "decreasing"
            return {"text": f"The **{metric}** trend is **{direction}** over the observed period.",
                    "table": trend, "figure": fig}

    # ── Anomalies ───────────────────────────────────────────────────
    if any(w in q for w in ("anomal", "outlier", "unusual", "abnormal")):
        metric = _match_column(q, num_cols) or revenue_col
        if metric:
            series = coerce_numeric(df[metric]).dropna()
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            mask = (series < lower) | (series > upper)
            anomalies = df.loc[mask.index[mask]]
            fig = px.box(df, y=metric, title=f"Anomaly detection on {metric}")
            return {
                "text": f"Detected **{int(mask.sum())}** anomalies in **{metric}** "
                        f"using the IQR method (outside [{lower:,.1f}, {upper:,.1f}]).",
                "table": anomalies.head(20), "figure": fig,
            }

    # ── Correlation ─────────────────────────────────────────────────
    if "correlat" in q or "relationship" in q:
        if len(num_cols) >= 2:
            corr = df[num_cols].corr(numeric_only=True).round(2)
            fig = px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r",
                            zmin=-1, zmax=1, title="Correlation matrix")
            return {"text": "Correlation matrix across numeric columns.", "figure": fig}

    # ── Count / how many ────────────────────────────────────────────
    if any(w in q for w in ("how many", "count", "number of", "total rows")):
        col = _match_column(q, cat_cols)
        if col:
            counts = df[col].value_counts().reset_index()
            counts.columns = [col, "count"]
            fig = px.bar(counts.head(15), x=col, y="count", title=f"Counts by {col}")
            return {"text": f"Value counts for **{col}** ({df[col].nunique()} unique).",
                    "table": counts, "figure": fig}
        return {"text": f"The dataset has **{len(df):,}** rows and **{df.shape[1]}** columns."}

    # ── Average / sum ───────────────────────────────────────────────
    if any(w in q for w in ("average", "mean", "sum", "total")):
        metric = _match_column(q, num_cols) or revenue_col
        if metric:
            series = coerce_numeric(df[metric])
            agg = "average" if any(w in q for w in ("average", "mean")) else "total"
            value = series.mean() if agg == "average" else series.sum()
            return {"text": f"The {agg} of **{metric}** is **{value:,.2f}**."}

    # ── LLM fallback (optional) ─────────────────────────────────────
    if cfg.llm_enabled:
        llm_answer = _llm_answer(df, question)
        if llm_answer:
            return {"text": llm_answer}

    return {
        "text": "I couldn't map that to a specific analysis. Try asking about "
                "*top customers*, *sales trends*, *anomalies*, *correlations*, "
                "or *averages*. (Connect an LLM API key for free-form Q&A.)"
    }


# ── Helpers ─────────────────────────────────────────────────────────────
def _extract_int(text: str, default: int) -> int:
    match = re.search(r"\b(\d+)\b", text)
    return int(match.group(1)) if match else default


def _match_column(text: str, columns: list[str]) -> str | None:
    """Find a column whose name appears in the question."""
    for col in columns:
        if col.lower() in text or col.lower().replace("_", " ") in text:
            return col
    return None


def _llm_answer(df: pd.DataFrame, question: str) -> str | None:
    """Optional LLM-backed answer. Returns None if unavailable/erroring."""
    try:
        context = (
            f"Columns: {list(df.columns)}\n"
            f"Shape: {df.shape}\n"
            f"Summary:\n{df.describe(include='all').head(3).to_string()}"
        )
        prompt = (
            "You are a senior data analyst. Given this dataset context, answer the "
            f"user's question concisely in business language.\n\n{context}\n\n"
            f"Question: {question}"
        )
        if cfg.openai_api_key:
            from openai import OpenAI

            client = OpenAI(api_key=cfg.openai_api_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return resp.choices[0].message.content
        if cfg.gemini_api_key:
            import google.generativeai as genai

            genai.configure(api_key=cfg.gemini_api_key)
            # Try a current fast model, fall back to 1.5-flash for older SDKs.
            for model_name in ("gemini-2.0-flash", "gemini-1.5-flash"):
                try:
                    model = genai.GenerativeModel(model_name)
                    return model.generate_content(prompt).text
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        logger.warning("LLM fallback failed", exc_info=True)
    return None


def render() -> None:
    """Render the AI Data Analyst Chatbot page."""
    page_banner(
        "🤖", "AI Data Analyst Chatbot",
        "Ask questions in plain English — get insights, tables and charts instantly.",
    )
    if not require_data():
        return

    df: pd.DataFrame = st.session_state["df"]

    if cfg.llm_enabled:
        st.caption("🟢 LLM provider connected — free-form questions enabled.")
    else:
        st.caption("⚪ Running in offline rule-based mode. Set OPENAI_API_KEY or "
                   "GEMINI_API_KEY to enable free-form Q&A.")

    st.markdown("**Try:** _Show top 10 customers_ · _What are the sales trends?_ · "
                "_Find anomalies_ · _Which category generated highest revenue?_")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    question = st.chat_input("Ask InsightAI about your data…")
    if question:
        with st.spinner("Analysing…"):
            result = answer_question(df, question)
        st.session_state["chat_history"].append((question, result))
        try:
            get_database().log_query(
                st.session_state.get("dataset_name"), question, result["text"]
            )
        except Exception:  # noqa: BLE001
            logger.debug("Query logging failed", exc_info=True)

    # Replay history (most recent last).
    for q, result in st.session_state["chat_history"]:
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            st.markdown(result["text"])
            if result.get("figure") is not None:
                st.plotly_chart(result["figure"], use_container_width=True)
            if result.get("table") is not None:
                st.dataframe(result["table"], use_container_width=True, hide_index=True)
