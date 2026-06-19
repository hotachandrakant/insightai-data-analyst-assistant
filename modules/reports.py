"""Module 9 – Automated Report Generator.

Builds a downloadable PDF report (executive summary, dataset overview, insights,
recommendations) and a multi-sheet Excel workbook summarising the dataset.
"""
from __future__ import annotations

import io
import re
from datetime import datetime

import pandas as pd
import streamlit as st

from database import get_database
from modules.insights import generate_insights
from utils import get_logger, load_config
from utils.helpers import categorical_columns, numeric_columns
from utils.ui import page_banner, require_data, section_header

logger = get_logger(__name__)
cfg = load_config()


def _strip_html(text: str) -> str:
    """Remove inline HTML tags so text is PDF-safe."""
    return re.sub(r"<[^>]+>", "", text)


def _latin1(text: str) -> str:
    """Make text safe for FPDF's default latin-1 encoding."""
    return text.encode("latin-1", "replace").decode("latin-1")


def build_pdf(df: pd.DataFrame, dataset_name: str, insights: list[dict]) -> bytes:
    """Render the executive PDF report to bytes."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Title block ────────────────────────────────────────────────
    pdf.set_fill_color(37, 99, 235)
    pdf.rect(0, 0, 210, 32, style="F")
    pdf.set_xy(12, 8)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 10, _latin1(f"{cfg.app_name} Report"), ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_x(12)
    pdf.cell(0, 8, _latin1(cfg.tagline), ln=True)

    pdf.set_text_color(15, 23, 42)
    pdf.ln(18)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _latin1(f"Dataset: {dataset_name}"), ln=True)
    pdf.cell(0, 6, _latin1(f"Generated: {datetime.now():%Y-%m-%d %H:%M}"), ln=True)
    pdf.ln(4)

    # ── Executive summary ──────────────────────────────────────────
    _pdf_heading(pdf, "1. Executive Summary")
    pdf.set_font("Helvetica", "", 10)
    summary = (
        f"This automated report analyses the '{dataset_name}' dataset, comprising "
        f"{df.shape[0]:,} records across {df.shape[1]} attributes. It surfaces key "
        f"business insights, data-quality observations and actionable recommendations "
        f"derived from statistical and exploratory analysis."
    )
    _pdf_body(pdf, summary)
    pdf.ln(2)

    # ── Dataset overview ───────────────────────────────────────────
    _pdf_heading(pdf, "2. Dataset Overview")
    pdf.set_font("Helvetica", "", 10)
    overview = [
        ("Rows", f"{df.shape[0]:,}"),
        ("Columns", f"{df.shape[1]:,}"),
        ("Numeric columns", str(len(numeric_columns(df)))),
        ("Categorical columns", str(len(categorical_columns(df)))),
        ("Missing values", f"{int(df.isna().sum().sum()):,}"),
        ("Duplicate rows", f"{int(df.duplicated().sum()):,}"),
    ]
    for label, value in overview:
        pdf.cell(60, 6, _latin1(label), border=0)
        pdf.cell(0, 6, _latin1(value), ln=True)
    pdf.ln(2)

    # ── Insights ───────────────────────────────────────────────────
    _pdf_heading(pdf, "3. Key Insights")
    pdf.set_font("Helvetica", "", 10)
    for i, item in enumerate(insights, 1):
        _pdf_body(pdf, f"{i}. {_strip_html(item['text'])}")
    pdf.ln(2)

    # ── Recommendations ────────────────────────────────────────────
    _pdf_heading(pdf, "4. Recommendations")
    pdf.set_font("Helvetica", "", 10)
    for rec in _recommendations(insights):
        _pdf_body(pdf, f"- {rec}")

    out = pdf.output(dest="S")
    return bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")


def _pdf_heading(pdf, text: str) -> None:
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(0, 8, _latin1(text), ln=True)
    pdf.set_text_color(15, 23, 42)


def _pdf_body(pdf, text: str) -> None:
    """Write a wrapped paragraph using an explicit effective width.

    Resetting x to the left margin and passing the effective page width avoids
    fpdf2's ``w=0`` edge case ("not enough horizontal space").
    """
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 6, _latin1(text))


def _recommendations(insights: list[dict]) -> list[str]:
    """Derive simple recommendations from insight tone."""
    recs: list[str] = []
    for item in insights:
        text = _strip_html(item["text"])
        if item["kind"] == "bad":
            recs.append(f"Prioritise corrective action: {text}")
        elif item["kind"] == "warn":
            recs.append(f"Monitor closely: {text}")
    if not recs:
        recs.append("Maintain current strategy; metrics are within healthy ranges.")
    recs.append("Schedule a recurring review to track these KPIs over time.")
    return recs


def build_excel(df: pd.DataFrame, insights: list[dict]) -> bytes:
    """Build a multi-sheet Excel summary workbook."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.head(1000).to_excel(writer, sheet_name="Data Sample", index=False)
        num_cols = numeric_columns(df)
        if num_cols:
            df[num_cols].describe().T.to_excel(writer, sheet_name="Statistics")
        pd.DataFrame(
            {"Insight": [_strip_html(i["text"]) for i in insights],
             "Severity": [i["kind"] for i in insights]}
        ).to_excel(writer, sheet_name="Insights", index=False)
        schema = pd.DataFrame({
            "Column": df.columns,
            "Type": [str(t) for t in df.dtypes],
            "Nulls": df.isna().sum().values,
            "Unique": [df[c].nunique() for c in df.columns],
        })
        schema.to_excel(writer, sheet_name="Schema", index=False)
    buffer.seek(0)
    return buffer.getvalue()


def render() -> None:
    """Render the Report Generator page."""
    page_banner(
        "📄", "Automated Report Generator",
        "Generate a board-ready PDF report and an Excel summary in one click.",
    )
    if not require_data():
        return

    df: pd.DataFrame = st.session_state["df"]
    dataset_name = st.session_state.get("dataset_name", "dataset")
    insights = generate_insights(df)

    st.markdown("**Report will include:** Executive Summary · Dataset Overview · "
                "Insights · Recommendations")

    with st.expander("Preview insights", expanded=True):
        for item in insights:
            st.markdown(f"- {_strip_html(item['text'])}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("📑 Generate PDF Report", type="primary"):
            try:
                pdf_bytes = build_pdf(df, dataset_name, insights)
                get_database().log_report(dataset_name, "pdf")
                st.download_button(
                    "⬇️ Download PDF", data=pdf_bytes,
                    file_name=f"InsightAI_Report_{dataset_name}.pdf",
                    mime="application/pdf",
                )
                st.success("PDF report generated.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"PDF generation failed: {exc}")
                logger.exception("PDF generation failed")

    with c2:
        if st.button("📊 Generate Excel Summary"):
            try:
                xlsx_bytes = build_excel(df, insights)
                get_database().log_report(dataset_name, "excel")
                st.download_button(
                    "⬇️ Download Excel", data=xlsx_bytes,
                    file_name=f"InsightAI_Summary_{dataset_name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                st.success("Excel summary generated.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Excel generation failed: {exc}")
                logger.exception("Excel generation failed")
