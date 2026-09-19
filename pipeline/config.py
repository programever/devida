"""Paths, settings and the small amount of show metadata DeViDa needs."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_DIR / "out"
DAYS_DIR = OUT_DIR / "days"
FEEDS_FILE = PROJECT_DIR / "feeds.txt"
PROMPT_FILE = PROJECT_DIR / "prompt.md"

DEFAULT_ENV_FILE = Path.home() / "alpha" / ".env"

# The page shows this many days. Older days stay on this box for ever; they only
# stop being published. Iker asked for 7 days on 2026-09-16.
PAGE_DAYS = 7


def load_env_file(path: Path | None = None) -> None:
    """Fill in missing os.environ keys from a KEY=VALUE file. Real env wins."""
    path = path or Path(os.environ.get("DEVIDA_ENV", DEFAULT_ENV_FILE))
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    claude_bin: str
    claude_model: str
    claude_timeout: int
    claude_workers: int
    story_count: int
    summary_words: int
    tts_voice: str
    tts_rate: str
    tts_pause_seconds: float
    page_days: int
    site_repo: str
    site_branch: str
    site_url: str
    http_timeout: float


def load_config(env_file: Path | None = None) -> Config:
    load_env_file(env_file)
    return Config(
        claude_bin=os.environ.get("CLAUDE_BIN", "").strip()
        or str(Path.home() / ".local" / "bin" / "claude"),
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-opus-5").strip(),
        claude_timeout=_int("CLAUDE_TIMEOUT", 420),
        claude_workers=_int("CLAUDE_WORKERS", 3),
        # Full size since 2026-09-16, when Iker said the shape was right.
        story_count=_int("STORY_COUNT", 15),
        # Iker asked for longer descriptions on 2026-09-16: simple English needs
        # more sentences than dense English to say the same thing.
        summary_words=_int("SUMMARY_WORDS", 130),
        # A clear American woman's voice. edge-tts has no daily limit.
        tts_voice=os.environ.get("TTS_VOICE", "en-US-AriaNeural").strip(),
        # A little slower than normal. English is not Iker's first language, and
        # a slower voice is much easier to follow.
        tts_rate=os.environ.get("TTS_RATE", "-10%").strip(),
        tts_pause_seconds=_float("TTS_PAUSE_SECONDS", 0.7),
        page_days=_int("PAGE_DAYS", PAGE_DAYS),
        site_repo=os.environ.get(
            "SITE_REPO", "git@github.com:programever/devida.git"
        ).strip(),
        site_branch=os.environ.get("SITE_BRANCH", "gh-pages").strip(),
        site_url=os.environ.get(
            "SITE_URL", "https://programever.github.io/devida/"
        ).strip(),
        http_timeout=_float("HTTP_TIMEOUT", 25.0),
    )


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def day_dir(day: date) -> Path:
    return DAYS_DIR / day.isoformat()


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")


def long_date(day: date) -> str:
    """The date written out in full, so the voice reads it like a person."""
    return f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]} {day.year}"


def short_date(day: date) -> str:
    """The date for one news story, shown under its title on the page."""
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def published_on(stamp: str) -> str:
    """Turn a stored publish time into a date Iker can read.

    Feeds give the time in world time (UTC). Iker is in Vietnam, seven hours
    ahead, so a story posted late in the evening Vietnam time would otherwise
    show yesterday's date. The time is moved to Vietnam time first.

    An empty or broken value gives an empty string, never an error. The date is
    a nice extra on the page; it must never stop a day being published.
    """
    if not stamp:
        return ""
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return short_date(when.astimezone(VN_TZ).date())


def published_days(limit: int) -> list[date]:
    """The days the page shows: the newest `limit` days we have built."""
    if not DAYS_DIR.is_dir():
        return []
    days: list[date] = []
    for folder in DAYS_DIR.iterdir():
        if not (folder / "content.json").is_file():
            continue
        try:
            days.append(date.fromisoformat(folder.name))
        except ValueError:
            continue
    return sorted(days, reverse=True)[:limit]
