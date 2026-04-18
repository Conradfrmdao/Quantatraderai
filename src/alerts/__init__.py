"""Alert pipeline — pluggable backends receive tagged trading events."""

from src.alerts.notifier import Notifier, TradingEvent, build_notifier

__all__ = ["Notifier", "TradingEvent", "build_notifier"]
