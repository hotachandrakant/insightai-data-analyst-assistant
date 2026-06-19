"""Utility package for InsightAI.

Exposes the most commonly used helpers at package level so callers can do
``from utils import get_logger, load_config``.
"""
from utils.logger import get_logger
from utils.config import load_config, AppConfig

__all__ = ["get_logger", "load_config", "AppConfig"]
