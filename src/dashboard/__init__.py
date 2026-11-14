"""
Dashboard Module

Web dashboard for monitoring the trading system.
"""

from .app import create_app, get_app
from .routes import router

__all__ = [
    "create_app",
    "get_app",
    "router",
]
