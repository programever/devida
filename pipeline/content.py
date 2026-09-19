"""Step 3: turn each chosen story into a title, a description and a link.

This is the whole "content" Iker asked for. One plain English title, one plain
English description, and the address of the original article so Iker can go and
read it. Everything is written in simple English on purpose: Iker is Vietnamese
and reads and listens in English as a second language.
"""
from __future__ import annotations

import dataclasses
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from .claude_cli import Claude, ClaudeError, fill
from .config import Config, long_date, published_on
from .crawl import Item, fetch_article

log = logging.getLogger(__name__)

STORY_FORMAT = """{
  "title": "a short plain English title, up to about 90 characters",
  "description": "simple English prose saying what happened, why a developer should care, and what to watch next"
}"""

TOPIC_LABELS = {
    "ai": "AI",
    "web": "Web",
    "ts": "TypeScript",
    "dev": "Dev tools",
}


@dataclasses.dataclass
class Story:
    uid: str
    topic: str
    title: str          # simple English
    description: str    # simple English
    link: str
    source: str
    original_title: str
    # When the story itself was published, as the feed gave it. Shown under the
    # title on the page. Never spoken: Iker asked on 2026-09-16 for the date to
    # be on the page only, because hearing a date before every story is noise.
    # Empty when a feed gave no date, which some do.
    published: str = ""

    @property
    def topic_label(self) -> str:
        return TOPIC_LABELS.get(self.topic, self.topic)

    @property
    def published_label(self) -> str:
        return published_on(self.published)


@dataclasses.dataclass
class Day:
    day: date
    stories: list[Story]
    built_at: str

    @property
    def word_count(self) -> int:
        return sum(len(s.description.split()) + len(s.title.split()) for s in self.stories)


def safe_workers(cfg: Config) -> int:
    """More than a few parallel `claude -p` calls just queue up and time out."""
    return max(1, min(cfg.claude_workers, 4))


def _one_story(claude: Claude, prompts: dict[str, str], cfg: Config, item: Item) -> Story | None:
    article = fetch_article(item, cfg.http_timeout)
    prompt = fill(
        prompts["story"],
        words=str(cfg.summary_words),
        format=STORY_FORMAT,
        topic=TOPIC_LABELS.get(item.topic, item.topic),
        title=item.title,
        source=item.source,
        link=item.link,
        summary=item.summary or "(none)",
        article=article or "(the full article could not be read, use the summary)",
    )
    try:
        answer = claude.ask_json(prompt, label=f"story {item.uid}")
    except ClaudeError as err:
        log.warning("story skipped, claude failed: %s (%s)", item.title[:60], err)
        return None

    title = str(answer.get("title", "")).strip()
    description = str(answer.get("description", "")).strip()
    if not title or not description:
        log.warning("story skipped, empty answer: %s", item.title[:60])
        return None
    return Story(
        uid=item.uid,
        topic=item.topic,
        title=title,
        description=description,
        link=item.link,
        source=item.source,
        original_title=item.title,
        published=item.published.isoformat() if item.published else "",
    )


def build_day(
    claude: Claude, prompts: dict[str, str], cfg: Config, day: date, items: list[Item]
) -> Day:
    """One Story for each chosen item. A story that fails is dropped, not fatal."""
    log.info("writing %d stories with %d workers", len(items), safe_workers(cfg))
    with ThreadPoolExecutor(max_workers=safe_workers(cfg)) as pool:
        results = list(pool.map(lambda i: _one_story(claude, prompts, cfg, i), items))

    stories = [s for s in results if s is not None]
    if not stories:
        raise ClaudeError("claude wrote no usable stories at all")
    if len(stories) < len(items):
        log.warning("%d of %d stories were dropped", len(items) - len(stories), len(items))
    log.info("content: %d stories for %s", len(stories), long_date(day))
    return Day(day=day, stories=stories, built_at=_stamp())


def _stamp() -> str:
    from .config import now_vn

    return now_vn().strftime("%Y-%m-%d %H:%M")


def day_to_dict(entry: Day) -> dict:
    return {
        "day": entry.day.isoformat(),
        "built_at": entry.built_at,
        "stories": [dataclasses.asdict(s) for s in entry.stories],
    }


def day_from_dict(data: dict) -> Day:
    return Day(
        day=date.fromisoformat(data["day"]),
        built_at=data.get("built_at", ""),
        # A day saved before the publish time was added simply has none.
        stories=[Story(**s) for s in data.get("stories", [])],
    )


def spoken_parts(entry: Day) -> list[str]:
    """What the voice reads: a short hello, then every story, then a goodbye.

    Everything is in simple English. Iker listens in English as a second
    language, so the wrapper words stay plain and the sentences stay short.

    One string per piece. The voice code turns each piece into audio on its own
    and joins them with a short silence, so the listener hears a small pause
    between stories.
    """
    count = len(entry.stories)
    word = "story" if count == 1 else "stories"
    parts = [
        f"Hello. This is DeViDa, your technology news for {long_date(entry.day)}. "
        f"Today there {'is' if count == 1 else 'are'} {count} {word}."
    ]
    for number, story in enumerate(entry.stories, start=1):
        opening = "Here is the story." if count == 1 else f"Story number {number}."
        parts.append(f"{opening} Topic: {story.topic_label}. {story.title}. {story.description}")
    parts.append("That is the end of today's news. Thank you for listening.")
    return parts
