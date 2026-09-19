"""Step 5: build the web page from the last few days.

One plain HTML file, no build tools, no JavaScript framework. It has to open fast
on a phone and still be readable in a year, so the styling is inline and simple.
"""
from __future__ import annotations

import html
import json
import logging
import shutil
from datetime import date
from pathlib import Path

from .config import Config, day_dir, long_date, published_days
from .content import Day, day_from_dict, spoken_parts
from .voice import audio_matches, duration_seconds

log = logging.getLogger(__name__)

SITE_TITLE = "DeViDa"
SITE_TAGLINE = "Technology news for developers, every day, in simple English"

# The page is public because a free GitHub web page has to be. It holds nothing
# private, but there is no reason for it to turn up in search results.
ROBOTS_TXT = "User-agent: *\nDisallow: /\n"

STYLE = """
*, *::before, *::after { box-sizing: border-box; }
:root {
  color-scheme: light dark;
  --bg: #fbfbfd; --card: #ffffff; --ink: #1d1d22; --soft: #63636e;
  --line: #e4e4ea; --accent: #2f5bd7; --chip: #eef1fb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14141a; --card: #1d1d25; --ink: #f0f0f4; --soft: #a0a0ad;
    --line: #2e2e39; --accent: #8fb0ff; --chip: #262633;
  }
}
body {
  margin: 0; padding: 0 1rem 4rem; background: var(--bg); color: var(--ink);
  font: 17px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 44rem; margin: 0 auto; }
header { padding: 2.5rem 0 1rem; border-bottom: 1px solid var(--line); margin-bottom: 1.5rem; }
h1 { margin: 0; font-size: 1.9rem; letter-spacing: -0.02em; }
header p { margin: 0.4rem 0 0; color: var(--soft); font-size: 0.95rem; }
.day { margin: 2.5rem 0; }
.day > h2 { font-size: 1.15rem; margin: 0 0 0.25rem; letter-spacing: -0.01em; }
.built { color: var(--soft); font-size: 0.82rem; margin: 0 0 0.9rem; }
audio { width: 100%; margin-bottom: 1.5rem; }
.noaudio {
  border: 1px dashed var(--line); border-radius: 10px; padding: 0.7rem 0.9rem;
  color: var(--soft); font-size: 0.9rem; margin-bottom: 1.5rem;
}
article {
  background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 1rem 1.1rem; margin-bottom: 0.85rem;
}
article h3 { margin: 0.45rem 0 0.35rem; font-size: 1.06rem; line-height: 1.4; }
article p { margin: 0 0 0.75rem; }
.when { color: var(--soft); font-size: 0.82rem; margin: 0 0 0.6rem; }
.chip {
  display: inline-block; background: var(--chip); color: var(--soft);
  border-radius: 999px; padding: 0.12rem 0.6rem;
  font-size: 0.74rem; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase;
}
.src { font-size: 0.86rem; color: var(--soft); }
.src a { color: var(--accent); text-decoration: none; }
.src a:hover { text-decoration: underline; }
footer {
  margin-top: 3.5rem; padding-top: 1.2rem; border-top: 1px solid var(--line);
  color: var(--soft); font-size: 0.85rem;
}
"""


def _audio_block(day: date, mp3: Path | None) -> str:
    if mp3 is None:
        return ('<div class="noaudio">There is no recording today. '
                "Microsoft's voice service did not answer.</div>")
    seconds = duration_seconds(mp3)
    length = f"{seconds // 60} min {seconds % 60:02d} sec" if seconds else "recording"
    return (
        f'<audio controls preload="none" src="audio/{day.isoformat()}.mp3" '
        f'title="Recording for {day.isoformat()} — {length}"></audio>'
    )


