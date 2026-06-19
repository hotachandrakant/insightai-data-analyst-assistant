"""Database package for InsightAI (SQLite-backed session history)."""
from database.db import Database, get_database

__all__ = ["Database", "get_database"]
