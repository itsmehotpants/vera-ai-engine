"""
suppression.py — Per-signal suppression. V4: mark_sent ONLY called from main.py, never inside composer.
"""
from datetime import datetime, timedelta
import hashlib

_suppression_store: dict[str, datetime] = {}

WINDOW_DELTAS: dict[str, timedelta] = {
    "1h":  timedelta(hours=1),
    "4h":  timedelta(hours=4),
    "24h": timedelta(hours=24),
    "7d":  timedelta(days=7),
}

SIGNAL_DEFAULT_WINDOWS: dict[str, str] = {
    "search_spike":      "1h",
    "time_of_day_spike": "1h",
    "lapse_recall":      "4h",
    "offer_expiry":      "4h",
    "compliance_alert":  "4h",
    "refill_due":        "24h",
    "metric_dip":        "24h",
    "seasonal_dip":      "24h",
    "active_offer":      "24h",
    "festival":          "7d",
    "review_ask":        "7d",
    "generic":           "24h",
    "follow_through":        "1h",
    "soft_objection_handle": "4h",
    "objection_reframe":     "4h",
    "answer_question":       "1h",
    "clarification":         "1h",
}


def make_key(merchant_id: str, signal_type: str) -> str:
    raw = f"{merchant_id}:{signal_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_suppressed(key: str) -> bool:
    expiry = _suppression_store.get(key)
    if expiry is None:
        return False
    if datetime.utcnow() > expiry:
        del _suppression_store[key]
        return False
    return True


def mark_sent(key: str, window: str = "24h") -> None:
    delta = WINDOW_DELTAS.get(window, timedelta(hours=24))
    _suppression_store[key] = datetime.utcnow() + delta


def default_window(signal_type: str) -> str:
    return SIGNAL_DEFAULT_WINDOWS.get(signal_type, "24h")


def purge_expired() -> int:
    now = datetime.utcnow()
    expired = [k for k, exp in _suppression_store.items() if now > exp]
    for k in expired:
        del _suppression_store[k]
    return len(expired)
