"""Module 7 – Forecasting.

Generates future predictions for a time series using ARIMA (statsmodels) and,
when installed, Facebook Prophet. The app degrades gracefully when Prophet is
unavailable.
"""
from __future__ import annotations

import warnings

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import get_logger
from utils.helpers import (
    coerce_numeric,
    datetime_columns,
    detect_semantic_column,
    numeric_columns,
)
from utils.ui import insight, page_banner, require_data, section_header

logger = get_logger(__name__)

try:
    from prophet import Prophet  # type: ignore

    _HAS_PROPHET = True
except Exception:  # noqa: BLE001  - prophet import can fail for many reasons
    _HAS_PROPHET = False


def _prepare_series(df: pd.DataFrame, date_col: str, value_col: str, freq: str) -> pd.Series:
    """Aggregate to a regular time series indexed by date."""
    tmp = df[[date_col, value_col]].dropna().copy()
    tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
    tmp[value_col] = coerce_numeric(tmp[value_col])
    tmp = tmp.dropna().sort_values(date_col)
    series = tmp.set_index(date_col)[value_col].resample(freq).sum()
    return series.interpolate()


def _forecast_arima(series: pd.Series, periods: int) -> pd.DataFrame:
    """Fit a simple ARIMA(1,1,1) model and forecast forward."""
    from statsmodels.tsa.arima.model import ARIMA

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ARIMA(series, order=(1, 1, 1)).fit()
        forecast = model.get_forecast(steps=periods)
    mean = forecast.predicted_mean
    ci = forecast.conf_int()
    return pd.DataFrame({
        "date": mean.index,
        "forecast": mean.values,
        "lower": ci.iloc[:, 0].values,
        "upper": ci.iloc[:, 1].values,
    })


def _forecast_prophet(series: pd.Series, periods: int, freq: str) -> pd.DataFrame:
    """Fit Prophet and forecast forward."""
    prophet_df = pd.DataFrame({"ds": series.index, "y": series.values})
    model = Prophet()
    model.fit(prophet_df)
    future = model.make_future_dataframe(periods=periods, freq=freq)
    fc = model.predict(future).tail(periods)
    return pd.DataFrame({
        "date": fc["ds"].values,
        "forecast": fc["yhat"].values,
        "lower": fc["yhat_lower"].values,
        "upper": fc["yhat_upper"].values,
    })


def render() -> None:
    """Render the Forecasting page."""
    page_banner(
        "🔮", "Forecasting",
        "Project future values of a metric using ARIMA or Prophet.",
    )
    if not require_data():
        return

    df: pd.DataFrame = st.session_state["df"]
    date_cols = datetime_columns(df)
    sem_date = detect_semantic_column(df, "date")
    if sem_date and sem_date not in date_cols:
        date_cols.append(sem_date)
    num_cols = numeric_columns(df)

    if not date_cols or not num_cols:
        st.warning("Forecasting needs at least one date column and one numeric column.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        date_col = st.selectbox("Date column", date_cols)
    with c2:
        value_col = st.selectbox("Metric to forecast", num_cols)
    with c3:
        freq_label = st.selectbox("Frequency", ["Monthly", "Weekly", "Daily"])
    freq = {"Monthly": "ME", "Weekly": "W", "Daily": "D"}[freq_label]

    periods = st.slider("Periods to forecast", 3, 36, 12)

    engines = ["ARIMA"] + (["Prophet"] if _HAS_PROPHET else [])
    engine = st.radio("Model", engines, horizontal=True)
    if not _HAS_PROPHET:
        st.caption("ℹ️ Prophet not installed — install `prophet` to enable it.")

    if not st.button("🔮 Generate Forecast", type="primary"):
        return

    try:
        series = _prepare_series(df, date_col, value_col, freq)
        if len(series) < 5:
            st.warning("Not enough data points to forecast (need at least 5).")
            return
        with st.spinner(f"Fitting {engine} model…"):
            if engine == "Prophet":
                fc = _forecast_prophet(series, periods, freq)
            else:
                fc = _forecast_arima(series, periods)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Forecast failed: {exc}")
        logger.exception("Forecast failed")
        return

    _plot_forecast(series, fc, value_col)


def _plot_forecast(series: pd.Series, fc: pd.DataFrame, value_col: str) -> None:
    """Render the historical series with the forecast and confidence band."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series.values, name="Historical",
                             mode="lines", line=dict(color="#2563EB")))
    fig.add_trace(go.Scatter(x=fc["date"], y=fc["forecast"], name="Forecast",
                             mode="lines", line=dict(color="#DC2626", dash="dash")))
    fig.add_trace(go.Scatter(
        x=list(fc["date"]) + list(fc["date"][::-1]),
        y=list(fc["upper"]) + list(fc["lower"][::-1]),
        fill="toself", fillcolor="rgba(220,38,38,0.12)",
        line=dict(color="rgba(0,0,0,0)"), name="Confidence interval", hoverinfo="skip",
    ))
    fig.update_layout(title=f"{value_col} forecast", xaxis_title="Date", yaxis_title=value_col)
    st.plotly_chart(fig, use_container_width=True)

    change = fc["forecast"].iloc[-1] - series.iloc[-1]
    pct = (change / abs(series.iloc[-1]) * 100) if series.iloc[-1] else 0
    tone = "good" if change >= 0 else "warn"
    insight(f"Projected <b>{value_col}</b> at the forecast horizon is "
            f"<b>{fc['forecast'].iloc[-1]:,.1f}</b> "
            f"({pct:+.1f}% vs the latest actual).", tone)

    st.dataframe(fc.round(2), use_container_width=True, hide_index=True)
