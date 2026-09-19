"""Remember which feed items were already used, so an episode never repeats one."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .config import OUT_DIR

STATE_FILE = OUT_DIR / "seen.json"
KEEP_DAYS = 45


def load_seen() -> dict[str, str]:
    if not STATE_FILE.is_file():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data.get("used", {}) if isinstance(data, dict) else {}


def save_seen(used: dict[str, str], today: date) -> None:
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    pruned = {uid: day for uid, day in used.items() if day >= cutoff}
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"used": pruned}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    tmp.replace(STATE_FILE)
