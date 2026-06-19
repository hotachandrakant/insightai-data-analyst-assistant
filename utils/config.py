"""Application configuration for InsightAI.

Configuration is intentionally simple: sensible defaults baked into an
:class:`AppConfig` dataclass, overridable through environment variables. This
keeps the app runnable out-of-the-box while allowing secrets (e.g. LLM API
keys) to be injected at deploy time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_secret(key: str, default: str = "") -> str:
    """Resolve a secret from environment variables or Streamlit secrets.

    Order of precedence:
        1. OS environment variable (local dev: ``export KEY=...``)
        2. Streamlit Cloud secrets (``st.secrets`` / ``.streamlit/secrets.toml``)

    This lets the same code pick up API keys whether running locally or on
    Streamlit Community Cloud (where secrets are set in the app dashboard).
    """
    value = os.getenv(key)
    if value:
        return value
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:  # noqa: BLE001 - secrets unavailable outside a Streamlit run
        pass
    return default


@dataclass(frozen=True)
class AppConfig:
    """Immutable runtime configuration."""

    app_name: str = "InsightAI"
    tagline: str = "AI Powered Data Analyst Assistant"
    version: str = "1.0.0"

    # Filesystem layout
    data_dir: Path = PROJECT_ROOT / "data"
    models_dir: Path = PROJECT_ROOT / "models"
    database_dir: Path = PROJECT_ROOT / "database"
    assets_dir: Path = PROJECT_ROOT / "assets"

    # Database
    db_path: Path = PROJECT_ROOT / "database" / "insightai.db"

    # Upload limits
    max_upload_mb: int = 200
    allowed_extensions: tuple[str, ...] = ("csv", "xlsx", "xls")

    # Cinematic dark "liquid glass" palette (RouteWise-inspired)
    primary_color: str = "#6366F1"      # indigo
    secondary_color: str = "#22D3EE"    # cyan
    accent_color: str = "#FBBF24"       # gold (route highlight)
    success_color: str = "#34D399"
    warning_color: str = "#FBBF24"
    danger_color: str = "#F43F5E"
    plotly_palette: tuple[str, ...] = (
        "#6366F1", "#22D3EE", "#FBBF24", "#34D399",
        "#F43F5E", "#A78BFA", "#F472B6", "#2DD4BF",
    )

    # LLM integration (optional) — read from env vars OR Streamlit Cloud secrets
    openai_api_key: str = field(default_factory=lambda: get_secret("OPENAI_API_KEY"))
    gemini_api_key: str = field(default_factory=lambda: get_secret("GEMINI_API_KEY"))
    llm_provider: str = field(default_factory=lambda: get_secret("LLM_PROVIDER", "auto"))

    @property
    def llm_enabled(self) -> bool:
        """True when at least one LLM provider key is configured."""
        return bool(self.openai_api_key or self.gemini_api_key)

    def ensure_dirs(self) -> None:
        """Create runtime directories if they do not yet exist."""
        for path in (self.data_dir, self.models_dir, self.database_dir, self.assets_dir):
            path.mkdir(parents=True, exist_ok=True)


_config: AppConfig | None = None


def load_config() -> AppConfig:
    """Return a cached singleton :class:`AppConfig` instance."""
    global _config
    if _config is None:
        _config = AppConfig()
        _config.ensure_dirs()
    return _config
