"""Step 1: read the RSS/Atom feeds and return today's candidate stories."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import feedparser
import httpx

from .config import FEEDS_FILE, VN_TZ

log = logging.getLogger(__name__)

USER_AGENT = "DeViDaBot/1.0 (+https://programever.github.io/devida/)"

# hnrss carries the whole front page, so only the AI items are wanted from it.
HN_AI_WORDS = (
    "ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic", "deepmind",
    "mistral", "llama", "diffusion", "transformer", "neural", "machine learning",
    "deep learning", "agent", "rag", "embedding", "inference", "fine-tune",
    "fine tune", "copilot", "cursor", "hugging face", "model",
)

TOPICS = ("ai", "web", "ts", "dev")

# Many projects tag a test build many times a day: v3.6.0-rc.9, v16.4.0-canary.36,
# "nightly: ...", "Nvim development (prerelease) build". They are not news, and a
# busy project can bury a real release under ten of them. These are dropped, but
# ONLY from GitHub release feeds. A company blog post may honestly be titled
# "Gemini 3.8 preview" and that is real news, so the filter never touches a blog.
PRERELEASE = re.compile(
    r"-(rc|alpha|beta|canary|next|nightly|dev|pre|preview|snapshot)[.\-]?\d*\b"
    r"|\d(rc|alpha|beta)\d*\b"
    r"|\b(nightly|prerelease|pre-release|development build|tip|staging|collab)\b",
    re.IGNORECASE,
)


def _is_github_releases(feed: "Feed") -> bool:
    return "github.com" in feed.host and feed.url.rstrip("/").endswith("releases.atom")


def _is_prerelease(title: str) -> bool:
    return bool(PRERELEASE.search(title))

# Every topic looks back exactly 24 hours. Iker asked for this on 2026-09-16:
# only what really happened since yesterday, nothing older.
#
# The cost of that rule was measured the same day and accepted. The official web
# and TypeScript blogs post a few times a year, so in a 24 hour window they give
# almost nothing, and most days are AI and dev. Iker chose that over reading
# stories he had already seen. Do not quietly widen these windows to "help".
DEFAULT_WINDOW_HOURS = 24
TOPIC_WINDOW_HOURS = {topic: DEFAULT_WINDOW_HOURS for topic in TOPICS}


@dataclass
class Item:
    uid: str
    topic: str
    title: str
    link: str
    source: str
    summary: str
    published: datetime
    article: str = field(default="")


@dataclass
class Feed:
    topic: str
    url: str

    @property
    def host(self) -> str:
        return urlsplit(self.url).netloc


def read_feeds(path=FEEDS_FILE) -> list[Feed]:
    feeds: list[Feed] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            log.warning("feeds.txt: skipping bad line %r", raw)
            continue
        topic, url = parts[0].strip().lower(), parts[1].strip()
        if topic not in TOPICS:
            log.warning("feeds.txt: unknown topic %r, skipping %s", topic, url)
            continue
        feeds.append(Feed(topic, url))
    return feeds


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        stamp = entry.get(key)
        if stamp:
            return datetime(*stamp[:6], tzinfo=timezone.utc)
    return None


def _uid(link: str, title: str) -> str:
    key = (link or "").strip().lower() or _clean(title).lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _title_key(title: str) -> str:
    plain = unicodedata.normalize("NFKD", _clean(title).lower())
    return re.sub(r"[^a-z0-9 ]+", "", plain)[:70].strip()


def _looks_like_ai(title: str, summary: str) -> bool:
    text = f" {_clean(title).lower()} {_clean(summary).lower()[:400]} "
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in HN_AI_WORDS)


def _fetch_one(feed: Feed, cutoff: datetime, timeout: float) -> list[Item]:
    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = client.get(feed.url)
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
    except Exception as err:
        log.warning("feed down, skipping: %s (%s)", feed.url, err)
        return []

    source = _clean(parsed.feed.get("title", "")) or feed.host
    items: list[Item] = []
    for entry in parsed.entries[:40]:
        published = _entry_time(entry)
        if published is None or published < cutoff:
            continue
        title = _clean(entry.get("title", ""))
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = _clean(entry.get("summary", ""))[:1200]
        # hnrss carries the whole front page, so the AI feed keeps only the AI
        # items. This is tied to the topic, not the host: a Hacker News feed
        # added under another topic must not be filtered for AI words.
        if feed.topic == "ai" and "hnrss.org" in feed.host \
                and not _looks_like_ai(title, summary):
            continue
        # A GitHub release feed also carries every test build. Skip those.
        if _is_github_releases(feed) and _is_prerelease(title):
            continue
        items.append(
            Item(
                uid=_uid(link, title),
                topic=feed.topic,
                title=title,
                link=link,
                source=source,
                summary=summary,
                published=published,
            )
        )
    log.info("%-38s %2d items  (%s)", feed.host, len(items), feed.topic)
    return items


def window_hours(day, topic: str) -> int:
    """How far back this topic looks. The same for every topic, every day."""
    return _env_hours(topic, TOPIC_WINDOW_HOURS.get(topic, DEFAULT_WINDOW_HOURS))


def _env_hours(topic: str, default: int) -> int:
    try:
        return int(os.environ.get(f"WINDOW_HOURS_{topic.upper()}", "").strip() or default)
    except ValueError:
        return default


def crawl(day, seen: dict[str, str], timeout: float = 25.0) -> list[Item]:
    feeds = read_feeds()
    now = datetime.now(VN_TZ).astimezone(timezone.utc)
    cutoffs = {
        topic: now - timedelta(hours=window_hours(day, topic)) for topic in TOPICS
    }
    log.info(
        "windows: %s",
        ", ".join(f"{t}={window_hours(day, t)}h" for t in TOPICS),
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        batches = pool.map(lambda f: _fetch_one(f, cutoffs[f.topic], timeout), feeds)

    items: list[Item] = []
    seen_uids: set[str] = set()
    seen_titles: set[str] = set()
    for batch in batches:
        for item in batch:
            title_key = _title_key(item.title)
            if item.uid in seen or item.uid in seen_uids or title_key in seen_titles:
                continue
            seen_uids.add(item.uid)
            if title_key:
                seen_titles.add(title_key)
            items.append(item)

    items.sort(key=lambda i: (TOPICS.index(i.topic), -i.published.timestamp()))
    log.info("crawl: %d fresh items from %d feeds", len(items), len(feeds))
    return items


def fetch_article(item: Item, timeout: float = 25.0, max_chars: int = 6000) -> str:
    """Full text of one story. Falls back to the feed summary."""
    try:
        import trafilatura

        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = client.get(item.link)
            response.raise_for_status()
        text = trafilatura.extract(
            response.text, include_comments=False, include_tables=False
        )
    except Exception as err:
        log.warning("article fetch failed for %s (%s)", item.link, err)
        text = None
    text = _clean(text or "") or item.summary
    return text[:max_chars]