def _story_block(story) -> str:
    e = html.escape
    # The date sits under the title, on the page only. It is never spoken: Iker
    # asked for that on 2026-09-16, because hearing a date before every story
    # gets in the way of listening. Some feeds give no date, and then the line
    # is simply left out rather than showing something empty or wrong.
    when = story.published_label
    date_line = f'<p class="when">{e(when)}</p>' if when else ""
    return (
        "<article>"
        f'<span class="chip">{e(story.topic_label)}</span>'
        f"<h3>{e(story.title)}</h3>"
        f"{date_line}"
        f"<p>{e(story.description)}</p>"
        f'<p class="src">{e(story.source)} — '
        f'<a href="{e(story.link)}" target="_blank" rel="noopener noreferrer">read the original</a></p>'
        "</article>"
    )


def _day_block(entry: Day, mp3: Path | None) -> str:
    stories = "".join(_story_block(s) for s in entry.stories)
    count = len(entry.stories)
    built = (f"<p class=\"built\">{count} {'story' if count == 1 else 'stories'}"
             f" · built at {html.escape(entry.built_at)}</p>")
    return (
        f'<section class="day" id="{entry.day.isoformat()}">'
        f"<h2>{html.escape(long_date(entry.day))}</h2>"
        f"{built}{_audio_block(entry.day, mp3)}{stories}"
        "</section>"
    )


def render(days: list[tuple[Day, Path | None]], site_url: str) -> str:
    newest = days[0][0].day.isoformat() if days else ""
    body = "".join(_day_block(entry, mp3) for entry, mp3 in days)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        f"<title>{SITE_TITLE} — {SITE_TAGLINE}</title>\n"
        f"<style>{STYLE}</style>\n</head>\n<body>\n"
        '<div class="wrap">\n'
        f"<header><h1>{SITE_TITLE}</h1><p>{SITE_TAGLINE}</p></header>\n"
        f"{body}\n"
        "<footer>This page keeps only the last "
        f"{len(days)} {'day' if len(days) == 1 else 'days'}. Newest: {newest}.</footer>\n"
        "</div>\n</body>\n</html>\n"
    )


def load_day(day: date) -> Day | None:
    saved = day_dir(day) / "content.json"
    if not saved.is_file():
        return None
    try:
        return day_from_dict(json.loads(saved.read_text(encoding="utf-8")))
    except (ValueError, KeyError, TypeError, OSError) as err:
        log.warning("cannot read the content of %s (%s), leaving it off the page", day, err)
        return None


def build_site(cfg: Config, target: Path) -> list[date]:
    """Write the whole page into an empty folder. Returns the days it published."""
    target.mkdir(parents=True, exist_ok=True)
    audio_dir = target / "audio"
    audio_dir.mkdir(exist_ok=True)

    days: list[tuple[Day, Path | None]] = []
    for day in published_days(cfg.page_days):
        entry = load_day(day)
        if entry is None:
            continue
        folder = day_dir(day)
        source_mp3 = folder / "audio.mp3"
        copied: Path | None = None
        if source_mp3.is_file() and source_mp3.stat().st_size > 0:
            # The sound must say the words we are about to print next to it.
            # A leftover file from an earlier, different run is not good enough.
            if audio_matches(folder, spoken_parts(entry)):
                copied = audio_dir / f"{day.isoformat()}.mp3"
                shutil.copy2(source_mp3, copied)
            else:
                log.warning(
                    "%s has a sound file that does not match its words, "
                    "leaving it off the page", day
                )
        days.append((entry, copied))

    if not days:
        raise RuntimeError("no day has content yet, there is nothing to publish")

    (target / "index.html").write_text(render(days, cfg.site_url), encoding="utf-8")
    (target / "robots.txt").write_text(ROBOTS_TXT, encoding="utf-8")
    # Stops GitHub from running the page through its blog engine, which would
    # hide any file whose name starts with an underscore.
    (target / ".nojekyll").write_text("", encoding="utf-8")

    published = [entry.day for entry, _ in days]
    with_audio = sum(1 for _, mp3 in days if mp3 is not None)
    log.info("site: %d days, %d with audio", len(published), with_audio)
    return published
