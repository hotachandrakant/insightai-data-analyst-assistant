"""InsightAI – AI Powered Data Analyst Assistant.

Main Streamlit entrypoint. Configures the page, injects the corporate theme,
renders the sidebar navigation and dispatches to the feature modules.

Run locally with:
    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from database import get_database
from modules import (
    auth,
    chatbot,
    cleaning,
    dashboard,
    eda,
    forecasting,
    insights,
    ml,
    reports,
    upload,
)
from utils import get_logger, load_config
from utils.ui import (
    footer,
    hero_3d,
    inject_css,
    kpi_cards,
    register_plotly_theme,
)

logger = get_logger("insightai.app")
cfg = load_config()

# Ordered navigation registry: label -> (icon, render fn, description).
PAGES: dict[str, tuple[str, callable, str]] = {
    "Home": ("🏠", None, "Overview & getting started"),
    "Data Upload": ("📂", upload.render, "Module 1"),
    "Data Cleaning": ("🧹", cleaning.render, "Module 2"),
    "Automated EDA": ("📊", eda.render, "Module 3"),
    "BI Dashboard": ("📈", dashboard.render, "Module 4"),
    "AI Chatbot": ("🤖", chatbot.render, "Module 5"),
    "ML Assistant": ("🧠", ml.render, "Module 6"),
    "Forecasting": ("🔮", forecasting.render, "Module 7"),
    "Insights": ("💡", insights.render, "Module 8"),
    "Reports": ("📄", reports.render, "Module 9"),
}


def _configure_page() -> None:
    st.set_page_config(
        page_title=f"{cfg.app_name} · {cfg.tagline}",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()
    register_plotly_theme()
    # Living, blurred orb layer that drifts behind every page for depth.
    st.markdown(
        '<div class="ia-orbs">'
        '<span class="ia-orb o1"></span><span class="ia-orb o2"></span>'
        '<span class="ia-orb o3"></span><span class="ia-orb o4"></span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _sidebar() -> str:
    """Render sidebar navigation and return the selected page label."""
    with st.sidebar:
        st.markdown(
            '<div class="ia-brand">📊 Insight<span>AI</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="color:#94A3B8;font-size:0.82rem;margin-top:-2px">{cfg.tagline}</div>'
            '<div class="ia-chips">'
            '<span class="ia-chip"><span class="ping"></span> Live</span>'
            '<span class="ia-chip">🌍 Global</span>'
            '<span class="ia-chip">🔒 Private</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        # Allow other parts of the app to jump pages (e.g. the home CTA button).
        if st.session_state.get("nav_target") in PAGES:
            st.session_state["nav"] = st.session_state.pop("nav_target")

        selection = st.radio(
            "Navigation",
            list(PAGES.keys()),
            format_func=lambda k: f"{PAGES[k][0]}  {k}",
            label_visibility="collapsed",
            key="nav",
        )

        st.divider()
        # ── Logged-in user chip ────────────────────────────────────────
        user = auth.current_user()
        if user:
            initial = (user.get("name") or "U")[0].upper()
            badge = "Guest" if user.get("guest") else "Verified ✓"
            st.markdown(
                f'<div class="ia-user"><div class="ia-avatar">{initial}</div>'
                f'<div><div class="ia-user-name">{user.get("name")}</div>'
                f'<div class="ia-user-meta">{badge}</div></div></div>',
                unsafe_allow_html=True,
            )
            if st.button("🚪 Log out", use_container_width=True):
                auth.logout()
                st.rerun()
            st.divider()

        dataset = st.session_state.get("dataset_name")
        if dataset:
            df = st.session_state["df"]
            st.markdown("**Active dataset**")
            st.success(f"{dataset}\n\n{df.shape[0]:,} rows × {df.shape[1]} cols")
            if st.button("🔄 Reset to original"):
                st.session_state["df"] = st.session_state["df_original"].copy()
                st.rerun()
        else:
            st.info("No dataset loaded")

        st.divider()
        st.markdown(
            f'<div class="ia-side-foot">v{cfg.version} · '
            f'{"🟢 LLM connected" if cfg.llm_enabled else "⚪ Offline engine"}<br>'
            'Runs entirely in your browser session.<br>'
            'Built with Streamlit · Plotly · scikit-learn</div>',
            unsafe_allow_html=True,
        )
    return selection


def _home() -> None:
    """Render the landing / home page."""
    hero_3d(
        'Turn raw data into<br><span class="grad">decisions</span>, instantly.',
        "InsightAI is your virtual data analyst — upload a CSV or Excel file and get "
        "automated cleaning, EDA, executive dashboards, ML predictions, forecasting, "
        "natural-language Q&A and board-ready reports in seconds.",
        height=500,
    )

    # Real, working CTA button (the in-hero CTA gives tap feedback; this navigates).
    bc1, bc2, bc3 = st.columns([1, 1.5, 1])
    with bc2:
        if st.button("🚀  Begin your analysis — Upload data",
                     type="primary", use_container_width=True):
            st.session_state["nav_target"] = "Data Upload"
            st.rerun()

    try:
        stats = get_database().stats()
    except Exception:  # noqa: BLE001
        stats = {"datasets": 0, "queries": 0, "reports": 0}

    kpi_cards([
        {"label": "Datasets Analysed", "value": f"{stats['datasets']:,}"},
        {"label": "Questions Answered", "value": f"{stats['queries']:,}"},
        {"label": "Reports Generated", "value": f"{stats['reports']:,}"},
        {"label": "Analysis Modules", "value": "9"},
    ])

    st.markdown(
        '<h3 style="margin-bottom:0.2rem">Everything a data analyst does — automated</h3>'
        '<p style="color:#94A3B8;margin-top:0">Nine intelligent modules, one seamless workflow.</p>',
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    feature_blurbs = [
        ("📂", "Data Upload", "CSV/Excel ingestion with instant preview and schema."),
        ("🧹", "Cleaning", "Detect & fix missing values, duplicates and outliers."),
        ("📊", "Automated EDA", "Interactive distributions, correlations and relationships."),
        ("📈", "BI Dashboard", "Executive KPIs, trends, category & regional analysis."),
        ("🤖", "AI Chatbot", "Ask questions in plain English, get charts & answers."),
        ("🧠", "ML Assistant", "Auto classification/regression with accuracy, precision, recall & F1."),
        ("🔮", "Forecasting", "Project future trends with ARIMA / Prophet."),
        ("💡", "Insights", "Board-ready business recommendations, automatically."),
        ("📄", "Reports", "One-click PDF and Excel report generation."),
    ]
    for i, (icon, title, blurb) in enumerate(feature_blurbs):
        with cols[i % 3]:
            st.markdown(
                f'<div class="ia-card" style="animation-delay:{i*0.06:.2f}s">'
                f'<div style="font-size:1.9rem;line-height:1">{icon}</div>'
                f'<h3 style="margin:0.4rem 0 0.3rem">{title}</h3>'
                f'<p>{blurb}</p></div>',
                unsafe_allow_html=True,
            )

    # ── "Why InsightAI" trust band ─────────────────────────────────
    st.markdown(
        '<div class="ia-card" style="margin-top:0.6rem">'
        '<h3>Why analysts choose InsightAI</h3>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:1rem;margin-top:0.4rem">'
        '<div><div style="font-size:1.5rem">⚡</div><b>Seconds, not hours</b>'
        '<p>Full analysis pipeline runs the moment you upload.</p></div>'
        '<div><div style="font-size:1.5rem">🌍</div><b>Use anywhere</b>'
        '<p>Responsive web app — works on desktop, iPad and phone.</p></div>'
        '<div><div style="font-size:1.5rem">🎯</div><b>Rigorous ML</b>'
        '<p>Cross-validated models with precision, recall and F1 scores.</p></div>'
        '<div><div style="font-size:1.5rem">🔒</div><b>Private by design</b>'
        '<p>Your data stays in your session — nothing is stored externally.</p></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("df") is None:
        st.info("👉 Head to **Data Upload** in the sidebar to load a dataset or try a sample.")


def main() -> None:
    _configure_page()
    # Initialise session-state keys once.
    for key in ("df", "df_original", "dataset_name"):
        st.session_state.setdefault(key, None)

    # ── Authentication gate ────────────────────────────────────────────
    if not auth.is_authenticated():
        auth.render_gate()
        footer()
        return

    selection = _sidebar()
    try:
        if selection == "Home":
            _home()
        else:
            _, render_fn, _ = PAGES[selection]
            render_fn()
    except Exception as exc:  # noqa: BLE001 - last-resort UI guard
        logger.exception("Unhandled error rendering page %s", selection)
        st.error(f"😬 Something went wrong rendering this page: {exc}")
        st.caption("Check the logs in `logs/insightai.log` for details.")

    footer()


if __name__ == "__main__":
    main()
